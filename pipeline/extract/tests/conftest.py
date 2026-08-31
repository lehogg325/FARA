from __future__ import annotations

import os

import psycopg
import pytest
from fara_normalize.load_dimensions import load_document_types, load_jurisdictions
from fara_normalize.migrate import migrate

TEST_DSN = os.environ.get("FARA_TEST_DATABASE_URL", "postgresql://fara:fara@localhost:5434/fara_test")

_DATA_TABLES = (
    "extraction_runs",
    "document_extracted_fields",
    "document_text",
    "registrant_docs",
    "foreign_principals",
    "short_form_registrants",
    "registrants",
    "document_types",
    "countries",
    "jurisdictions",
)


@pytest.fixture(scope="session")
def test_dsn() -> str:
    admin_dsn = TEST_DSN.rsplit("/", 1)[0] + "/postgres"
    dbname = TEST_DSN.rsplit("/", 1)[1]
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone()
        if not exists:
            conn.execute(f"CREATE DATABASE {dbname}")
    return TEST_DSN


@pytest.fixture()
def migrated_conn(test_dsn: str):
    conn = psycopg.connect(test_dsn)
    migrate(conn)
    load_jurisdictions(conn)
    load_document_types(conn)
    conn.commit()
    yield conn
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {', '.join(_DATA_TABLES)} RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()


def seed_registrant(conn, registration_number: int, name: str = "Test Registrant") -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO registrants (
                jurisdiction, registration_number, name, status,
                source_row_hash, first_seen_snapshot_date, last_seen_snapshot_date
            ) VALUES ('fara', %s, %s, 'active', 'seed', '2026-08-01', '2026-08-01')
            RETURNING registrant_id
            """,
            (registration_number, name),
        )
        return cur.fetchone()[0]


def seed_registrant_doc(
    conn, registrant_id: int, registration_number: int, url: str, document_type_code: str = "REGISTRATION_STATEMENT"
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO registrant_docs (
                jurisdiction, registrant_id, registration_number, date_stamped, date_stamped_raw,
                document_type_code, document_type_raw_label, url, url_available,
                source_row_hash, first_seen_snapshot_date, last_seen_snapshot_date
            ) VALUES (
                'fara', %s, %s, '2026-08-01', '08/01/2026',
                %s, %s, %s, true,
                'seed', '2026-08-01', '2026-08-01'
            )
            RETURNING registrant_doc_id
            """,
            (registrant_id, registration_number, document_type_code, document_type_code, url),
        )
        return cur.fetchone()[0]
