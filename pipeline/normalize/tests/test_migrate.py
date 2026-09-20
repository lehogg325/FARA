from __future__ import annotations

from fara_normalize.migrate import _migrations_dir, migrate

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
    # A hardcoded filename list drifts every time a migration is added (it did
    # -- this was still asserting the list as of 0006) -- assert against the
    # runner's own directory listing instead, so it can't go stale again.
    expected = sorted(p.name for p in _migrations_dir().glob("*.sql"))
    assert expected  # sanity: the glob itself isn't silently matching nothing
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations ORDER BY filename")
        assert [r[0] for r in cur.fetchall()] == expected


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


def test_fp_grouped_lookup_index_exists(migrated_conn):
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'foreign_principals'")
        indexes = {r[0] for r in cur.fetchall()}
    assert "ix_fp_grouped_lookup" in indexes


# Every table fara_app can read -- EXPECTED_TABLES minus schema_migrations
# (the migration ledger itself; no router ever reads it). load_runs/
# extraction_runs ARE included here even though 0009 keeps them off the
# public PostgREST surface (anon/authenticated) as internal pipeline
# bookkeeping -- meta.py's /api/meta aggregates over both for dataset
# freshness/extraction-coverage reporting, so this app's own connection
# needs them regardless of what the (unused) public REST API exposes.
FARA_APP_READABLE_TABLES = EXPECTED_TABLES - {"schema_migrations"}


def test_fara_app_role_has_select_only_access(migrated_conn):
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname = 'fara_app'")
        role = cur.fetchone()
        assert role is not None
        assert role[1] is False  # NOLOGIN until a password is granted outside git

        cur.execute(
            "SELECT tablename FROM pg_policies WHERE policyname = 'fara_app read access' ORDER BY tablename"
        )
        policy_tables = {r[0] for r in cur.fetchall()}
    assert policy_tables == FARA_APP_READABLE_TABLES
