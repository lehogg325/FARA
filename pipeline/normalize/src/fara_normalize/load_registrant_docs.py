from __future__ import annotations

from dataclasses import dataclass

import psycopg

from fara_normalize.csv_readers import clean_str, is_malformed_row, parse_mmddyyyy, row_hash
from fara_normalize.load_dimensions import register_observed_country
from fara_normalize.registrant_lookup import load_registrant_id_map

JURISDICTION = "fara"

_STAGING_COLUMNS = (
    "jurisdiction",
    "registrant_id",
    "registration_number",
    "date_stamped",
    "date_stamped_raw",
    "document_type_code",
    "document_type_raw_label",
    "short_form_name",
    "foreign_principal_name",
    "foreign_principal_country_raw",
    "url",
    "url_available",
    "source_row_hash",
)

# Natural key match, shared by all three bulk statements below — must exactly
# match ux_registrant_docs_natural_key (migrations/0001_init.sql).
_NATURAL_KEY_JOIN = """
    rd.jurisdiction = s.jurisdiction AND rd.registration_number = s.registration_number
    AND rd.document_type_raw_label = s.document_type_raw_label
    AND rd.date_stamped_raw = s.date_stamped_raw
    AND rd.url IS NOT DISTINCT FROM s.url
    AND rd.short_form_name IS NOT DISTINCT FROM s.short_form_name
    AND rd.foreign_principal_name IS NOT DISTINCT FROM s.foreign_principal_name
"""

_INSERT_MISSING_SQL = f"""
INSERT INTO registrant_docs (
    jurisdiction, registrant_id, registration_number, date_stamped, date_stamped_raw,
    document_type_code, document_type_raw_label, short_form_name, foreign_principal_name,
    foreign_principal_country_raw, url, url_available,
    source_row_hash, first_seen_snapshot_date, last_seen_snapshot_date
)
SELECT s.jurisdiction, s.registrant_id, s.registration_number, s.date_stamped, s.date_stamped_raw,
       s.document_type_code, s.document_type_raw_label, s.short_form_name, s.foreign_principal_name,
       s.foreign_principal_country_raw, s.url, s.url_available,
       s.source_row_hash, %(snapshot_date)s, %(snapshot_date)s
FROM stg_registrant_docs s
WHERE NOT EXISTS (SELECT 1 FROM registrant_docs rd WHERE {_NATURAL_KEY_JOIN})
"""

# Append-only: the natural key itself never changes on update — only the
# descriptive fields that can legitimately be corrected in a later snapshot.
_UPDATE_CHANGED_SQL = f"""
UPDATE registrant_docs rd SET
    date_stamped = s.date_stamped,
    foreign_principal_country_raw = s.foreign_principal_country_raw,
    url_available = s.url_available,
    source_row_hash = s.source_row_hash,
    last_seen_snapshot_date = %(snapshot_date)s,
    updated_at = now()
FROM stg_registrant_docs s
WHERE {_NATURAL_KEY_JOIN}
  AND rd.source_row_hash IS DISTINCT FROM s.source_row_hash
"""

# Must run before both _UPDATE_CHANGED_SQL and _INSERT_MISSING_SQL. Before
# _INSERT_MISSING_SQL: matched on hash equality alone, which would also
# trivially match rows _INSERT_MISSING_SQL just created (a freshly inserted
# row's hash always equals its own staging row's hash) if it ran first —
# confirmed live, that ordering double-counted every insert as "unchanged"
# too. Before _UPDATE_CHANGED_SQL for the same reason: that statement also
# overwrites source_row_hash to match the staging row, which would make a
# just-updated row trivially match this hash-equality condition too if it ran
# first — confirmed live 2026-09-02, that ordering double-counted every
# update as "unchanged" as well. Running this against only pre-existing,
# not-yet-touched rows first keeps all three counts disjoint.
_TOUCH_UNCHANGED_SQL = f"""
UPDATE registrant_docs rd SET last_seen_snapshot_date = %(snapshot_date)s
FROM stg_registrant_docs s
WHERE {_NATURAL_KEY_JOIN}
  AND rd.source_row_hash = s.source_row_hash
"""

