from __future__ import annotations

from fara_normalize.load_registrants import load_registrants

ROW_A = {
    "Registration Number": "1001",
    "Registration Date": "01/15/2020",
    "Termination Date": "",
    "Name": "Acme Advocacy LLC",
    "Business Name": "",
    "Address 1": "100 Main St",
    "Address 2": "",
    "City": "Washington",
    "State": "DC",
    "Zip": "20001",
}
ROW_B = {
    "Registration Number": "1002",
    "Registration Date": "02/20/2019",
    "Termination Date": "03/01/2023",
    "Name": "Old Firm Inc",
    "Business Name": "",
    "Address 1": "200 Elm St",
    "Address 2": "",
    "City": "Alexandria",
    "State": "VA",
    "Zip": "22301",
}


def _fetch(conn, registration_number: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, address_1, status, first_seen_snapshot_date, last_seen_snapshot_date "
            "FROM registrants WHERE jurisdiction='fara' AND registration_number=%s",
            (registration_number,),
        )
        return cur.fetchone()


def test_insert_new_rows_and_derive_status(migrated_conn):
    result = load_registrants(migrated_conn, [ROW_A, ROW_B], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 2
    assert result.updated == 0
    assert result.unchanged == 0
    assert result.missing_from_snapshot == 0

    active_row = _fetch(migrated_conn, 1001)
    assert active_row[0] == "Acme Advocacy LLC"
    assert active_row[2] == "active"

    terminated_row = _fetch(migrated_conn, 1002)
    assert terminated_row[2] == "terminated"


def test_rerun_same_data_is_a_pure_touch_no_updates(migrated_conn):
    load_registrants(migrated_conn, [ROW_A, ROW_B], "2026-08-01")
    migrated_conn.commit()

    result = load_registrants(migrated_conn, [ROW_A, ROW_B], "2026-08-08")
    migrated_conn.commit()

    assert result.inserted == 0
    assert result.updated == 0
    assert result.unchanged == 2

    row = _fetch(migrated_conn, 1001)
    assert str(row[4]) == "2026-08-08"  # last_seen bumped even though nothing else changed


def test_one_address_change_plus_one_new_row(migrated_conn):
    load_registrants(migrated_conn, [ROW_A, ROW_B], "2026-08-01")
    migrated_conn.commit()

    row_a_edited = dict(ROW_A, **{"Address 1": "999 New Address Ave"})
    row_c_new = {
        "Registration Number": "1003",
        "Registration Date": "08/10/2026",
        "Termination Date": "",
        "Name": "Brand New Registrant",
        "Business Name": "",
        "Address 1": "1 Fresh Blvd",
        "Address 2": "",
        "City": "Denver",
        "State": "CO",
        "Zip": "80202",
    }

    result = load_registrants(migrated_conn, [row_a_edited, ROW_B, row_c_new], "2026-08-08")
    migrated_conn.commit()

    assert result.inserted == 1
    assert result.updated == 1
    assert result.unchanged == 1

    assert _fetch(migrated_conn, 1001)[1] == "999 New Address Ave"
    assert _fetch(migrated_conn, 1003) is not None


def test_row_missing_from_a_later_snapshot_is_flagged_not_deleted(migrated_conn):
    load_registrants(migrated_conn, [ROW_A, ROW_B], "2026-08-01")
    migrated_conn.commit()

    # ROW_B absent from this snapshot — must survive, just flagged.
    result = load_registrants(migrated_conn, [ROW_A], "2026-08-08")
    migrated_conn.commit()

    assert result.missing_from_snapshot == 1
    assert _fetch(migrated_conn, 1002) is not None  # never deleted


def test_intra_file_duplicate_registration_number_settles_on_last_row(migrated_conn):
    # Confirmed live: reg 5769 appeared twice in one real snapshot, differing
    # only in Termination Date (docs/api-notes.md). Without deduplication this
    # would alternate between the two rows' values on every re-run forever.
    dup_first = dict(ROW_A, **{"Termination Date": "01/01/2021"})
    dup_second = dict(ROW_A, **{"Termination Date": "02/02/2022"})

    result = load_registrants(migrated_conn, [dup_first, dup_second], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 1
    assert result.duplicate_rows_collapsed == 1
    row = _fetch(migrated_conn, 1001)
    assert row[2] == "terminated"

    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT termination_date FROM registrants WHERE jurisdiction='fara' AND registration_number=1001"
        )
        assert str(cur.fetchone()[0]) == "2022-02-02"  # last row in the file wins

    # Re-running the identical (still-duplicated) input must settle, not flip-flop.
    result2 = load_registrants(migrated_conn, [dup_first, dup_second], "2026-08-08")
    migrated_conn.commit()
    assert result2.inserted == 0
    assert result2.updated == 0
    assert result2.unchanged == 1


def test_purely_whitespace_change_still_counts_as_an_update(migrated_conn):
    load_registrants(migrated_conn, [ROW_A], "2026-08-01")
    migrated_conn.commit()

    whitespace_only = dict(ROW_A, **{"Name": ROW_A["Name"] + "  "})
    result = load_registrants(migrated_conn, [whitespace_only], "2026-08-08")
    migrated_conn.commit()

    # Hash is computed on the raw row, so even a whitespace-only source change
    # registers as a real update, though the cleaned column value is unaffected.
    assert result.updated == 1
    assert _fetch(migrated_conn, 1001)[0] == "Acme Advocacy LLC"
