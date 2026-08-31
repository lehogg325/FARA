from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from fara_backend.db import get_db
from fara_backend.schemas import DocumentSearchResult, DocumentText, ExtractedField, Page, RegistrantDoc

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_doc_or_404(conn: psycopg.Connection, jurisdiction: str, registrant_doc_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM registrant_docs WHERE jurisdiction = %s AND registrant_doc_id = %s",
        (jurisdiction, registrant_doc_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    return row


@router.get("", response_model=Page[RegistrantDoc])
def list_documents(
    jurisdiction: str = Query("fara"),
    document_type: str | None = None,
    registrant_id: int | None = None,
    country: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: psycopg.Connection = Depends(get_db),
) -> Page[RegistrantDoc]:
    where = ["jurisdiction = %(jurisdiction)s"]
    params: dict = {"jurisdiction": jurisdiction, "limit": limit, "offset": offset}
    if document_type:
        where.append("document_type_code = %(document_type)s")
        params["document_type"] = document_type
    if registrant_id:
        where.append("registrant_id = %(registrant_id)s")
        params["registrant_id"] = registrant_id
    if country:
        where.append("foreign_principal_country_raw = %(country)s")
        params["country"] = country
    if date_from:
        where.append("date_stamped >= %(date_from)s")
        params["date_from"] = date_from
    if date_to:
        where.append("date_stamped <= %(date_to)s")
        params["date_to"] = date_to
    where_sql = " AND ".join(where)

    total = conn.execute(f"SELECT count(*) AS n FROM registrant_docs WHERE {where_sql}", params).fetchone()["n"]
    rows = conn.execute(
        f"SELECT * FROM registrant_docs WHERE {where_sql} "
        "ORDER BY date_stamped DESC NULLS LAST LIMIT %(limit)s OFFSET %(offset)s",
        params,
    ).fetchall()
    return Page(items=[RegistrantDoc(**r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/search", response_model=Page[DocumentSearchResult])
def search_documents(
    q: str,
    jurisdiction: str = Query("fara"),
    document_type: str | None = None,
    registrant_id: int | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: psycopg.Connection = Depends(get_db),
) -> Page[DocumentSearchResult]:
    where = ["rd.jurisdiction = %(jurisdiction)s", "dt.text_search @@ plainto_tsquery('english', %(q)s)"]
    params: dict = {"jurisdiction": jurisdiction, "q": q, "limit": limit, "offset": offset}
    if document_type:
        where.append("rd.document_type_code = %(document_type)s")
        params["document_type"] = document_type
    if registrant_id:
        where.append("rd.registrant_id = %(registrant_id)s")
        params["registrant_id"] = registrant_id
    where_sql = " AND ".join(where)

    total = conn.execute(
        f"SELECT count(*) AS n FROM document_text dt JOIN registrant_docs rd "
        f"ON rd.registrant_doc_id = dt.registrant_doc_id WHERE {where_sql}",
        params,
    ).fetchone()["n"]
    rows = conn.execute(
        f"""
        SELECT rd.registrant_doc_id, rd.registration_number, rd.document_type_raw_label, rd.date_stamped,
               ts_headline('english', dt.extracted_text, plainto_tsquery('english', %(q)s),
                           'MaxFragments=1, MaxWords=40, MinWords=15') AS snippet
        FROM document_text dt
        JOIN registrant_docs rd ON rd.registrant_doc_id = dt.registrant_doc_id
        WHERE {where_sql}
        ORDER BY ts_rank(dt.text_search, plainto_tsquery('english', %(q)s)) DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    ).fetchall()
    return Page(items=[DocumentSearchResult(**r) for r in rows], total=total, limit=limit, offset=offset)


# Registered ahead of /{registrant_doc_id}/text and /fields is unnecessary (those
# have an extra path segment), but this bare route must still come after /search
# above — otherwise FastAPI would try to parse "search" as this route's int param.
@router.get("/{registrant_doc_id}", response_model=RegistrantDoc)
def get_document(
    registrant_doc_id: int, jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)
) -> RegistrantDoc:
    return RegistrantDoc(**_get_doc_or_404(conn, jurisdiction, registrant_doc_id))


@router.get("/{registrant_doc_id}/text", response_model=DocumentText)
def get_document_text(
    registrant_doc_id: int, jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)
) -> DocumentText:
    _get_doc_or_404(conn, jurisdiction, registrant_doc_id)
    row = conn.execute(
        "SELECT * FROM document_text WHERE registrant_doc_id = %s", (registrant_doc_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no extracted text for this document")
    return DocumentText(**row)


@router.get("/{registrant_doc_id}/fields", response_model=list[ExtractedField])
def get_document_fields(
    registrant_doc_id: int, jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)
) -> list[ExtractedField]:
    _get_doc_or_404(conn, jurisdiction, registrant_doc_id)
    rows = conn.execute(
        "SELECT * FROM document_extracted_fields WHERE registrant_doc_id = %s ORDER BY field_key",
        (registrant_doc_id,),
    ).fetchall()
    return [ExtractedField(**r) for r in rows]
