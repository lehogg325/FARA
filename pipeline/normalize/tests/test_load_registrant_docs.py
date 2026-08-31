from __future__ import annotations

from fara_normalize.load_dimensions import load_document_types
from fara_normalize.load_registrant_docs import load_registrant_docs
from fara_normalize.load_registrants import load_registrants

REGISTRANT_ROW = {
    "Registration Number": "4001",
    "Registration Date": "01/01/2018",
    "Termination Date": "",
    "Name": "Strategic Comms LLC",
    "Business Name": "",
    "Address 1": "1 K Street",
    "Address 2": "",
    "City": "Washington",
    "State": "DC",
    "Zip": "20005",
}

DOC_ROW = {
    "Date Stamped": "03/01/2018",
    "Registrant Name": "Strategic Comms LLC",
    "Registration Number": "4001",
    "Document Type": "Registration Statement",
    "Short Form Name": "",
    "Foreign Principal Name": "",
    "Foreign Principal Country": "",
    "URL": "https://efile.fara.gov/docs/4001-Registration-Statement-20180301-1.pdf",
}


def _seed(conn):
    load_registrants(conn, [REGISTRANT_ROW], "2026-08-01")
    load_document_types(conn)
    conn.commit()


def test_insert_resolves_registrant_and_document_type(migrated_conn):
    _seed(migrated_conn)
    result = load_registrant_docs(migrated_conn, [DOC_ROW], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 1
    assert result.skipped_unmapped_document_type == 0
    assert result.skipped_unmapped_registrant == 0

    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT document_type_code, url_available FROM registrant_docs "
            "WHERE jurisdiction='fara' AND registration_number=4001"
        )
        code, url_available = cur.fetchone()
    assert code == "REGISTRATION_STATEMENT"
    assert url_available is True


def test_first_load_reports_zero_unchanged_not_double_counted(migrated_conn):
    # Regression: the bulk staging-table approach originally ran INSERT before
    # the unchanged-touch step, and a freshly inserted row's hash trivially
    # equals its own staging row's hash — so every insert also got counted as
    # "unchanged." Confirmed live against the real 153K-row file before fixing
    # the statement order (docs/api-notes.md).
    _seed(migrated_conn)
    result = load_registrant_docs(migrated_conn, [DOC_ROW], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 1
    assert result.updated == 0
    assert result.unchanged == 0


def test_rerun_same_data_next_snapshot_settles_to_unchanged(migrated_conn):
    _seed(migrated_conn)
    load_registrant_docs(migrated_conn, [DOC_ROW], "2026-08-01")
    migrated_conn.commit()

    result = load_registrant_docs(migrated_conn, [DOC_ROW], "2026-08-08")
    migrated_conn.commit()

    assert result.inserted == 0
    assert result.updated == 0
    assert result.unchanged == 1


def test_office_only_sentinel_is_not_url_available(migrated_conn):
    _seed(migrated_conn)
    office_only = dict(DOC_ROW, **{"URL": "Available-FARA-Public-Office"})
    load_registrant_docs(migrated_conn, [office_only], "2026-08-01")
    migrated_conn.commit()

    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT url_available FROM registrant_docs WHERE jurisdiction='fara' AND registration_number=4001"
        )
        assert cur.fetchone()[0] is False


def test_unmapped_document_type_is_skipped_and_counted(migrated_conn):
    _seed(migrated_conn)
    bad = dict(DOC_ROW, **{"Document Type": "Not A Real Type"})
    result = load_registrant_docs(migrated_conn, [bad], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 0
    assert result.skipped_unmapped_document_type == 1


def test_office_only_docs_disambiguated_by_short_form_name(migrated_conn):
    # Confirmed real shape (docs/api-notes.md): multiple people's Short-Form
    # filings under one registrant, same date, same office-only sentinel URL —
    # only Short Form Name tells them apart.
    _seed(migrated_conn)
    base = dict(DOC_ROW, **{"Document Type": "Short-Form", "URL": "Available-FARA-Public-Office"})
    row_a = dict(base, **{"Short Form Name": "Smith, Jane"})
    row_b = dict(base, **{"Short Form Name": "Doe, John"})

    result = load_registrant_docs(migrated_conn, [row_a, row_b], "2026-08-01")
    migrated_conn.commit()

    assert result.inserted == 2  # NOT collapsed as duplicates
    assert result.duplicate_rows_collapsed == 0


def test_append_only_no_row_ever_deleted_across_snapshots(migrated_conn):
    _seed(migrated_conn)
    load_registrant_docs(migrated_conn, [DOC_ROW], "2026-08-01")
    migrated_conn.commit()

    # A later snapshot's file no longer lists this historical doc — it must survive.
    result = load_registrant_docs(migrated_conn, [], "2026-08-08")
    migrated_conn.commit()

    assert result.missing_from_snapshot == 1
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM registrant_docs WHERE jurisdiction='fara'")
        assert cur.fetchone()[0] == 1
