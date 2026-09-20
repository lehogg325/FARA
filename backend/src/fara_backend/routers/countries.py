from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from fara_backend.db import get_db
from fara_backend.graph import build_country_graph, build_registrant_expansion, top_contacts, top_recipients
from fara_backend.schemas import (
    Country,
    CountryContact,
    CountryContribution,
    CountryDetail,
    CountryGraph,
    Page,
    RegistrantExpansion,
    RegistrantSummary,
    TopContact,
    TopicCount,
    TopRecipient,
)

router = APIRouter(prefix="/countries", tags=["countries"])


@router.get("", response_model=list[Country])
def list_countries(jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)) -> list[Country]:
    rows = conn.execute(
        """
        SELECT c.country_name, c.note,
               count(DISTINCT fp.registrant_id) AS registrant_count,
               count(DISTINCT fp.foreign_principal_id) AS foreign_principal_count
        FROM countries c
        LEFT JOIN foreign_principals fp ON fp.jurisdiction = c.jurisdiction AND fp.country_raw = c.country_name
        WHERE c.jurisdiction = %s
        GROUP BY c.country_name, c.note
        -- Seed data includes defensive spelling variants that were never actually
        -- observed in real filings — hide those dead entries instead of listing
        -- every possible DOJ spelling (migration 0008_country_notes.sql).
        HAVING count(DISTINCT fp.registrant_id) > 0
        ORDER BY registrant_count DESC, c.country_name
        """,
        (jurisdiction,),
    ).fetchall()
    return [Country(**r) for r in rows]


@router.get("/{country_name}", response_model=CountryDetail)
def get_country(
    country_name: str, jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)
) -> CountryDetail:
    exists = conn.execute(
        "SELECT 1 FROM countries WHERE jurisdiction = %s AND country_name = %s", (jurisdiction, country_name)
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="country not found")

    row = conn.execute(
        """
        SELECT
            count(DISTINCT r.registrant_id) FILTER (WHERE r.status = 'active') AS active_registrant_count,
            count(DISTINCT r.registrant_id) AS total_registrant_count,
            count(DISTINCT fp.foreign_principal_id) AS foreign_principal_count
        FROM foreign_principals fp
        JOIN registrants r ON r.registrant_id = fp.registrant_id
        WHERE fp.jurisdiction = %(j)s AND fp.country_raw = %(country)s
        """,
        {"j": jurisdiction, "country": country_name},
    ).fetchone()

    contact_row = conn.execute(
        """
        SELECT count(*) AS contact_count
        FROM reportable_contacts rc
        JOIN registrant_docs rd ON rd.registrant_doc_id = rc.registrant_doc_id
        JOIN foreign_principals fp ON fp.registrant_id = rd.registrant_id
        WHERE fp.jurisdiction = %(j)s AND fp.country_raw = %(country)s
        """,
        {"j": jurisdiction, "country": country_name},
    ).fetchone()

    contrib_row = conn.execute(
        """
        SELECT count(*) AS contribution_count, sum(def.field_value_numeric) AS contribution_total
        FROM document_extracted_fields def
        JOIN registrant_docs rd ON rd.registrant_doc_id = def.registrant_doc_id
        JOIN foreign_principals fp ON fp.registrant_id = rd.registrant_id
        WHERE fp.jurisdiction = %(j)s AND fp.country_raw = %(country)s AND def.field_key LIKE 'political_contribution[%%'
        """,
        {"j": jurisdiction, "country": country_name},
    ).fetchone()

    return CountryDetail(
        country_name=country_name,
        active_registrant_count=row["active_registrant_count"],
        total_registrant_count=row["total_registrant_count"],
        foreign_principal_count=row["foreign_principal_count"],
        contact_count=contact_row["contact_count"],
        contribution_count=contrib_row["contribution_count"],
        contribution_total=contrib_row["contribution_total"],
    )


