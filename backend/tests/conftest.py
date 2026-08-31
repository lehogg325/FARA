from __future__ import annotations

import os
from datetime import date, datetime, timezone

import psycopg
import pytest
from fara_normalize.load_dimensions import load_jurisdictions
from fara_normalize.migrate import migrate
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from fara_backend.db import get_db
from fara_backend.main import app

TEST_DSN = os.environ.get("FARA_TEST_DATABASE_URL", "postgresql://fara:fara@localhost:5434/fara_test")

_DATA_TABLES = (
    "reportable_contacts",
    "document_topics",
    "topics",
    "extraction_runs",
    "document_extracted_fields",
    "document_text",
    "registrant_docs",
    "foreign_principals",
    "short_form_registrants",
    "registrants",
    "document_types",
    "countries",
    "load_runs",
    "jurisdictions",
)


@pytest.fixture(scope="session")
def test_dsn() -> str:
    admin_dsn = TEST_DSN.rsplit("/", 1)[0] + "/postgres"
    dbname = TEST_DSN.rsplit("/", 1)[1]
    with psycopg.connect(admin_dsn, autocommit=True) as admin_conn:
        exists = admin_conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone()
        if not exists:
            admin_conn.execute(f"CREATE DATABASE {dbname}")
    return TEST_DSN


@pytest.fixture()
def conn(test_dsn: str):
    # Migrations rely on tuple-indexed rows (migrate.py) — run them on a plain
    # connection, then hand tests a dict_row connection matching what the API
    # routes themselves expect (fara_backend.db.get_db uses dict_row too).
    setup_conn = psycopg.connect(test_dsn)
    migrate(setup_conn)
    load_jurisdictions(setup_conn)
    setup_conn.commit()
    setup_conn.close()

    connection = psycopg.connect(test_dsn, row_factory=dict_row)
    yield connection
    connection.rollback()
    with connection.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {', '.join(_DATA_TABLES)} RESTART IDENTITY CASCADE")
    connection.commit()
    connection.close()


