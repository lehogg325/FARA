from __future__ import annotations

from fara_normalize.load_foreign_principals import load_foreign_principals
from fara_normalize.load_registrants import load_registrants

REGISTRANT_ROW = {
    "Registration Number": "2001",
    "Registration Date": "01/01/2015",
    "Termination Date": "",
    "Name": "Global Advocates LLC",
    "Business Name": "",
    "Address 1": "1 Advocacy Way",
    "Address 2": "",
    "City": "Washington",
    "State": "DC",
    "Zip": "20001",
}

FP_ROW = {
    "Foreign Principal Termination Date": "",
    "Foreign Principal": "Ministry of Culture",
    "Foreign Principal Registration Date": "02/01/2015",
    "Country/Location Represented": "FRANCE",
    "Registration Number": "2001",
    "Registrant Date": "01/01/2015",
    "Registrant Name": "Global Advocates LLC",
    "Address 1": "1 Rue de Paris",
    "Address 2": "",
    "City": "Paris",
    "State": "",
    "Zip": "",
}

# Confirmed real shape (docs/api-notes.md): an unescaped quote inside the name
# shifts every later column, leaving Registration Number non-numeric.
CORRUPTED_ROW = {
    "Foreign Principal Termination Date": "12/01/2022",
    "Foreign Principal": 'Some Org (SAR") ',
    "Foreign Principal Registration Date": ' through Some Firm"',
    "Country/Location Represented": "10/12/2022",
    "Registration Number": "SAUDI ARABIA",
    "Registrant Date": "3301",
    "Registrant Name": "11/10/1981",
    "Address 1": "Some Firm, LLC",
    "Address 2": "",
    "City": "",
    "State": "",
    "Zip": "",
}


def _seed_registrant(conn):
    load_registrants(conn, [REGISTRANT_ROW], "2026-08-01")
    conn.commit()


def test_insert_resolves_registrant_id_and_stores_country_as_free_text(migrated_conn):
    _seed_registrant(migrated_conn)
    result = load_foreign_principals(migrated_conn, [FP_ROW], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 1
    assert result.skipped_unparseable == 0
    assert result.skipped_unmapped_registrant == 0

    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT fp.country_raw, r.registrant_id = fp.registrant_id "
            "FROM foreign_principals fp JOIN registrants r ON r.jurisdiction='fara' AND r.registration_number=2001 "
            "WHERE fp.jurisdiction='fara' AND fp.registration_number=2001"
        )
        country_raw, fk_matches = cur.fetchone()
    assert country_raw == "FRANCE"
    assert fk_matches is True

    with migrated_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM countries WHERE jurisdiction='fara' AND country_name='FRANCE'")
        assert cur.fetchone() is not None  # auto-registered


def test_corrupted_row_is_skipped_and_counted_not_crashed_on(migrated_conn):
    _seed_registrant(migrated_conn)
    result = load_foreign_principals(migrated_conn, [FP_ROW, CORRUPTED_ROW], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 1  # only the good row
    assert result.skipped_unparseable == 1


def test_malformed_row_with_restkey_overflow_is_skipped_even_with_numeric_regnum(migrated_conn):
    # Confirmed real (docs/api-notes.md): 5 of the 14 malformed rows still have
    # a numeric-looking Registration Number while other columns are shifted —
    # is_malformed_row (restkey overflow) is what actually catches these.
    _seed_registrant(migrated_conn)
    sneaky_row = dict(FP_ROW)
    sneaky_row[None] = ["unexpected overflow column"]

    result = load_foreign_principals(migrated_conn, [FP_ROW, sneaky_row], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 1
    assert result.skipped_unparseable == 1


def test_row_referencing_unknown_registrant_is_skipped_and_counted(migrated_conn):
    # No registrant seeded at all — the FK target genuinely doesn't exist yet.
    result = load_foreign_principals(migrated_conn, [FP_ROW], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 0
    assert result.skipped_unmapped_registrant == 1


def test_rerun_same_data_settles_to_unchanged(migrated_conn):
    _seed_registrant(migrated_conn)
    load_foreign_principals(migrated_conn, [FP_ROW], "2026-08-01")
    migrated_conn.commit()

    result = load_foreign_principals(migrated_conn, [FP_ROW], "2026-08-08")
    migrated_conn.commit()

    assert result.inserted == 0
    assert result.updated == 0
    assert result.unchanged == 1
