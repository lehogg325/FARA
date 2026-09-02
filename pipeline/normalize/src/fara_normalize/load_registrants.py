from __future__ import annotations

from dataclasses import dataclass

import psycopg

from fara_normalize.csv_readers import clean_str, is_malformed_row, normalize_zip, parse_mmddyyyy, row_hash

JURISDICTION = "fara"

_STAGING_COLUMNS = (
    "jurisdiction",
    "registration_number",
    "name",
    "business_name",
    "address_1",
    "address_2",
    "city",
    "state",
    "zip",
    "registration_date",
    "termination_date",
    "status",
    "source_row_hash",
)

_NATURAL_KEY_JOIN = "r.jurisdiction = s.jurisdiction AND r.registration_number = s.registration_number"

_INSERT_MISSING_SQL = f"""
INSERT INTO registrants (
    jurisdiction, registration_number, name, business_name,
    address_1, address_2, city, state, zip,
    registration_date, termination_date, status,
    source_row_hash, first_seen_snapshot_date, last_seen_snapshot_date
)
SELECT s.jurisdiction, s.registration_number, s.name, s.business_name,
       s.address_1, s.address_2, s.city, s.state, s.zip,
       s.registration_date, s.termination_date, s.status,
       s.source_row_hash, %(snapshot_date)s, %(snapshot_date)s
FROM stg_registrants s
WHERE NOT EXISTS (SELECT 1 FROM registrants r WHERE {_NATURAL_KEY_JOIN})
"""

_UPDATE_CHANGED_SQL = f"""
UPDATE registrants r SET
    name = s.name, business_name = s.business_name,
    address_1 = s.address_1, address_2 = s.address_2, city = s.city, state = s.state, zip = s.zip,
    registration_date = s.registration_date, termination_date = s.termination_date, status = s.status,
    source_row_hash = s.source_row_hash, last_seen_snapshot_date = %(snapshot_date)s, updated_at = now()
FROM stg_registrants s
WHERE {_NATURAL_KEY_JOIN} AND r.source_row_hash IS DISTINCT FROM s.source_row_hash
"""

# Must run before _UPDATE_CHANGED_SQL and _INSERT_MISSING_SQL — see the
# ordering comment where these statements are executed, below.
_TOUCH_UNCHANGED_SQL = f"""
UPDATE registrants r SET last_seen_snapshot_date = %(snapshot_date)s
FROM stg_registrants s
WHERE {_NATURAL_KEY_JOIN} AND r.source_row_hash = s.source_row_hash
"""

_MISSING_FROM_SNAPSHOT_SQL = """
SELECT count(*) FROM registrants
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


def _parse_row(raw_row: dict[str, str]) -> dict:
    termination_date = parse_mmddyyyy(raw_row.get("Termination Date"))
    return {
        "jurisdiction": JURISDICTION,
        "registration_number": int(clean_str(raw_row["Registration Number"])),
        "name": clean_str(raw_row.get("Name")),
        "business_name": clean_str(raw_row.get("Business Name")),
        "address_1": clean_str(raw_row.get("Address 1")),
        "address_2": clean_str(raw_row.get("Address 2")),
        "city": clean_str(raw_row.get("City")),
        "state": clean_str(raw_row.get("State")),
        "zip": normalize_zip(raw_row.get("Zip")),
        "registration_date": parse_mmddyyyy(raw_row.get("Registration Date")),
        "termination_date": termination_date,
        "status": "terminated" if termination_date else "active",
        "source_row_hash": row_hash(raw_row),
    }


def load_registrants(
    conn: psycopg.Connection, raw_rows: list[dict[str, str]], snapshot_date: str
) -> LoadResult:
    """Type-1 slowly-changing-dimension upsert (no amendment-lane resolution —
    see docs/api-notes.md: a Registration Number is one durable identity for a
    registrant's whole life). Rows missing from today's snapshot are never
    deleted, only flagged via missing_from_snapshot for human review — a
    registrant vanishing from the Active file should reappear in Terminated
    same/next day; if it disappears from both, that's a signal, not an error.

    Confirmed live (docs/api-notes.md): the real bulk file has had at least one
    Registration Number appear on two rows in the same snapshot with conflicting
    field values (reg 5769, differing only in Termination Date). Without
    deduplication, re-loading the same file would alternate between the two
    rows' values on every run instead of settling — so intra-file duplicates are
    collapsed up front, last occurrence in the file wins, consistent with the
    last-write-wins convention used everywhere else in this loader.

    Bulk-loaded via a staging table + 3 set-based statements, not a per-row
    SELECT-then-INSERT/UPDATE loop — confirmed live against Supabase's session
    pooler (2026-09-02, docs/deploy.md): the per-row version took 3m42s for
    7,079 rows, ~30 rows/sec, round-trip latency dominated over query cost
    exactly like registrant_docs did before it got the same fix (0003).
    """
    deduped: dict[int, dict[str, str]] = {}
    duplicate_count = 0
    skipped_unparseable = 0
    for raw_row in raw_rows:
        reg_num_raw = clean_str(raw_row.get("Registration Number"))
        if reg_num_raw is None or not reg_num_raw.isdigit() or is_malformed_row(raw_row):
            skipped_unparseable += 1
            continue
        regnum = int(reg_num_raw)
        if regnum in deduped:
            duplicate_count += 1
        deduped[regnum] = raw_row

    staged_rows = [_parse_row(raw_row) for raw_row in deduped.values()]

    with conn.cursor() as cur:
        cur.execute("TRUNCATE stg_registrants")
        with cur.copy(f"COPY stg_registrants ({', '.join(_STAGING_COLUMNS)}) FROM STDIN") as copy:
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

        cur.execute("TRUNCATE stg_registrants")
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
    )
