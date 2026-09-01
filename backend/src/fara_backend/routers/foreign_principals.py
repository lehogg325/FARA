from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from fara_backend.db import get_db
from fara_backend.schemas import ForeignPrincipal, ForeignPrincipalByNameGroup, Page, RegistrantSummary

router = APIRouter(prefix="/foreign-principals", tags=["foreign-principals"])


_FP_SELECT = (
    "SELECT fp.*, r.name AS registrant_name, r.status AS registrant_status "
    "FROM foreign_principals fp JOIN registrants r ON r.registrant_id = fp.registrant_id"
)


@router.get("", response_model=Page[ForeignPrincipal])
def list_foreign_principals(
    jurisdiction: str = Query("fara"),
    country: str | None = None,
    q: str | None = None,
    status: str | None = Query(None, pattern="^(active|terminated)$"),
    sort: str = Query("registration_date_desc", pattern="^(registration_date_desc|name_asc|country_asc)$"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: psycopg.Connection = Depends(get_db),
) -> Page[ForeignPrincipal]:
    where = ["fp.jurisdiction = %(jurisdiction)s"]
    params: dict = {"jurisdiction": jurisdiction, "limit": limit, "offset": offset}
    if country:
        where.append("fp.country_raw = %(country)s")
        params["country"] = country
    if q:
        where.append("fp.foreign_principal_name ILIKE %(q)s")
        params["q"] = f"%{q}%"
    if status:
        where.append("r.status = %(status)s")
        params["status"] = status
    where_sql = " AND ".join(where)
    order_sql = {
        "registration_date_desc": "fp.registration_date DESC NULLS LAST",
        "name_asc": "fp.foreign_principal_name ASC",
        "country_asc": "fp.country_raw ASC NULLS LAST, fp.foreign_principal_name ASC",
    }[sort]

    total = conn.execute(
        f"SELECT count(*) AS n FROM foreign_principals fp JOIN registrants r ON r.registrant_id = fp.registrant_id "
        f"WHERE {where_sql}",
        params,
    ).fetchone()["n"]
    rows = conn.execute(
        f"{_FP_SELECT} WHERE {where_sql} ORDER BY {order_sql} LIMIT %(limit)s OFFSET %(offset)s",
        params,
    ).fetchall()
    return Page(items=[ForeignPrincipal(**r) for r in rows], total=total, limit=limit, offset=offset)


# Registered ahead of /{foreign_principal_id} — otherwise FastAPI would try to
# parse the literal path segment "by-name" as that route's int path param.
@router.get("/by-name", response_model=list[ForeignPrincipalByNameGroup])
def foreign_principals_by_name(
    name: str,
    country: str | None = None,
    jurisdiction: str = Query("fara"),
    conn: psycopg.Connection = Depends(get_db),
) -> list[ForeignPrincipalByNameGroup]:
    where = ["jurisdiction = %(jurisdiction)s", "foreign_principal_name ILIKE %(name)s"]
    params: dict = {"jurisdiction": jurisdiction, "name": name}
    if country:
        where.append("country_raw = %(country)s")
        params["country"] = country
    where_sql = " AND ".join(where)

    groups = conn.execute(
        f"SELECT foreign_principal_name, country_raw, array_agg(DISTINCT registrant_id) AS registrant_ids "
        f"FROM foreign_principals WHERE {where_sql} GROUP BY foreign_principal_name, country_raw",
        params,
    ).fetchall()

    result = []
    for g in groups:
        registrants = conn.execute(
            "SELECT * FROM registrants WHERE registrant_id = ANY(%s) ORDER BY name", (g["registrant_ids"],)
        ).fetchall()
        result.append(
            ForeignPrincipalByNameGroup(
                foreign_principal_name=g["foreign_principal_name"],
                country_raw=g["country_raw"],
                registrant_count=len(registrants),
                registrants=[RegistrantSummary(**r) for r in registrants],
            )
        )
    return result


@router.get("/{foreign_principal_id}", response_model=ForeignPrincipal)
def get_foreign_principal(
    foreign_principal_id: int, jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)
) -> ForeignPrincipal:
    row = conn.execute(
        f"{_FP_SELECT} WHERE fp.jurisdiction = %s AND fp.foreign_principal_id = %s",
        (jurisdiction, foreign_principal_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="foreign principal not found")
    return ForeignPrincipal(**row)
