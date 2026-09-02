from __future__ import annotations

from dataclasses import dataclass

import psycopg

from fara_normalize.csv_readers import clean_str, is_malformed_row, normalize_zip, parse_mmddyyyy, row_hash
from fara_normalize.load_dimensions import register_observed_country
from fara_normalize.registrant_lookup import load_registrant_id_map

JURISDICTION = "fara"

_STAGING_COLUMNS = (
    "jurisdiction",
    "registrant_id",
    "registration_number",
    "foreign_principal_name",
    "country_raw",
    "address_1",
    "address_2",
    "city",
    "state",
    "zip",
    "registration_date",
    "termination_date",
    "source_row_hash",
)

_NATURAL_KEY_JOIN = """
    fp.jurisdiction = s.jurisdiction AND fp.registration_number = s.registration_number
    AND fp.foreign_principal_name = s.foreign_principal_name
    AND fp.country_raw IS NOT DISTINCT FROM s.country_raw
    AND fp.registration_date IS NOT DISTINCT FROM s.registration_date
"""

_INSERT_MISSING_SQL = f"""
INSERT INTO foreign_principals (
    jurisdiction, registrant_id, registration_number, foreign_principal_name, country_raw,
    address_1, address_2, city, state, zip, registration_date, termination_date,
    source_row_hash, first_seen_snapshot_date, last_seen_snapshot_date
)
SELECT s.jurisdiction, s.registrant_id, s.registration_number, s.foreign_principal_name, s.country_raw,
       s.address_1, s.address_2, s.city, s.state, s.zip, s.registration_date, s.termination_date,
       s.source_row_hash, %(snapshot_date)s, %(snapshot_date)s
FROM stg_foreign_principals s
WHERE NOT EXISTS (SELECT 1 FROM foreign_principals fp WHERE {_NATURAL_KEY_JOIN})
"""

_UPDATE_CHANGED_SQL = f"""
UPDATE foreign_principals fp SET
    address_1 = s.address_1, address_2 = s.address_2, city = s.city, state = s.state, zip = s.zip,
    termination_date = s.termination_date, source_row_hash = s.source_row_hash,
    last_seen_snapshot_date = %(snapshot_date)s, updated_at = now()
FROM stg_foreign_principals s
WHERE {_NATURAL_KEY_JOIN} AND fp.source_row_hash IS DISTINCT FROM s.source_row_hash
"""

# Must run before _UPDATE_CHANGED_SQL and _INSERT_MISSING_SQL — see the
# ordering comment where these statements are executed, below.
_TOUCH_UNCHANGED_SQL = f"""
UPDATE foreign_principals fp SET last_seen_snapshot_date = %(snapshot_date)s
FROM stg_foreign_principals s
WHERE {_NATURAL_KEY_JOIN} AND fp.source_row_hash = s.source_row_hash
"""

_MISSING_FROM_SNAPSHOT_SQL = """
SELECT count(*) FROM foreign_principals
WHERE jurisdiction = %(jurisdiction)s AND last_seen_snapshot_date < %(snapshot_date)s
"""


@dataclass
class LoadResult:
    total_rows: int
    inserted: int
    updated: int
    unchanged: int
    missing_from_snapshot: int
    duplicate_rows_collapsed: int = 0
    skipped_unparseable: int = 0
    skipped_unmapped_registrant: int = 0


def _natural_key(raw_row: dict[str, str]) -> tuple:
    return (
        raw_row["Registration Number"],
        clean_str(raw_row.get("Foreign Principal")),
        clean_str(raw_row.get("Country/Location Represented")),
        clean_str(raw_row.get("Foreign Principal Registration Date")),
    )


def _parse_row(raw_row: dict[str, str], registrant_id: int) -> dict:
    return {
        "jurisdiction": JURISDICTION,
        "registrant_id": registrant_id,
        "registration_number": int(clean_str(raw_row["Registration Number"])),
        "foreign_principal_name": clean_str(raw_row.get("Foreign Principal")),
        "country_raw": clean_str(raw_row.get("Country/Location Represented")),
        "address_1": clean_str(raw_row.get("Address 1")),
        "address_2": clean_str(raw_row.get("Address 2")),
        "city": clean_str(raw_row.get("City")),
        "state": clean_str(raw_row.get("State")),
        "zip": normalize_zip(raw_row.get("Zip")),
        "registration_date": parse_mmddyyyy(raw_row.get("Foreign Principal Registration Date")),
        "termination_date": parse_mmddyyyy(raw_row.get("Foreign Principal Termination Date")),
        "source_row_hash": row_hash(raw_row),
    }


