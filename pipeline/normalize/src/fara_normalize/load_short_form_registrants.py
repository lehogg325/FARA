from __future__ import annotations

from dataclasses import dataclass

import psycopg

from fara_normalize.csv_readers import clean_str, is_malformed_row, parse_mmddyyyy, row_hash
from fara_normalize.registrant_lookup import load_registrant_id_map

JURISDICTION = "fara"

_STAGING_COLUMNS = (
    "jurisdiction",
    "parent_registrant_id",
    "parent_registration_number",
    "last_name",
    "first_name",
    "short_form_date",
    "termination_date",
    "source_row_hash",
)

_NATURAL_KEY_JOIN = """
    sf.jurisdiction = s.jurisdiction AND sf.parent_registration_number = s.parent_registration_number
    AND sf.last_name IS NOT DISTINCT FROM s.last_name AND sf.first_name IS NOT DISTINCT FROM s.first_name
    AND sf.short_form_date IS NOT DISTINCT FROM s.short_form_date
"""

_INSERT_MISSING_SQL = f"""
INSERT INTO short_form_registrants (
    jurisdiction, parent_registrant_id, parent_registration_number, last_name, first_name,
    short_form_date, termination_date, source_row_hash, first_seen_snapshot_date, last_seen_snapshot_date
)
SELECT s.jurisdiction, s.parent_registrant_id, s.parent_registration_number, s.last_name, s.first_name,
       s.short_form_date, s.termination_date, s.source_row_hash, %(snapshot_date)s, %(snapshot_date)s
FROM stg_short_form_registrants s
WHERE NOT EXISTS (SELECT 1 FROM short_form_registrants sf WHERE {_NATURAL_KEY_JOIN})
"""

_UPDATE_CHANGED_SQL = f"""
UPDATE short_form_registrants sf SET
    termination_date = s.termination_date, source_row_hash = s.source_row_hash,
    last_seen_snapshot_date = %(snapshot_date)s, updated_at = now()
FROM stg_short_form_registrants s
WHERE {_NATURAL_KEY_JOIN} AND sf.source_row_hash IS DISTINCT FROM s.source_row_hash
"""

# Must run before _UPDATE_CHANGED_SQL and _INSERT_MISSING_SQL — see the
# ordering comment where these statements are executed, below.
_TOUCH_UNCHANGED_SQL = f"""
UPDATE short_form_registrants sf SET last_seen_snapshot_date = %(snapshot_date)s
FROM stg_short_form_registrants s
WHERE {_NATURAL_KEY_JOIN} AND sf.source_row_hash = s.source_row_hash
"""

_MISSING_FROM_SNAPSHOT_SQL = """
SELECT count(*) FROM short_form_registrants
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
        clean_str(raw_row.get("Short Form Last Name")),
        clean_str(raw_row.get("Short Form First Name")),
        clean_str(raw_row.get("Short Form Date")),
    )


def _parse_row(raw_row: dict[str, str], parent_registrant_id: int) -> dict:
    return {
        "jurisdiction": JURISDICTION,
        "parent_registrant_id": parent_registrant_id,
        "parent_registration_number": int(clean_str(raw_row["Registration Number"])),
        "last_name": clean_str(raw_row.get("Short Form Last Name")),
        "first_name": clean_str(raw_row.get("Short Form First Name")),
        "short_form_date": parse_mmddyyyy(raw_row.get("Short Form Date")),
        "termination_date": parse_mmddyyyy(raw_row.get("Short Form Termination Date")),
        "source_row_hash": row_hash(raw_row),
    }


def load_short_form_registrants(
    conn: psycopg.Connection, raw_rows: list[dict[str, str]], snapshot_date: str
) -> LoadResult:
    """Confirmed live: a handful of (registrant, name, short-form date) triples
    repeat with only Termination Date differing — same class of bug as
    registrant 5769 in the registrants file (docs/api-notes.md) — last row in
    the file wins, consistent with load_registrants.

    Bulk-loaded via a staging table + 3 set-based statements, not a per-row
    SELECT-then-INSERT/UPDATE loop — confirmed live against Supabase's session
    pooler (2026-09-02, docs/deploy.md): the per-row version didn't finish
    44,613 rows within the ingest-bulk workflow's total time budget at the
    ~30 rows/sec round-trip-latency-bound rate observed on the other datasets,
    the exact problem registrant_docs already hit and fixed (0003).
    """
    registrant_id_map = load_registrant_id_map(conn, JURISDICTION)

    deduped: dict[tuple, dict[str, str]] = {}
    duplicate_count = 0
    skipped_unparseable = 0
    for raw_row in raw_rows:
        if is_malformed_row(raw_row):
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
        parent_registrant_id = registrant_id_map.get(registration_number)
        if parent_registrant_id is None:
            skipped_unmapped_registrant += 1
            continue

        staged_rows.append(_parse_row(raw_row, parent_registrant_id))

    with conn.cursor() as cur:
        cur.execute("TRUNCATE stg_short_form_registrants")
        with cur.copy(f"COPY stg_short_form_registrants ({', '.join(_STAGING_COLUMNS)}) FROM STDIN") as copy:
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

        cur.execute("TRUNCATE stg_short_form_registrants")
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
