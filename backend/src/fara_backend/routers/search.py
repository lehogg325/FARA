from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, Query

from fara_backend.db import get_db
from fara_backend.schemas import SearchResult
from fara_backend.text_normalize import NORM_SQL

router = APIRouter(tags=["search"])

_VALID_TYPES = {"registrant", "foreign_principal", "short_form_registrant", "country"}

# Registrant and foreign_principal are grouped by normalized name (registrant)
# or normalized (name, country) (foreign_principal) so re-registrations and
# name-spelling variants collapse into one search hit with a group_count,
# instead of flooding the results with one row per raw record — the exact
# behavior a user pointed at directly ("Podesta Group, Inc." showing twice
# under different registration numbers; "Ballard Partners" showing twice for
# an active/terminated re-registration). country and short_form_registrant
# keep their existing one-row-per-record grain — a short-form filer is a
# distinct person, not a duplicate.
_SUBQUERIES = {
    "country": """
        SELECT 'country' AS entity_type, NULL AS entity_id, country_name AS label,
               NULL AS detail, NULL AS registration_number, NULL AS group_count, NULL AS active_count
        FROM countries
        WHERE jurisdiction = %(jurisdiction)s AND country_name ILIKE %(q)s
        ORDER BY country_name LIMIT %(limit)s
    """,
    "registrant": f"""
        SELECT 'registrant' AS entity_type,
               (array_agg(registrant_id ORDER BY registration_date DESC NULLS LAST))[1] AS entity_id,
               (array_agg(name ORDER BY registration_date DESC NULLS LAST))[1] AS label,
               NULL AS detail,
               (array_agg(registration_number ORDER BY registration_date DESC NULLS LAST))[1] AS registration_number,
               count(*) AS group_count,
               count(*) FILTER (WHERE status = 'active') AS active_count
        FROM registrants
        WHERE jurisdiction = %(jurisdiction)s AND name ILIKE %(q)s
        GROUP BY {NORM_SQL.format(col="name")}
        ORDER BY max(name) LIMIT %(limit)s
    """,
    "foreign_principal": f"""
        SELECT 'foreign_principal' AS entity_type,
               (array_agg(foreign_principal_id ORDER BY registration_date DESC NULLS LAST))[1] AS entity_id,
               (array_agg(foreign_principal_name ORDER BY registration_date DESC NULLS LAST))[1] AS label,
               (array_agg(country_raw ORDER BY registration_date DESC NULLS LAST))[1] AS detail,
               (array_agg(registration_number ORDER BY registration_date DESC NULLS LAST))[1] AS registration_number,
               count(DISTINCT registrant_id) AS group_count,
               NULL AS active_count
        FROM foreign_principals
        WHERE jurisdiction = %(jurisdiction)s AND foreign_principal_name ILIKE %(q)s
        GROUP BY {NORM_SQL.format(col="foreign_principal_name")}, {NORM_SQL.format(col="coalesce(country_raw, '')")}
        ORDER BY max(foreign_principal_name) LIMIT %(limit)s
    """,
    "short_form_registrant": """
        SELECT 'short_form_registrant' AS entity_type, short_form_registrant_id AS entity_id,
               trim(coalesce(first_name, '') || ' ' || coalesce(last_name, '')) AS label,
               NULL AS detail, parent_registration_number AS registration_number, NULL AS group_count, NULL AS active_count
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

    # A single type explicitly requested gets the full limit to itself, same as
    # before. Otherwise each type gets its own guaranteed sub-limit so a flood
    # of one type (e.g. registrants) can no longer push another type (e.g.
    # foreign principals) out of the results entirely.
    per_type_limit = limit if type else max(1, min(limit, 6))
    params = {"jurisdiction": jurisdiction, "q": f"%{q}%", "limit": per_type_limit}

    by_type: dict[str, list[SearchResult]] = {}
    for entity_type in entity_types:
        rows = conn.execute(_SUBQUERIES[entity_type], params).fetchall()
        by_type[entity_type] = [SearchResult(**r) for r in rows]

    if type:
        return by_type[type][:limit]

    # Round-robin merge across types so every type present gets a fair share
    # of the final list rather than being crowded out by concatenation order.
    results: list[SearchResult] = []
    i = 0
    while len(results) < limit and any(i < len(by_type[t]) for t in entity_types):
        for t in entity_types:
            if len(results) >= limit:
                break
            if i < len(by_type[t]):
                results.append(by_type[t][i])
        i += 1
    return results
