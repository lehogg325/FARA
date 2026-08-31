from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import anthropic
import psycopg

from fara_extract.extraction_runs import record_run
from fara_extract.fields_llm import DEFAULT_MODEL, extract_exhibit_ab_fields, extractor_version

JURISDICTION = "fara"
STAGE = "fields_llm"

# Only the fixture-proven target for this build step (docs/extraction.md) —
# adding another doc type is a new schema + a new entry here, not new plumbing.
_TARGET_DOC_TYPES = ["EXHIBIT_AB"]

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

_UPSERT_FIELD_SQL = """
INSERT INTO document_extracted_fields (
    registrant_doc_id, field_key, field_value_text, field_value_numeric, field_value_date,
    extraction_method, extractor_version, extracted_at
) VALUES (%(registrant_doc_id)s, %(field_key)s, %(field_value_text)s, NULL, NULL,
          'llm', %(extractor_version)s, %(extracted_at)s)
ON CONFLICT (registrant_doc_id, field_key, extractor_version) DO UPDATE SET
    field_value_text = excluded.field_value_text, extracted_at = excluded.extracted_at
"""


@dataclass
class FieldsLlmStageSummary:
    candidates: int
    processed: int
    fields_written: int
    failed: int


def run_fields_llm_stage(
    *,
    conn: psycopg.Connection,
    llm_client: anthropic.Anthropic,
    mode: str = "new",
    batch_size: int = 50,
    model: str = DEFAULT_MODEL,
    from_date: str = "1900-01-01",
) -> FieldsLlmStageSummary:
    version = extractor_version(model)
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

    processed = fields_written = failed = 0

    for registrant_doc_id, extracted_text in candidates:
        try:
            fields = extract_exhibit_ab_fields(extracted_text, client=llm_client, model=model)
        except anthropic.AuthenticationError:
            # Not a per-document problem — every remaining call would fail
            # identically, so stop the batch rather than burn through it.
            raise
        except Exception as e:
            record_run(conn, registrant_doc_id, STAGE, version, "failed", error_message=str(e))
            conn.commit()
            failed += 1
            continue

        now = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            for field_key, value in fields.model_dump().items():
                if value is None:
                    continue
                # No dedicated boolean column in this EAV schema — serialize as
                # lowercase "true"/"false", not Python's "True"/"False", so a
                # later consumer parsing this text field sees the conventional form.
                text_value = str(value).lower() if isinstance(value, bool) else str(value)
                cur.execute(
                    _UPSERT_FIELD_SQL,
                    {
                        "registrant_doc_id": registrant_doc_id,
                        "field_key": field_key,
                        "field_value_text": text_value,
                        "extractor_version": version,
                        "extracted_at": now,
                    },
                )
                fields_written += 1
        record_run(conn, registrant_doc_id, STAGE, version, "succeeded")
        conn.commit()
        processed += 1

    return FieldsLlmStageSummary(
        candidates=len(candidates), processed=processed, fields_written=fields_written, failed=failed
    )