_MISSING_FROM_SNAPSHOT_SQL = """
SELECT count(*) FROM registrant_docs
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
    skipped_unmapped_document_type: int = 0


def _natural_key(raw_row: dict[str, str]) -> tuple:
    return (
        raw_row["Registration Number"],
        clean_str(raw_row.get("Document Type")),
        clean_str(raw_row.get("Date Stamped")),
        clean_str(raw_row.get("URL")),
        clean_str(raw_row.get("Short Form Name")),
        clean_str(raw_row.get("Foreign Principal Name")),
    )


def _load_document_type_map(conn: psycopg.Connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT document_type_label, document_type_code FROM document_types WHERE jurisdiction = %s",
            (JURISDICTION,),
        )
        return dict(cur.fetchall())


def _parse_row(raw_row: dict[str, str], registrant_id: int, document_type_code: str) -> dict:
    url = clean_str(raw_row.get("URL"))
    date_stamped_raw = clean_str(raw_row.get("Date Stamped")) or ""
    return {
        "jurisdiction": JURISDICTION,
        "registrant_id": registrant_id,
        "registration_number": int(clean_str(raw_row["Registration Number"])),
        "date_stamped": parse_mmddyyyy(raw_row.get("Date Stamped")),
        "date_stamped_raw": date_stamped_raw,
        "document_type_code": document_type_code,
        "document_type_raw_label": clean_str(raw_row.get("Document Type")),
        "short_form_name": clean_str(raw_row.get("Short Form Name")),
        "foreign_principal_name": clean_str(raw_row.get("Foreign Principal Name")),
        "foreign_principal_country_raw": clean_str(raw_row.get("Foreign Principal Country")),
        "url": url,
        "url_available": bool(url and url.startswith("http")),
        "source_row_hash": row_hash(raw_row),
    }


def load_registrant_docs(
    conn: psycopg.Connection, raw_rows: list[dict[str, str]], snapshot_date: str
) -> LoadResult:
    """Append-only ledger (docs/api-notes.md: a FARA 'Amendment' is just another
    document row, never a value superseding an earlier one — no lane resolution
    needed, unlike LDA). Confirmed live: URL alone doesn't disambiguate distinct
    documents once it's the office-only sentinel (many people's Short-Form
    filings share a registrant+date+sentinel-URL) — short_form_name and
    foreign_principal_name are part of the natural key for exactly that reason.

    Bulk-loaded via a staging table + 3 set-based statements rather than a
    per-row loop: confirmed live that ~300K synchronous round trips (one SELECT
    + one INSERT/UPDATE per row) over this table's ~150K rows didn't finish in
    8+ minutes even with every query hitting its index — round-trip count
    itself was the bottleneck, not query cost.
    """
    document_type_map = _load_document_type_map(conn)
    registrant_id_map = load_registrant_id_map(conn, JURISDICTION)
    known_countries: set[str | None] = set()

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
    skipped_unmapped_document_type = 0
    staged_rows: list[dict] = []

    for raw_row in deduped.values():
        document_type_raw_label = clean_str(raw_row.get("Document Type"))
        document_type_code = document_type_map.get(document_type_raw_label)
        if document_type_code is None:
            skipped_unmapped_document_type += 1
            continue

        registration_number = int(clean_str(raw_row["Registration Number"]))
        registrant_id = registrant_id_map.get(registration_number)
        if registrant_id is None:
            skipped_unmapped_registrant += 1
            continue

        params = _parse_row(raw_row, registrant_id, document_type_code)
        country_raw = params["foreign_principal_country_raw"]
        if country_raw not in known_countries:
            register_observed_country(conn, JURISDICTION, country_raw)
            known_countries.add(country_raw)

        staged_rows.append(params)

    with conn.cursor() as cur:
        cur.execute("TRUNCATE stg_registrant_docs")
        with cur.copy(f"COPY stg_registrant_docs ({', '.join(_STAGING_COLUMNS)}) FROM STDIN") as copy:
            for params in staged_rows:
                copy.write_row(tuple(params[col] for col in _STAGING_COLUMNS))

        # See the ordering comment on _TOUCH_UNCHANGED_SQL above — it must run
        # first, before either of the other two statements.
        cur.execute(_TOUCH_UNCHANGED_SQL, {"snapshot_date": snapshot_date})
        unchanged = cur.rowcount
        cur.execute(_UPDATE_CHANGED_SQL, {"snapshot_date": snapshot_date})
        updated = cur.rowcount
        cur.execute(_INSERT_MISSING_SQL, {"snapshot_date": snapshot_date})
        inserted = cur.rowcount

        cur.execute("TRUNCATE stg_registrant_docs")
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
        skipped_unmapped_document_type=skipped_unmapped_document_type,
    )
