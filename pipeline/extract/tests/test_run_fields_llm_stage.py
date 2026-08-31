from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import anthropic
import pytest
from fara_extract.extraction_runs import already_succeeded
from fara_extract.fields_llm import ExhibitABFields, extractor_version
from fara_extract.run_fields_llm_stage import run_fields_llm_stage
from fara_extract.text import extract_pdf_text

from conftest import seed_registrant, seed_registrant_doc

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "pdfs"


def _mock_client(parsed_output, stop_reason: str = "end_turn") -> MagicMock:
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.parse.return_value = MagicMock(parsed_output=parsed_output, stop_reason=stop_reason)
    return client


def _seed_document_text(conn, registrant_doc_id: int, filename: str) -> None:
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
                registrant_doc_id, result.extracted_text, result.extraction_method,
                result.page_count, result.char_count, result.quality_flag, datetime.now(timezone.utc),
            ),
        )


def _seed_exhibit_ab_doc(conn):
    registrant_id = seed_registrant(conn, 6170, "Mercury Public Affairs, LLC")
    doc_id = seed_registrant_doc(
        conn, registrant_id, 6170,
        "https://efile.fara.gov/docs/6170-Exhibit-AB-20260803-3.pdf",
        document_type_code="EXHIBIT_AB",
    )
    _seed_document_text(conn, doc_id, "era3-exhibit-ab.pdf")
    conn.commit()
    return doc_id


def test_fields_written_from_mocked_llm_response(migrated_conn):
    doc_id = _seed_exhibit_ab_doc(migrated_conn)
    llm_client = _mock_client(
        ExhibitABFields(
            nature_of_activities="Public relations and government relations advice",
            includes_political_activity=True,
            political_activity_description="Lobbying on behalf of the foreign principal",
            compensation_terms=None,
        )
    )

    summary = run_fields_llm_stage(conn=migrated_conn, llm_client=llm_client)

    assert summary.processed == 1
    assert summary.fields_written == 3  # compensation_terms was None, correctly skipped

    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT field_key, field_value_text FROM document_extracted_fields "
            "WHERE registrant_doc_id = %s ORDER BY field_key",
            (doc_id,),
        )
        rows = dict(cur.fetchall())
    assert rows["nature_of_activities"] == "Public relations and government relations advice"
    assert rows["includes_political_activity"] == "true"  # lowercase, not Python's "True"
    assert "compensation_terms" not in rows

    assert already_succeeded(migrated_conn, doc_id, "fields_llm", extractor_version())


def test_rerun_skips_already_succeeded_docs(migrated_conn):
    _seed_exhibit_ab_doc(migrated_conn)
    llm_client = _mock_client(ExhibitABFields(nature_of_activities="Consulting"))

    run_fields_llm_stage(conn=migrated_conn, llm_client=llm_client)
    summary2 = run_fields_llm_stage(conn=migrated_conn, llm_client=llm_client)

    assert summary2.candidates == 0
    llm_client.messages.parse.assert_called_once()  # never called a second time


def test_per_document_failure_is_recorded_and_batch_continues(migrated_conn):
    doc_id = _seed_exhibit_ab_doc(migrated_conn)
    llm_client = _mock_client(None, stop_reason="refusal")

    summary = run_fields_llm_stage(conn=migrated_conn, llm_client=llm_client)

    assert summary.processed == 0
    assert summary.failed == 1
    assert not already_succeeded(migrated_conn, doc_id, "fields_llm", extractor_version())


def test_authentication_error_aborts_the_whole_batch(migrated_conn):
    _seed_exhibit_ab_doc(migrated_conn)
    llm_client = MagicMock(spec=anthropic.Anthropic)
    llm_client.messages.parse.side_effect = anthropic.AuthenticationError(
        message="invalid api key", response=MagicMock(status_code=401, headers={}), body=None
    )

    with pytest.raises(anthropic.AuthenticationError):
        run_fields_llm_stage(conn=migrated_conn, llm_client=llm_client)
