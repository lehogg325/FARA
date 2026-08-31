from __future__ import annotations

from datetime import datetime, timezone

from fara_extract.run_fields_rules_stage import run_fields_rules_stage
from fara_extract.text import extract_pdf_text

from conftest import seed_registrant, seed_registrant_doc

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "pdfs"


def _seed_document_text(conn, registrant_doc_id: int, filename: str) -> str:
    result = extract_pdf_text((FIXTURES_DIR / filename).read_bytes())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO document_text (
                registrant_doc_id, extracted_text, extraction_method, page_count, char_count,
                quality_flag, extractor_version, extracted_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'text-v1', %s)
            """,
            (
                registrant_doc_id,
                result.extracted_text,
                result.extraction_method,
                result.page_count,
                result.char_count,
                result.quality_flag,
                datetime.now(timezone.utc),
            ),
        )
    return result.extracted_text


def test_political_contributions_written_as_indexed_fields(migrated_conn):
    registrant_id = seed_registrant(migrated_conn, 6170, "Mercury Public Affairs, LLC")
    doc_id = seed_registrant_doc(
        migrated_conn, registrant_id, 6170,
        "https://efile.fara.gov/docs/6170-Registration-Statement-20130514-1.pdf",
        document_type_code="REGISTRATION_STATEMENT",
    )
    _seed_document_text(migrated_conn, doc_id, "era3-registration-statement.pdf")
    migrated_conn.commit()

    summary = run_fields_rules_stage(conn=migrated_conn, mode="new")

    assert summary.processed == 1
    assert summary.fields_written == 14  # confirmed real count (test_fields_rules.py)

    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT field_key, field_value_numeric, field_value_date FROM document_extracted_fields "
            "WHERE registrant_doc_id = %s ORDER BY field_key",
            (doc_id,),
        )
        rows = cur.fetchall()
    assert rows[0][0] == "political_contribution[0]"
    assert float(rows[0][1]) == 1000.00
    assert str(rows[0][2]) == "2013-02-07"


def test_agreement_date_written_for_exhibit_ab(migrated_conn):
    registrant_id = seed_registrant(migrated_conn, 6170, "Mercury Public Affairs, LLC")
    doc_id = seed_registrant_doc(
        migrated_conn, registrant_id, 6170,
        "https://efile.fara.gov/docs/6170-Exhibit-AB-20260803-3.pdf",
        document_type_code="EXHIBIT_AB",
    )
    _seed_document_text(migrated_conn, doc_id, "era3-exhibit-ab.pdf")
    migrated_conn.commit()

    summary = run_fields_rules_stage(conn=migrated_conn, mode="new")

    assert summary.fields_written == 1
    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT field_value_date FROM document_extracted_fields "
            "WHERE registrant_doc_id = %s AND field_key = 'agreement_date'",
            (doc_id,),
        )
        assert str(cur.fetchone()[0]) == "2026-07-24"


def test_rerun_skips_already_processed_docs(migrated_conn):
    registrant_id = seed_registrant(migrated_conn, 6170, "Mercury Public Affairs, LLC")
    doc_id = seed_registrant_doc(
        migrated_conn, registrant_id, 6170,
        "https://efile.fara.gov/docs/6170-Registration-Statement-20130514-1.pdf",
        document_type_code="REGISTRATION_STATEMENT",
    )
    _seed_document_text(migrated_conn, doc_id, "era3-registration-statement.pdf")
    migrated_conn.commit()

    run_fields_rules_stage(conn=migrated_conn, mode="new")
    summary2 = run_fields_rules_stage(conn=migrated_conn, mode="new")

    assert summary2.candidates == 0


def test_document_type_without_target_fields_yields_nothing(migrated_conn):
    registrant_id = seed_registrant(migrated_conn, 6170, "Mercury Public Affairs, LLC")
    doc_id = seed_registrant_doc(
        migrated_conn, registrant_id, 6170,
        "https://efile.fara.gov/docs/6170-Amendment-20260807-12.pdf",
        document_type_code="AMENDMENT",
    )
    _seed_document_text(migrated_conn, doc_id, "era3-amendment.pdf")
    migrated_conn.commit()

    summary = run_fields_rules_stage(conn=migrated_conn, mode="new")
    assert summary.candidates == 0  # AMENDMENT isn't in either target-doc-type set
