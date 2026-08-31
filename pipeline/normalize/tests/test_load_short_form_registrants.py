from __future__ import annotations

from fara_normalize.load_registrants import load_registrants
from fara_normalize.load_short_form_registrants import load_short_form_registrants

REGISTRANT_ROW = {
    "Registration Number": "3001",
    "Registration Date": "01/01/2020",
    "Termination Date": "",
    "Name": "Public Affairs Group",
    "Business Name": "",
    "Address 1": "1 Lobby Lane",
    "Address 2": "",
    "City": "Washington",
    "State": "DC",
    "Zip": "20001",
}

SF_ROW = {
    "Short Form Termination Date": "",
    "Short Form Date": "02/01/2020",
    "Short Form Last Name": "Smith",
    "Short Form First Name": "Jane",
    "Registration Number": "3001",
    "Registration Date": "01/01/2020",
    "Registrant Name": "Public Affairs Group",
    "Address 1": "1 Lobby Lane",
    "Address 2": "",
    "City": "Washington",
    "State": "DC",
    "Zip": "20001",
}


def _seed_registrant(conn):
    load_registrants(conn, [REGISTRANT_ROW], "2026-08-01")
    conn.commit()


def test_insert_resolves_parent_registrant(migrated_conn):
    _seed_registrant(migrated_conn)
    result = load_short_form_registrants(migrated_conn, [SF_ROW], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 1
    assert result.skipped_unmapped_registrant == 0


def test_unknown_parent_registrant_is_skipped(migrated_conn):
    result = load_short_form_registrants(migrated_conn, [SF_ROW], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 0
    assert result.skipped_unmapped_registrant == 1


def test_blank_last_name_is_loaded_not_rejected(migrated_conn):
    # Confirmed real (docs/api-notes.md): 9 of 44,606 rows have a genuinely
    # blank Short Form Last Name in the source, not corruption.
    _seed_registrant(migrated_conn)
    blank_last_name = dict(SF_ROW, **{"Short Form Last Name": "", "Short Form First Name": "Soemarsono"})

    result = load_short_form_registrants(migrated_conn, [blank_last_name], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 1
    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT last_name, first_name FROM short_form_registrants "
            "WHERE jurisdiction='fara' AND parent_registration_number=3001"
        )
        assert cur.fetchone() == (None, "Soemarsono")


def test_duplicate_same_form_date_differing_termination_settles_on_last(migrated_conn):
    # Confirmed real shape (docs/api-notes.md): same person/date, two rows
    # differing only in Termination Date.
    _seed_registrant(migrated_conn)
    row_a = dict(SF_ROW, **{"Short Form Termination Date": "01/01/2021"})
    row_b = dict(SF_ROW, **{"Short Form Termination Date": "02/02/2022"})

    result = load_short_form_registrants(migrated_conn, [row_a, row_b], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 1
    assert result.duplicate_rows_collapsed == 1

    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT termination_date FROM short_form_registrants "
            "WHERE jurisdiction='fara' AND parent_registration_number=3001 AND last_name='Smith'"
        )
        assert str(cur.fetchone()[0]) == "2022-02-02"

    result2 = load_short_form_registrants(migrated_conn, [row_a, row_b], "2026-08-08")
    migrated_conn.commit()
    assert result2.updated == 0
    assert result2.unchanged == 1
