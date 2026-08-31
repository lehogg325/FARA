from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import anthropic
import psycopg

from fara_extract.extraction_runs import record_run
from fara_extract.fields_contacts import (
    CONTACTS_EXTRACTOR_VERSION,
    find_populated_contact_windows,
    extract_reportable_contacts,
)
from fara_extract.fields_llm import DEFAULT_MODEL

JURISDICTION = "fara"
STAGE = "contacts"

# Confirmed real (docs/phase2.md): the Item 11 "Date Contact Method Purpose" table
# only ever appears in these two document types.
_TARGET_DOC_TYPES = ["EXHIBIT_AB", "SUPPLEMENTAL_STATEMENT"]

_CANDIDATES_SQL_NEW = """
SELECT dt.registrant_doc_id, dt.extracted_text
FROM document_text dt
JOIN registrant_docs rd ON rd.registrant_doc_id = dt.registrant_doc_id
WHERE rd.jurisdiction = %(jurisdiction)s
  AND rd.document_type_code = ANY(%(document_types)s)
  AND NOT EXISTS (
      SELECT 1 FROM extraction_runs er
      WHERE er.registrant_doc_id = dt.registrant_doc_id AND er.stage = %(stage)s
        AND er.extractor_version = %(extractor_version)s AND er.status = 'succeeded'
  )
ORDER BY dt.registrant_doc_id
LIMIT %(batch_size)s
"""

_CANDIDATES_SQL_BACKFILL = """
SELECT dt.registrant_doc_id, dt.extracted_text
FROM document_text dt
JOIN registrant_docs rd ON rd.registrant_doc_id = dt.registrant_doc_id
JOIN registrants r ON r.registrant_id = rd.registrant_id
WHERE rd.jurisdiction = %(jurisdiction)s
  AND rd.document_type_code = ANY(%(document_types)s)
  AND rd.date_stamped >= %(from_date)s
  AND NOT EXISTS (
      SELECT 1 FROM extraction_runs er
      WHERE er.registrant_doc_id = dt.registrant_doc_id AND er.stage = %(stage)s
        AND er.extractor_version = %(extractor_version)s AND er.status = 'succeeded'
  )
ORDER BY (r.status = 'active') DESC, rd.date_stamped DESC NULLS LAST
LIMIT %(batch_size)s
"""

_INSERT_CONTACT_SQL = """
INSERT INTO reportable_contacts (
    registrant_doc_id, contact_date, contact_date_raw, contact_name_raw,
    contact_method, purpose, extraction_method, extractor_version, extracted_at
) VALUES (%(registrant_doc_id)s, NULL, %(date_raw)s, %(contact_name_raw)s,
          %(contact_method)s, %(purpose)s, 'llm', %(extractor_version)s, %(extracted_at)s)
ON CONFLICT (registrant_doc_id, contact_name_raw, contact_date_raw, purpose, extractor_version)
DO UPDATE SET contact_method = excluded.contact_method, extracted_at = excluded.extracted_at
"""


@dataclass
class ContactsStageSummary:
    candidates: int
    processed: int
    windows_found: int
    contacts_written: int
    failed: int


def run_contacts_stage(
    *,
    conn: psycopg.Connection,
    llm_client: anthropic.Anthropic,
    mode: str = "new",
    batch_size: int = 50,
    model: str = DEFAULT_MODEL,
    from_date: str = "1900-01-01",
) -> ContactsStageSummary:
    version = CONTACTS_EXTRACTOR_VERSION
    sql = _CANDIDATES_SQL_BACKFILL if mode == "backfill" else _CANDIDATES_SQL_NEW
    params = {
        "jurisdiction": JURISDICTION,
        "document_types": _TARGET_DOC_TYPES,
        "stage": STAGE,
        "extractor_version": version,
        "batch_size": batch_size,
    }
    if mode == "backfill":
        params["from_date"] = from_date
    with conn.cursor() as cur:
        cur.execute(sql, params)
        candidates = cur.fetchall()

    processed = windows_found = contacts_written = failed = 0

    for registrant_doc_id, extracted_text in candidates:
        windows = find_populated_contact_windows(extracted_text)
        if not windows:
            # No rule-detected populated table — a real, common, and cheap
            # outcome (docs/phase2.md: ~96% of documents with the Item 11
            # table are blank or appendix-deferred). No LLM call needed.
            record_run(conn, registrant_doc_id, STAGE, version, "succeeded")
            conn.commit()
            processed += 1
            continue

        windows_found += len(windows)
        try:
            now = datetime.now(timezone.utc)
            with conn.cursor() as cur:
                for window in windows:
                    contacts = extract_reportable_contacts(window, client=llm_client, model=model)
                    for c in contacts:
                        cur.execute(
                            _INSERT_CONTACT_SQL,
                            {
                                "registrant_doc_id": registrant_doc_id,
                                "date_raw": c.date,
                                "contact_name_raw": c.contact_name or "(unnamed)",
                                "contact_method": c.contact_method,
                                "purpose": c.purpose,
                                "extractor_version": version,
                                "extracted_at": now,
                            },
                        )
                        contacts_written += 1
        except anthropic.AuthenticationError:
            raise
        except Exception as e:
            record_run(conn, registrant_doc_id, STAGE, version, "failed", error_message=str(e))
            conn.commit()
            failed += 1
            continue

        record_run(conn, registrant_doc_id, STAGE, version, "succeeded")
        conn.commit()
        processed += 1

    return ContactsStageSummary(
        candidates=len(candidates), processed=processed, windows_found=windows_found,
        contacts_written=contacts_written, failed=failed,
    )