@router.get("/{country_name}/registrants", response_model=Page[RegistrantSummary])
def get_country_registrants(
    country_name: str,
    jurisdiction: str = Query("fara"),
    status: str | None = Query(None, pattern="^(active|terminated)$"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
    conn: psycopg.Connection = Depends(get_db),
) -> Page[RegistrantSummary]:
    where = ["fp.jurisdiction = %(j)s", "fp.country_raw = %(country)s"]
    params: dict = {"j": jurisdiction, "country": country_name, "limit": limit, "offset": offset}
    if status:
        where.append("r.status = %(status)s")
        params["status"] = status
    where_sql = " AND ".join(where)

    # DISTINCT r.* matches get_country()'s count(DISTINCT r.registrant_id) above —
    # a registrant with two foreign_principals rows for this country (e.g. a
    # re-registration) isn't listed twice.
    total = conn.execute(
        f"""
        SELECT count(DISTINCT r.registrant_id) AS n
        FROM registrants r JOIN foreign_principals fp ON fp.registrant_id = r.registrant_id
        WHERE {where_sql}
        """,
        params,
    ).fetchone()["n"]
    rows = conn.execute(
        f"""
        SELECT DISTINCT r.*
        FROM registrants r JOIN foreign_principals fp ON fp.registrant_id = r.registrant_id
        WHERE {where_sql}
        ORDER BY r.name LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    ).fetchall()
    return Page(items=[RegistrantSummary(**r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{country_name}/contacts", response_model=Page[CountryContact])
def get_country_contacts(
    country_name: str,
    jurisdiction: str = Query("fara"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
    conn: psycopg.Connection = Depends(get_db),
) -> Page[CountryContact]:
    params = {"j": jurisdiction, "country": country_name, "limit": limit, "offset": offset}
    # Same join shape as get_country()'s contact_row above, so this total always
    # matches the number that was clicked.
    total = conn.execute(
        """
        SELECT count(*) AS n
        FROM reportable_contacts rc
        JOIN registrant_docs rd ON rd.registrant_doc_id = rc.registrant_doc_id
        JOIN foreign_principals fp ON fp.registrant_id = rd.registrant_id
        WHERE fp.jurisdiction = %(j)s AND fp.country_raw = %(country)s
        """,
        params,
    ).fetchone()["n"]
    rows = conn.execute(
        """
        SELECT rc.reportable_contact_id, rc.registrant_doc_id, rd.registrant_id, r.name AS registrant_name,
               rc.contact_date, rc.contact_name_raw, rc.contact_method, rc.purpose
        FROM reportable_contacts rc
        JOIN registrant_docs rd ON rd.registrant_doc_id = rc.registrant_doc_id
        JOIN foreign_principals fp ON fp.registrant_id = rd.registrant_id
        JOIN registrants r ON r.registrant_id = rd.registrant_id
        WHERE fp.jurisdiction = %(j)s AND fp.country_raw = %(country)s
        ORDER BY rc.contact_date DESC NULLS LAST
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    ).fetchall()
    return Page(items=[CountryContact(**r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{country_name}/contributions", response_model=Page[CountryContribution])
def get_country_contributions(
    country_name: str,
    jurisdiction: str = Query("fara"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
    conn: psycopg.Connection = Depends(get_db),
) -> Page[CountryContribution]:
    params = {"j": jurisdiction, "country": country_name, "limit": limit, "offset": offset}
    # Same join shape as get_country()'s contrib_row above, so this total always
    # matches the number that was clicked. Each political_contribution[N] field_key
    # is already one full contribution record (text=recipient, numeric=amount,
    # date=date) — confirmed live, not split across multiple field_keys — so this
    # is a plain SELECT, not a re-aggregation.
    total = conn.execute(
        """
        SELECT count(*) AS n
        FROM document_extracted_fields def
        JOIN registrant_docs rd ON rd.registrant_doc_id = def.registrant_doc_id
        JOIN foreign_principals fp ON fp.registrant_id = rd.registrant_id
        WHERE fp.jurisdiction = %(j)s AND fp.country_raw = %(country)s AND def.field_key LIKE 'political_contribution[%%'
        """,
        params,
    ).fetchone()["n"]
    rows = conn.execute(
        """
        SELECT rd.registrant_doc_id, rd.registrant_id, r.name AS registrant_name,
               def.field_value_text AS recipient_raw, def.field_value_numeric AS amount,
               def.field_value_date AS contribution_date
        FROM document_extracted_fields def
        JOIN registrant_docs rd ON rd.registrant_doc_id = def.registrant_doc_id
        JOIN foreign_principals fp ON fp.registrant_id = rd.registrant_id
        JOIN registrants r ON r.registrant_id = rd.registrant_id
        WHERE fp.jurisdiction = %(j)s AND fp.country_raw = %(country)s AND def.field_key LIKE 'political_contribution[%%'
        ORDER BY def.field_value_date DESC NULLS LAST
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    ).fetchall()
    return Page(items=[CountryContribution(**r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{country_name}/topics", response_model=list[TopicCount])
def get_country_topics(
    country_name: str, jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)
) -> list[TopicCount]:
    rows = conn.execute(
        """
        SELECT t.topic, t.topic_label, count(DISTINCT dt.registrant_doc_id) AS document_count
        FROM document_topics dt
        JOIN topics t ON t.topic = dt.topic
        JOIN registrant_docs rd ON rd.registrant_doc_id = dt.registrant_doc_id
        JOIN foreign_principals fp ON fp.registrant_id = rd.registrant_id
        WHERE fp.jurisdiction = %(j)s AND fp.country_raw = %(country)s
        GROUP BY t.topic, t.topic_label, t.sort_order
        ORDER BY document_count DESC, t.sort_order
        """,
        {"j": jurisdiction, "country": country_name},
    ).fetchall()
    return [TopicCount(**r) for r in rows]


@router.get("/{country_name}/graph", response_model=CountryGraph)
def get_country_graph(
    country_name: str, jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)
) -> CountryGraph:
    return build_country_graph(conn, jurisdiction, country_name)


@router.get("/{country_name}/graph/registrants/{registrant_id}/expand", response_model=RegistrantExpansion)
def expand_registrant(
    country_name: str, registrant_id: int, jurisdiction: str = Query("fara"),
    conn: psycopg.Connection = Depends(get_db),
) -> RegistrantExpansion:
    owned = conn.execute(
        "SELECT 1 FROM foreign_principals WHERE jurisdiction = %s AND country_raw = %s AND registrant_id = %s",
        (jurisdiction, country_name, registrant_id),
    ).fetchone()
    if owned is None:
        raise HTTPException(status_code=404, detail="registrant not found for this country")
    return build_registrant_expansion(conn, registrant_id)


@router.get("/{country_name}/top-contacts", response_model=list[TopContact])
def get_top_contacts(
    country_name: str, jurisdiction: str = Query("fara"), limit: int = Query(25, ge=1, le=100),
    conn: psycopg.Connection = Depends(get_db),
) -> list[TopContact]:
    return top_contacts(conn, jurisdiction, country_name, limit)


@router.get("/{country_name}/top-recipients", response_model=list[TopRecipient])
def get_top_recipients(
    country_name: str, jurisdiction: str = Query("fara"), limit: int = Query(25, ge=1, le=100),
    conn: psycopg.Connection = Depends(get_db),
) -> list[TopRecipient]:
    return top_recipients(conn, jurisdiction, country_name, limit)
