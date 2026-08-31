from __future__ import annotations

import os

import psycopg
import pytest

from fara_normalize.load_dimensions import load_jurisdictions
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
    load_jurisdictions(conn)  # FK target every downstream table needs
    conn.commit()
    yield conn
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {', '.join(_DATA_TABLES)} RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()
