from __future__ import annotations

from fara_normalize.load_dimensions import (
    load_countries,
    load_document_types,
    load_jurisdictions,
    register_observed_country,
)


def _table_count(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        return cur.fetchone()[0]


def test_load_dimensions_seeds_expected_counts(migrated_conn):
    j = load_jurisdictions(migrated_conn)
    d = load_document_types(migrated_conn)
    c = load_countries(migrated_conn)
    migrated_conn.commit()

    assert j == 1
    assert d == 10
    assert c == 273
    assert _table_count(migrated_conn, "document_types") == 10
    assert _table_count(migrated_conn, "countries") == 273


def test_loading_twice_is_idempotent(migrated_conn):
    for _ in range(2):
        load_jurisdictions(migrated_conn)
        load_document_types(migrated_conn)
        load_countries(migrated_conn)
    migrated_conn.commit()

    assert _table_count(migrated_conn, "jurisdictions") == 1
    assert _table_count(migrated_conn, "document_types") == 10
    assert _table_count(migrated_conn, "countries") == 273


def test_register_observed_country_adds_new_value_without_a_fk_failure(migrated_conn):
    load_jurisdictions(migrated_conn)
    register_observed_country(migrated_conn, "fara", "UNITED KINGDOM OF CORALLAND")
    migrated_conn.commit()

    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM countries WHERE jurisdiction = 'fara' AND country_name = 'UNITED KINGDOM OF CORALLAND'"
        )
        assert cur.fetchone() is not None


def test_register_observed_country_ignores_empty_string(migrated_conn):
    load_jurisdictions(migrated_conn)
    register_observed_country(migrated_conn, "fara", "")
    migrated_conn.commit()
    assert _table_count(migrated_conn, "countries") == 0
