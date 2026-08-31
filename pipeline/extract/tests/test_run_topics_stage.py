from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import anthropic
import pytest
from fara_extract.extraction_runs import already_succeeded
from fara_extract.fields_topics import TopicClassification, extractor_version
from fara_extract.run_topics_stage import run_topics_stage

from conftest import seed_registrant, seed_registrant_doc


def _mock_client(parsed_output, stop_reason: str = "end_turn") -> MagicMock:
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.parse.return_value = MagicMock(parsed_output=parsed_output, stop_reason=stop_reason)
    return client


def _seed_doc_with_narrative_field(conn, nature_of_activities: str) -> int:
    registrant_id = seed_registrant(conn, 6492, "Sitrick Group")
    doc_id = seed_registrant_doc(
        conn, registrant_id, 6492, "https://efile.fara.gov/docs/test.pdf", document_type_code="EXHIBIT_AB"
    )
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO document_extracted_fields
                (registrant_doc_id, field_key, field_value_text, extraction_method, extractor_version, extracted_at)
            VALUES (%s, 'nature_of_activities', %s, 'llm', 'llm-claude-opus-5-v1', %s)
            """,
            (doc_id, nature_of_activities, now),
        )
    conn.commit()
    return doc_id


def test_topics_written_from_mocked_classification(migrated_conn):
    doc_id = _seed_doc_with_narrative_field(
        migrated_conn, "Support Huawei's communications in the U.S., including strategic counsel and media relations."
    )
    llm_client = _mock_client(TopicClassification(topics=["media_pr", "technology_export_controls"]))

    summary = run_topics_stage(conn=migrated_conn, llm_client=llm_client)

    assert summary.processed == 1
    assert summary.topics_written == 2

    with migrated_conn.cursor() as cur:
        cur.execute("SELECT topic FROM document_topics WHERE registrant_doc_id = %s ORDER BY topic", (doc_id,))
        topics = [r[0] for r in cur.fetchall()]
    assert topics == ["media_pr", "technology_export_controls"]
    assert already_succeeded(migrated_conn, doc_id, "topics", extractor_version("claude-opus-5"))


def test_backfill_mode_candidate_query_does_not_error(migrated_conn):
    # Regression: the backfill query's GROUP BY (needed for the FILTER
    # aggregates) originally omitted r.status even though ORDER BY referenced
    # it — Postgres rejects that. Only backfill mode joins `registrants` at
    # all, so `mode="new"` tests elsewhere never exercised this query.
    doc_id = _seed_doc_with_narrative_field(migrated_conn, "Consulting services for a European client.")
    llm_client = _mock_client(TopicClassification(topics=["general_representation"]))

    summary = run_topics_stage(conn=migrated_conn, llm_client=llm_client, mode="backfill", from_date="2020-01-01")

    assert summary.processed == 1
    assert already_succeeded(migrated_conn, doc_id, "topics", extractor_version("claude-opus-5"))


def test_rerun_skips_already_succeeded_docs(migrated_conn):
    _seed_doc_with_narrative_field(migrated_conn, "Tourism promotion services.")
    llm_client = _mock_client(TopicClassification(topics=["tourism_culture"]))

    run_topics_stage(conn=migrated_conn, llm_client=llm_client)
    summary2 = run_topics_stage(conn=migrated_conn, llm_client=llm_client)

    assert summary2.candidates == 0
    llm_client.messages.parse.assert_called_once()


def test_per_document_failure_is_recorded_and_batch_continues(migrated_conn):
    doc_id = _seed_doc_with_narrative_field(migrated_conn, "Consulting services.")
    llm_client = _mock_client(None, stop_reason="refusal")

    summary = run_topics_stage(conn=migrated_conn, llm_client=llm_client)

    assert summary.processed == 0
    assert summary.failed == 1
    assert not already_succeeded(migrated_conn, doc_id, "topics", extractor_version("claude-opus-5"))


def test_authentication_error_aborts_the_whole_batch(migrated_conn):
    _seed_doc_with_narrative_field(migrated_conn, "Consulting services.")
    llm_client = MagicMock(spec=anthropic.Anthropic)
    llm_client.messages.parse.side_effect = anthropic.AuthenticationError(
        message="invalid api key", response=MagicMock(status_code=401, headers={}), body=None
    )

    with pytest.raises(anthropic.AuthenticationError):
        run_topics_stage(conn=migrated_conn, llm_client=llm_client)
