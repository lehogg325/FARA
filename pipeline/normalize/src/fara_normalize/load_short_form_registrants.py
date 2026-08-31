from __future__ import annotations

from dataclasses import dataclass

import psycopg

from fara_normalize.csv_readers import clean_str, is_malformed_row, parse_mmddyyyy, row_hash
from fara_normalize.registrant_lookup import load_registrant_id_map

JURISDICTION = "fara"

_SELECT_EXISTING_SQL = """
SELECT source_row_hash FROM short_form_registrants
WHERE jurisdiction = %(jurisdiction)s AND parent_registration_number = %(parent_registration_number)s
  AND last_name IS NOT DISTINCT FROM %(last_name)s AND first_name IS NOT DISTINCT FROM %(first_name)s
  AND short_form_date IS NOT DISTINCT FROM %(short_form_date)s
"""

_INSERT_SQL = """
INSERT INTO short_form_registrants (
    jurisdiction, parent_registrant_id, parent_registration_number, last_name, first_name,
    short_form_date, termination_date, source_row_hash, first_seen_snapshot_date, last_seen_snapshot_date
) VALUES (
    %(jurisdiction)s, %(parent_registrant_id)s, %(parent_registration_number)s, %(last_name)s, %(first_name)s,
    %(short_form_date)s, %(termination_date)s, %(source_row_hash)s, %(snapshot_date)s, %(snapshot_date)s
)
"""

_UPDATE_CHANGED_SQL = """
UPDATE short_form_registrants SET
    termination_date = %(termination_date)s, source_row_hash = %(source_row_hash)s,
    last_seen_snapshot_date = %(snapshot_date)s, updated_at = now()
WHERE jurisdiction = %(jurisdiction)s AND parent_registration_number = %(parent_registration_number)s
  AND last_name IS NOT DISTINCT FROM %(last_name)s AND first_name IS NOT DISTINCT FROM %(first_name)s
  AND short_form_date IS NOT DISTINCT FROM %(short_form_date)s
"""

_TOUCH_LAST_SEEN_SQL = """
UPDATE short_form_registrants SET last_seen_snapshot_date = %(snapshot_date)s
WHERE jurisdiction = %(jurisdiction)s AND parent_registration_number = %(parent_registration_number)s
  AND last_name IS NOT DISTINCT FROM %(last_name)s AND first_name IS NOT DISTINCT FROM %(first_name)s
  AND short_form_date IS NOT DISTINCT FROM %(short_form_date)s
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


def _parse_row(raw_row: dict[str, str], parent_registrant_id: int, snapshot_date: str) -> dict:
    return {
        "jurisdiction": JURISDICTION,
        "parent_registrant_id": parent_registrant_id,
        "parent_registration_number": int(clean_str(raw_row["Registration Number"])),
        "last_name": clean_str(raw_row.get("Short Form Last Name")),
        "first_name": clean_str(raw_row.get("Short Form First Name")),
        "short_form_date": parse_mmddyyyy(raw_row.get("Short Form Date")),
        "termination_date": parse_mmddyyyy(raw_row.get("Short Form Termination Date")),
        "source_row_hash": row_hash(raw_row),
        "snapshot_date": snapshot_date,
    }


def load_short_form_registrants(
    conn: psycopg.Connection, raw_rows: list[dict[str, str]], snapshot_date: str
) -> LoadResult:
    """Confirmed live: a handful of (registrant, name, short-form date) triples
    repeat with only Termination Date differing — same class of bug as
    registrant 5769 in the registrants file (docs/api-notes.md) — last row in
    the file wins, consistent with load_registrants.
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

    inserted = updated = unchanged = 0
    skipped_unmapped_registrant = 0

    with conn.cursor() as cur:
        for raw_row in deduped.values():
            registration_number = int(clean_str(raw_row["Registration Number"]))
            parent_registrant_id = registrant_id_map.get(registration_number)
            if parent_registrant_id is None:
                skipped_unmapped_registrant += 1
                continue

            params = _parse_row(raw_row, parent_registrant_id, snapshot_date)
            cur.execute(_SELECT_EXISTING_SQL, params)
            existing = cur.fetchone()

            if existing is None:
                cur.execute(_INSERT_SQL, params)
                inserted += 1
            elif existing[0] != params["source_row_hash"]:
                cur.execute(_UPDATE_CHANGED_SQL, params)
                updated += 1
            else:
                cur.execute(_TOUCH_LAST_SEEN_SQL, params)
                unchanged += 1

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
