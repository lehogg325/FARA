from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import anthropic
import pytest
from fara_extract.extraction_runs import already_succeeded
from fara_extract.fields_contacts import CONTACTS_EXTRACTOR_VERSION, ReportableContact, ReportableContactsExtraction
from fara_extract.run_contacts_stage import run_contacts_stage

from conftest import seed_registrant, seed_registrant_doc

# Real, verbatim from a 2025-2026 filing (docs/phase2.md) — see test_fields_contacts.py.
_QATAR_POPULATED_TEXT = (
    "11. Set forth below in the required detail the registrant's political activities.\n"
    "Date Contact Method Purpose\n"
    "Embassy of the State 03/26/2026 Rachel Oglesby, Email U.S.-Qatar relations\n"
    "of Qatar Jennifer Chong,\n"
    "Dept of Education\n"
    "13. In addition to the above described activities..."
)

_BLANK_TEXT = (
    "Date Contact Method Purpose\n"
    "Received by NSD/FARA Registration Unit 03/10/2025 11:37:17 AM\n"
    "12. During the period beginning 60 days prior to the obligation to register..."
)


def _mock_client(parsed_output, stop_reason: str = "end_turn") -> MagicMock:
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.parse.return_value = MagicMock(parsed_output=parsed_output, stop_reason=stop_reason)
    return client


def _seed_doc_with_text(conn, text: str, document_type_code: str = "EXHIBIT_AB") -> int:
    registrant_id = seed_registrant(conn, 5870, "Test Registrant")
    doc_id = seed_registrant_doc(
        conn, registrant_id, 5870, "https://efile.fara.gov/docs/test.pdf", document_type_code=document_type_code
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO document_text (
                registrant_doc_id, extracted_text, extraction_method, page_count, char_count,
                quality_flag, extractor_version, extracted_at
            ) VALUES (%s, %s, 'native', 1, %s, 'ok', 'text-v1', %s)
            """,
            (doc_id, text, len(text), datetime.now(timezone.utc)),
        )
    conn.commit()
    return doc_id


def test_populated_table_triggers_llm_call_and_writes_contact(migrated_conn):
    doc_id = _seed_doc_with_text(migrated_conn, _QATAR_POPULATED_TEXT)
    llm_client = _mock_client(
        ReportableContactsExtraction(
            contacts=[
                ReportableContact(
                    date="03/26/2026", contact_name="Rachel Oglesby, Dept of Education",
                    contact_method="Email", purpose="U.S.-Qatar relations",
                )
            ]
        )
    )

    summary = run_contacts_stage(conn=migrated_conn, llm_client=llm_client)

    assert summary.processed == 1
    assert summary.windows_found == 1
    assert summary.contacts_written == 1
    llm_client.messages.parse.assert_called_once()

    with migrated_conn.cursor() as cur:
        cur.execute("SELECT contact_name_raw, contact_method, purpose FROM reportable_contacts WHERE registrant_doc_id = %s", (doc_id,))
        row = cur.fetchone()
    assert row[0] == "Rachel Oglesby, Dept of Education"
    assert row[1] == "Email"
    assert already_succeeded(migrated_conn, doc_id, "contacts", CONTACTS_EXTRACTOR_VERSION)


def test_blank_table_skips_llm_call_entirely(migrated_conn):
    doc_id = _seed_doc_with_text(migrated_conn, _BLANK_TEXT)
    llm_client = _mock_client(None)  # would fail if called — proves it wasn't

    summary = run_contacts_stage(conn=migrated_conn, llm_client=llm_client)

    assert summary.processed == 1
    assert summary.windows_found == 0
    assert summary.contacts_written == 0
    llm_client.messages.parse.assert_not_called()
    assert already_succeeded(migrated_conn, doc_id, "contacts", CONTACTS_EXTRACTOR_VERSION)


def test_rerun_skips_already_succeeded_docs(migrated_conn):
    _seed_doc_with_text(migrated_conn, _QATAR_POPULATED_TEXT)
    llm_client = _mock_client(ReportableContactsExtraction(contacts=[]))

    run_contacts_stage(conn=migrated_conn, llm_client=llm_client)
    summary2 = run_contacts_stage(conn=migrated_conn, llm_client=llm_client)

    assert summary2.candidates == 0


def test_per_document_failure_is_recorded_and_batch_continues(migrated_conn):
    doc_id = _seed_doc_with_text(migrated_conn, _QATAR_POPULATED_TEXT)
    llm_client = _mock_client(None, stop_reason="refusal")

    summary = run_contacts_stage(conn=migrated_conn, llm_client=llm_client)

    assert summary.processed == 0
    assert summary.failed == 1
    assert not already_succeeded(migrated_conn, doc_id, "contacts", CONTACTS_EXTRACTOR_VERSION)


def test_authentication_error_aborts_the_whole_batch(migrated_conn):
    _seed_doc_with_text(migrated_conn, _QATAR_POPULATED_TEXT)
    llm_client = MagicMock(spec=anthropic.Anthropic)
    llm_client.messages.parse.side_effect = anthropic.AuthenticationError(
        message="invalid api key", response=MagicMock(status_code=401, headers={}), body=None
    )

    with pytest.raises(anthropic.AuthenticationError):
        run_contacts_stage(conn=migrated_conn, llm_client=llm_client)