@pytest.fixture()
def client(conn):
    def _override_get_db():
        yield conn

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded(conn):
    """One registrant with a foreign principal, a short-form individual, and a
    filed document with extracted text + one rule-based field — enough real
    shape to exercise every endpoint without a live database."""
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO countries (jurisdiction, country_name) VALUES ('fara', 'ICELAND')")
        cur.execute(
            "INSERT INTO document_types (jurisdiction, document_type_code, document_type_label) "
            "VALUES ('fara', 'EXHIBIT_AB', 'Exhibit AB')"
        )
        cur.execute(
            "INSERT INTO topics (topic, topic_label, sort_order) VALUES "
            "('diplomacy_bilateral', 'Diplomatic & Bilateral Relations', 9)"
        )
        cur.execute(
            """
            INSERT INTO registrants
                (jurisdiction, registration_number, name, business_name, address_1, city, state, zip,
                 registration_date, termination_date, status, source_row_hash,
                 first_seen_snapshot_date, last_seen_snapshot_date)
            VALUES ('fara', 5870, 'Brownstein Hyatt Farber Schreck, LLP', NULL, '100 Main St',
                    'Washington', 'DC', '20001', '2020-01-15', NULL, 'active', 'h1', %s, %s)
            RETURNING registrant_id
            """,
            (date(2026, 1, 1), date(2026, 1, 1)),
        )
        registrant_id = cur.fetchone()["registrant_id"]

        cur.execute(
            """
            INSERT INTO foreign_principals
                (jurisdiction, registrant_id, registration_number, foreign_principal_name, country_raw,
                 registration_date, termination_date, source_row_hash, first_seen_snapshot_date, last_seen_snapshot_date)
            VALUES ('fara', %s, 5870, 'The Government of Iceland', 'ICELAND', '2026-08-01', NULL, 'h2', %s, %s)
            RETURNING foreign_principal_id
            """,
            (registrant_id, date(2026, 1, 1), date(2026, 1, 1)),
        )
        foreign_principal_id = cur.fetchone()["foreign_principal_id"]

        cur.execute(
            """
            INSERT INTO short_form_registrants
                (jurisdiction, parent_registrant_id, parent_registration_number, last_name, first_name,
                 short_form_date, termination_date, source_row_hash, first_seen_snapshot_date, last_seen_snapshot_date)
            VALUES ('fara', %s, 5870, 'Buckner', 'Jason', '2026-08-01', NULL, 'h3', %s, %s)
            RETURNING short_form_registrant_id
            """,
            (registrant_id, date(2026, 1, 1), date(2026, 1, 1)),
        )
        short_form_registrant_id = cur.fetchone()["short_form_registrant_id"]

        cur.execute(
            """
            INSERT INTO registrant_docs
                (jurisdiction, registrant_id, registration_number, date_stamped, date_stamped_raw,
                 document_type_code, document_type_raw_label, url, url_available, source_row_hash,
                 first_seen_snapshot_date, last_seen_snapshot_date, pdf_object_key, pdf_byte_size, pdf_downloaded_at)
            VALUES ('fara', %s, 5870, '2026-08-13', '08/13/2026', 'EXHIBIT_AB', 'Exhibit AB',
                    'https://efile.fara.gov/docs/5870-Exhibit-AB-20260813-2.pdf', true, 'h4', %s, %s,
                    'fara/docs/5870/5870-Exhibit-AB-20260813-2.pdf', 28867, %s)
            RETURNING registrant_doc_id
            """,
            (registrant_id, date(2026, 1, 1), date(2026, 1, 1), now),
        )
        registrant_doc_id = cur.fetchone()["registrant_doc_id"]

        cur.execute(
            """
            INSERT INTO document_text
                (registrant_doc_id, extracted_text, extraction_method, page_count, char_count,
                 quality_flag, extractor_version, extracted_at)
            VALUES (%s, 'Provide strategic advice on navigating engagements with the United States government.',
                    'native', 11, 88, 'ok', 'text-v1', %s)
            """,
            (registrant_doc_id, now),
        )

        cur.execute(
            """
            INSERT INTO document_extracted_fields
                (registrant_doc_id, field_key, field_value_text, extraction_method, extractor_version, extracted_at)
            VALUES (%s, 'nature_of_activities',
                    'Provide strategic advice on navigating engagements with the United States government.',
                    'llm', 'llm-claude-opus-5-v1', %s)
            """,
            (registrant_doc_id, now),
        )

        cur.execute(
            """
            INSERT INTO extraction_runs (registrant_doc_id, stage, extractor_version, status, started_at, finished_at)
            VALUES (%s, 'fields_llm', 'llm-claude-opus-5-v1', 'succeeded', %s, %s)
            """,
            (registrant_doc_id, now, now),
        )

        cur.execute(
            """
            INSERT INTO document_topics (registrant_doc_id, topic, extractor_version, extracted_at)
            VALUES (%s, 'diplomacy_bilateral', 'topics-claude-opus-5-v1', %s)
            """,
            (registrant_doc_id, now),
        )

        cur.execute(
            """
            INSERT INTO reportable_contacts
                (registrant_doc_id, contact_date_raw, contact_name_raw, contact_method, purpose,
                 extraction_method, extractor_version, extracted_at)
            VALUES (%s, '03/26/2026', 'Rachel Oglesby, Dept of Education', 'Email', 'U.S.-Iceland relations',
                    'llm', 'contacts-llm-v1', %s)
            """,
            (registrant_doc_id, now),
        )

        cur.execute(
            """
            INSERT INTO document_extracted_fields
                (registrant_doc_id, field_key, field_value_text, field_value_numeric, field_value_date,
                 extraction_method, extractor_version, extracted_at)
            VALUES (%s, 'political_contribution[0]', 'Friends of a Senator', 2500.00, '2026-03-01',
                    'rule', 'rules-v1', %s)
            """,
            (registrant_doc_id, now),
        )

        cur.execute(
            """
            INSERT INTO load_runs
                (jurisdiction, dataset, snapshot_date, source_archive_key, source_row_count, loaded_row_count,
                 started_at, finished_at, status)
            VALUES ('fara', 'registrants', %s, 'fara/bulk/registrants/date=2026-08-01', 1, 1, %s, %s, 'succeeded')
            """,
            (date(2026, 8, 1), now, now),
        )
    conn.commit()

    return {
        "registrant_id": registrant_id,
        "foreign_principal_id": foreign_principal_id,
        "short_form_registrant_id": short_form_registrant_id,
        "registrant_doc_id": registrant_doc_id,
    }
