from __future__ import annotations

from fara_normalize.migrate import migrate

EXPECTED_TABLES = {
    "jurisdictions",
    "countries",
    "document_types",
    "registrants",
    "short_form_registrants",
    "foreign_principals",
    "registrant_docs",
    "load_runs",
    "document_text",
    "document_extracted_fields",
    "extraction_runs",
    "reportable_contacts",
    "topics",
    "document_topics",
    "schema_migrations",
}


def test_migrate_applies_all_migrations_in_order(migrated_conn):
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations ORDER BY filename")
        assert [r[0] for r in cur.fetchall()] == [
            "0001_init.sql",
            "0002_document_mining.sql",
            "0003_staging_tables.sql",
            "0004_search_indexes.sql",
            "0005_contacts_and_topics.sql",
            "0006_bulk_staging_for_remaining_loaders.sql",
        ]


def test_migrate_is_idempotent(migrated_conn):
    assert migrate(migrated_conn) == []


def test_core_tables_exist(migrated_conn):
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = {r[0] for r in cur.fetchall()}
    assert EXPECTED_TABLES <= tables


def test_pdf_archive_columns_added_by_second_migration(migrated_conn):
    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'registrant_docs'"
        )
        columns = {r[0] for r in cur.fetchall()}
    assert {"pdf_object_key", "pdf_sha256", "pdf_downloaded_at"} <= columns
