from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, Query

from fara_backend.db import get_db
from fara_backend.schemas import SearchResult

router = APIRouter(tags=["search"])

_VALID_TYPES = {"registrant", "foreign_principal", "short_form_registrant"}

_SUBQUERIES = {
    "registrant": """
        SELECT 'registrant' AS entity_type, registrant_id AS entity_id, name AS label,
               business_name AS detail, registration_number
        FROM registrants
        WHERE jurisdiction = %(jurisdiction)s AND name ILIKE %(q)s
        ORDER BY name LIMIT %(limit)s
    """,
    "foreign_principal": """
        SELECT 'foreign_principal' AS entity_type, foreign_principal_id AS entity_id, foreign_principal_name AS label,
               country_raw AS detail, registration_number
        FROM foreign_principals
        WHERE jurisdiction = %(jurisdiction)s AND foreign_principal_name ILIKE %(q)s
        ORDER BY foreign_principal_name LIMIT %(limit)s
    """,
    "short_form_registrant": """
        SELECT 'short_form_registrant' AS entity_type, short_form_registrant_id AS entity_id,
               trim(coalesce(first_name, '') || ' ' || coalesce(last_name, '')) AS label,
               NULL AS detail, parent_registration_number AS registration_number
        FROM short_form_registrants
        WHERE jurisdiction = %(jurisdiction)s AND (first_name ILIKE %(q)s OR last_name ILIKE %(q)s)
        ORDER BY last_name LIMIT %(limit)s
    """,
}


@router.get("/search", response_model=list[SearchResult])
def search(
    q: str,
    type: str | None = Query(None, alias="type"),
    jurisdiction: str = Query("fara"),
    limit: int = Query(10, ge=1, le=50),
    conn: psycopg.Connection = Depends(get_db),
) -> list[SearchResult]:
    entity_types = [type] if type in _VALID_TYPES else list(_SUBQUERIES)
    params = {"jurisdiction": jurisdiction, "q": f"%{q}%", "limit": limit}

    results: list[SearchResult] = []
    for entity_type in entity_types:
        rows = conn.execute(_SUBQUERIES[entity_type], params).fetchall()
        results.extend(SearchResult(**r) for r in rows)
    return results[:limit]