def load_foreign_principals(
    conn: psycopg.Connection, raw_rows: list[dict[str, str]], snapshot_date: str
) -> LoadResult:
    """Confirmed live (docs/api-notes.md): ~9 of 17,739 rows have an unescaped
    double quote inside the Foreign Principal name that shifts every subsequent
    CSV column, leaving Registration Number non-numeric. These are skipped and
    counted — the source row is unrecoverable, not a bug in this parser.
    Country is stored as free text and auto-registered into the countries
    reference table, never FK-enforced (confirmed real anomalies rule out a
    closed vocabulary here).

    Bulk-loaded via a staging table + 3 set-based statements, not a per-row
    SELECT-then-INSERT/UPDATE loop — confirmed live against Supabase's session
    pooler (2026-09-02, docs/deploy.md): the per-row version took 8m23s for
    17,745 rows, ~35 rows/sec, round-trip latency dominated over query cost
    exactly like registrant_docs did before it got the same fix (0003).
    Country registration stays a small per-distinct-value loop (a few hundred
    round trips at most, not one per row — never the bottleneck).
    """
    registrant_id_map = load_registrant_id_map(conn, JURISDICTION)
    known_countries: set[str | None] = set()

    deduped: dict[tuple, dict[str, str]] = {}
    duplicate_count = 0
    skipped_unparseable = 0

    for raw_row in raw_rows:
        reg_num_raw = clean_str(raw_row.get("Registration Number"))
        # Confirmed live: 14 malformed rows, only 9 of which have a non-numeric
        # Registration Number — the other 5 still "look" valid there while
        # other columns are shifted, so is_malformed_row is checked too.
        if reg_num_raw is None or not reg_num_raw.isdigit() or is_malformed_row(raw_row):
            skipped_unparseable += 1
            continue
        key = _natural_key(raw_row)
        if key in deduped:
            duplicate_count += 1
        deduped[key] = raw_row

    skipped_unmapped_registrant = 0
    staged_rows: list[dict] = []

    for raw_row in deduped.values():
        registration_number = int(clean_str(raw_row["Registration Number"]))
        registrant_id = registrant_id_map.get(registration_number)
        if registrant_id is None:
            skipped_unmapped_registrant += 1
            continue

        params = _parse_row(raw_row, registrant_id)
        if params["country_raw"] not in known_countries:
            register_observed_country(conn, JURISDICTION, params["country_raw"])
            known_countries.add(params["country_raw"])

        staged_rows.append(params)

    with conn.cursor() as cur:
        cur.execute("TRUNCATE stg_foreign_principals")
        with cur.copy(f"COPY stg_foreign_principals ({', '.join(_STAGING_COLUMNS)}) FROM STDIN") as copy:
            for params in staged_rows:
                copy.write_row(tuple(params[col] for col in _STAGING_COLUMNS))

        # Order matters, for two reasons: (1) _TOUCH_UNCHANGED_SQL must run
        # before _UPDATE_CHANGED_SQL — that statement also overwrites
        # source_row_hash to match the staging row, which would make a
        # just-updated row trivially match _TOUCH_UNCHANGED_SQL's
        # hash-equality condition too if it ran second, double-counting every
        # update as "unchanged" as well (confirmed live, 2026-09-02). (2) both
        # must run before _INSERT_MISSING_SQL creates new rows with
        # trivially-self-matching hashes.
        cur.execute(_TOUCH_UNCHANGED_SQL, {"snapshot_date": snapshot_date})
        unchanged = cur.rowcount
        cur.execute(_UPDATE_CHANGED_SQL, {"snapshot_date": snapshot_date})
        updated = cur.rowcount
        cur.execute(_INSERT_MISSING_SQL, {"snapshot_date": snapshot_date})
        inserted = cur.rowcount

        cur.execute("TRUNCATE stg_foreign_principals")
        cur.execute(_MISSING_FROM_SNAPSHOT_SQL, {"jurisdiction": JURISDICTION, "snapshot_date": snapshot_date})
        missing = cur.fetchone()[0]

    return LoadResult(
        total_rows=len(raw_rows),
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        missing_from_snapshot=missing,
        duplicate_rows_collapsed=duplicate_count,
        skipped_unparseable=skipped_unparseable,
        skipped_unmapped_registrant=skipped_unmapped_registrant,
    )
