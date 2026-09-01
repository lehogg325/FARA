from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from fara_backend.db import get_db
from fara_backend.schemas import (
    ForeignPrincipal,
    ForeignPrincipalByNameGroup,
    ForeignPrincipalGrouped,
    Page,
    RegistrantSummary,
)
from fara_backend.text_normalize import NORM_SQL

router = APIRouter(prefix="/foreign-principals", tags=["foreign-principals"])


_FP_SELECT = (
    "SELECT fp.*, r.name AS registrant_name, r.status AS registrant_status "
    "FROM foreign_principals fp JOIN registrants r ON r.registrant_id = fp.registrant_id"
)

_NORM_NAME = NORM_SQL.format(col="fp.foreign_principal_name")
_NORM_COUNTRY = NORM_SQL.format(col="coalesce(fp.country_raw, '')")

_GROUPED_ORDER_SQL = {
    "registration_date_desc": "max(fp.registration_date) DESC NULLS LAST",
    "name_asc": "min(fp.foreign_principal_name) ASC",
    "country_asc": "min(fp.country_raw) ASC NULLS LAST, min(fp.foreign_principal_name) ASC",
}
_RAW_ORDER_SQL = {
    "registration_date_desc": "fp.registration_date DESC NULLS LAST",
    "name_asc": "fp.foreign_principal_name ASC",
    "country_asc": "fp.country_raw ASC NULLS LAST, fp.foreign_principal_name ASC",
}


@router.get("", response_model=None)
def list_foreign_principals(
    jurisdiction: str = Query("fara"),
    country: str | None = None,
    q: str | None = None,
    status: str | None = Query(None, pattern="^(active|terminated)$"),
    sort: str = Query("registration_date_desc", pattern="^(registration_date_desc|name_asc|country_asc)$"),
    group_by_name: bool = Query(True),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: psycopg.Connection = Depends(get_db),
) -> Page[ForeignPrincipal] | Page[ForeignPrincipalGrouped]:
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

    if not group_by_name:
        rows = conn.execute(
            f"{_FP_SELECT} WHERE {where_sql} ORDER BY {_RAW_ORDER_SQL[sort]} LIMIT %(limit)s OFFSET %(offset)s",
            params,
        ).fetchall()
        total = conn.execute(
            f"SELECT count(*) AS n FROM foreign_principals fp JOIN registrants r ON r.registrant_id = fp.registrant_id "
            f"WHERE {where_sql}",
            params,
        ).fetchone()["n"]
        return Page(items=[ForeignPrincipal(**r) for r in rows], total=total, limit=limit, offset=offset)

    # Grouped mode (default): one row per normalized (name, country) pair, so a
    # principal reported by many registrants shows once with a registrant_count
    # instead of flooding the list with one row per registrant relationship.
    total = conn.execute(
        f"SELECT count(*) AS n FROM (SELECT 1 FROM foreign_principals fp "
        f"JOIN registrants r ON r.registrant_id = fp.registrant_id WHERE {where_sql} "
        f"GROUP BY {_NORM_NAME}, {_NORM_COUNTRY}) t",
        params,
    ).fetchone()["n"]
    rows = conn.execute(
        f"""
        SELECT (array_agg(fp.foreign_principal_name ORDER BY fp.registration_date DESC NULLS LAST))[1] AS foreign_principal_name,
               (array_agg(fp.country_raw ORDER BY fp.registration_date DESC NULLS LAST))[1] AS country_raw,
               count(DISTINCT fp.registrant_id) AS registrant_count,
               (array_agg(DISTINCT r.name))[1:3] AS sample_registrant_names,
               max(fp.registration_date) AS latest_registration_date
        FROM foreign_principals fp JOIN registrants r ON r.registrant_id = fp.registrant_id
        WHERE {where_sql}
        GROUP BY {_NORM_NAME}, {_NORM_COUNTRY}
        ORDER BY {_GROUPED_ORDER_SQL[sort]}
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    ).fetchall()
    return Page(items=[ForeignPrincipalGrouped(**r) for r in rows], total=total, limit=limit, offset=offset)


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
    norm_name = NORM_SQL.format(col="foreign_principal_name")
    norm_country = NORM_SQL.format(col="coalesce(country_raw, '')")

    groups = conn.execute(
        f"SELECT (array_agg(foreign_principal_name))[1] AS foreign_principal_name, "
        f"(array_agg(country_raw))[1] AS country_raw, "
        f"array_agg(DISTINCT registrant_id) AS registrant_ids "
        f"FROM foreign_principals WHERE {where_sql} "
        f"GROUP BY {norm_name}, {norm_country}",
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
