from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from fara_backend.db import get_db
from fara_backend.schemas import ForeignPrincipal, Page, RegistrantDetail, RegistrantDoc, RegistrantSummary, ShortFormRegistrant

router = APIRouter(prefix="/registrants", tags=["registrants"])


def _get_registrant_or_404(conn: psycopg.Connection, jurisdiction: str, registrant_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM registrants WHERE jurisdiction = %s AND registrant_id = %s", (jurisdiction, registrant_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="registrant not found")
    return row


@router.get("", response_model=Page[RegistrantSummary])
def list_registrants(
    jurisdiction: str = Query("fara"),
    status: str | None = Query(None, pattern="^(active|terminated)$"),
    state: str | None = None,
    q: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: psycopg.Connection = Depends(get_db),
) -> Page[RegistrantSummary]:
    where = ["jurisdiction = %(jurisdiction)s"]
    params: dict = {"jurisdiction": jurisdiction, "limit": limit, "offset": offset}
    if status:
        where.append("status = %(status)s")
        params["status"] = status
    if state:
        where.append("state = %(state)s")
        params["state"] = state
    if q:
        where.append("name ILIKE %(q)s")
        params["q"] = f"%{q}%"
    where_sql = " AND ".join(where)

    total = conn.execute(f"SELECT count(*) AS n FROM registrants WHERE {where_sql}", params).fetchone()["n"]
    rows = conn.execute(
        f"SELECT * FROM registrants WHERE {where_sql} ORDER BY name LIMIT %(limit)s OFFSET %(offset)s", params
    ).fetchall()
    return Page(items=[RegistrantSummary(**r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{registrant_id}", response_model=RegistrantDetail)
def get_registrant(
    registrant_id: int, jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)
) -> RegistrantDetail:
    row = _get_registrant_or_404(conn, jurisdiction, registrant_id)
    counts = conn.execute(
        """
        SELECT
            (SELECT count(*) FROM foreign_principals WHERE registrant_id = %(id)s) AS foreign_principal_count,
            (SELECT count(*) FROM short_form_registrants WHERE parent_registrant_id = %(id)s) AS short_form_registrant_count,
            (SELECT count(*) FROM registrant_docs WHERE registrant_id = %(id)s) AS document_count
        """,
        {"id": registrant_id},
    ).fetchone()
    return RegistrantDetail(**row, **counts)


@router.get("/{registrant_id}/foreign-principals", response_model=Page[ForeignPrincipal])
def get_registrant_foreign_principals(
    registrant_id: int,
    jurisdiction: str = Query("fara"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: psycopg.Connection = Depends(get_db),
) -> Page[ForeignPrincipal]:
    _get_registrant_or_404(conn, jurisdiction, registrant_id)
    total = conn.execute(
        "SELECT count(*) AS n FROM foreign_principals WHERE registrant_id = %s", (registrant_id,)
    ).fetchone()["n"]
    rows = conn.execute(
        "SELECT fp.*, r.name AS registrant_name, r.status AS registrant_status "
        "FROM foreign_principals fp JOIN registrants r ON r.registrant_id = fp.registrant_id "
        "WHERE fp.registrant_id = %s "
        "ORDER BY fp.registration_date DESC NULLS LAST LIMIT %s OFFSET %s",
        (registrant_id, limit, offset),
    ).fetchall()
    return Page(items=[ForeignPrincipal(**r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{registrant_id}/short-form-registrants", response_model=Page[ShortFormRegistrant])
def get_registrant_short_forms(
    registrant_id: int,
    jurisdiction: str = Query("fara"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: psycopg.Connection = Depends(get_db),
) -> Page[ShortFormRegistrant]:
    _get_registrant_or_404(conn, jurisdiction, registrant_id)
    total = conn.execute(
        "SELECT count(*) AS n FROM short_form_registrants WHERE parent_registrant_id = %s", (registrant_id,)
    ).fetchone()["n"]
    rows = conn.execute(
        "SELECT * FROM short_form_registrants WHERE parent_registrant_id = %s "
        "ORDER BY short_form_date DESC NULLS LAST LIMIT %s OFFSET %s",
        (registrant_id, limit, offset),
    ).fetchall()
    return Page(items=[ShortFormRegistrant(**r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{registrant_id}/documents", response_model=Page[RegistrantDoc])
def get_registrant_documents(
    registrant_id: int,
    jurisdiction: str = Query("fara"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: psycopg.Connection = Depends(get_db),
) -> Page[RegistrantDoc]:
    _get_registrant_or_404(conn, jurisdiction, registrant_id)
    total = conn.execute(
        "SELECT count(*) AS n FROM registrant_docs WHERE registrant_id = %s", (registrant_id,)
    ).fetchone()["n"]
    rows = conn.execute(
        "SELECT * FROM registrant_docs WHERE registrant_id = %s "
        "ORDER BY date_stamped DESC NULLS LAST LIMIT %s OFFSET %s",
        (registrant_id, limit, offset),
    ).fetchall()
    return Page(items=[RegistrantDoc(**r) for r in rows], total=total, limit=limit, offset=offset)
