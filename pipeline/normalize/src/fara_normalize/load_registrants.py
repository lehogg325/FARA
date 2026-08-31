from __future__ import annotations

from dataclasses import dataclass

import psycopg

from fara_normalize.csv_readers import clean_str, is_malformed_row, normalize_zip, parse_mmddyyyy, row_hash

JURISDICTION = "fara"

_INSERT_SQL = """
INSERT INTO registrants (
    jurisdiction, registration_number, name, business_name,
    address_1, address_2, city, state, zip,
    registration_date, termination_date, status,
    source_row_hash, first_seen_snapshot_date, last_seen_snapshot_date
) VALUES (
    %(jurisdiction)s, %(registration_number)s, %(name)s, %(business_name)s,
    %(address_1)s, %(address_2)s, %(city)s, %(state)s, %(zip)s,
    %(registration_date)s, %(termination_date)s, %(status)s,
    %(source_row_hash)s, %(snapshot_date)s, %(snapshot_date)s
)
"""

_UPDATE_CHANGED_SQL = """
UPDATE registrants SET
    name = %(name)s, business_name = %(business_name)s,
    address_1 = %(address_1)s, address_2 = %(address_2)s,
    city = %(city)s, state = %(state)s, zip = %(zip)s,
    registration_date = %(registration_date)s, termination_date = %(termination_date)s,
    status = %(status)s, source_row_hash = %(source_row_hash)s,
    last_seen_snapshot_date = %(snapshot_date)s, updated_at = now()
WHERE jurisdiction = %(jurisdiction)s AND registration_number = %(registration_number)s
"""

_TOUCH_LAST_SEEN_SQL = """
UPDATE registrants SET last_seen_snapshot_date = %(snapshot_date)s
WHERE jurisdiction = %(jurisdiction)s AND registration_number = %(registration_number)s
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


def _parse_row(raw_row: dict[str, str], snapshot_date: str) -> dict:
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
        "snapshot_date": snapshot_date,
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

    inserted = updated = unchanged = 0

    with conn.cursor() as cur:
        for raw_row in deduped.values():
            params = _parse_row(raw_row, snapshot_date)
            cur.execute(
                "SELECT source_row_hash FROM registrants "
                "WHERE jurisdiction = %(jurisdiction)s AND registration_number = %(registration_number)s",
                params,
            )
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
    )
