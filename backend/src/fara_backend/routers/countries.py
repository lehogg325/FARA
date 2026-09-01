from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from fara_backend.db import get_db
from fara_backend.graph import build_country_graph, build_registrant_expansion, top_contacts, top_recipients
from fara_backend.schemas import (
    Country,
    CountryDetail,
    CountryGraph,
    RegistrantExpansion,
    TopContact,
    TopicCount,
    TopRecipient,
)

router = APIRouter(prefix="/countries", tags=["countries"])


@router.get("", response_model=list[Country])
def list_countries(jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)) -> list[Country]:
    rows = conn.execute(
        """
        SELECT c.country_name,
               count(DISTINCT fp.registrant_id) AS registrant_count,
               count(DISTINCT fp.foreign_principal_id) AS foreign_principal_count
        FROM countries c
        LEFT JOIN foreign_principals fp ON fp.jurisdiction = c.jurisdiction AND fp.country_raw = c.country_name
        WHERE c.jurisdiction = %s
        GROUP BY c.country_name
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
