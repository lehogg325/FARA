from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg

from fara_extract.extraction_runs import record_run
from fara_extract.fields_rules import RULES_EXTRACTOR_VERSION, extract_agreement_date, extract_political_contributions

JURISDICTION = "fara"
STAGE = "fields_rule"

# Only documents confirmed live to carry this item (docs/extraction.md):
# Registration Statement Item 10(c), Supplemental Statement Item 15(c), Short-Form Item 15.
_POLITICAL_CONTRIBUTION_DOC_TYPES = {"REGISTRATION_STATEMENT", "SUPPLEMENTAL_STATEMENT", "SHORT-FORM"}
_AGREEMENT_DATE_DOC_TYPES = {"EXHIBIT_AB"}

_CANDIDATES_SQL_NEW = """
SELECT dt.registrant_doc_id, dt.extracted_text, rd.document_type_code
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
SELECT dt.registrant_doc_id, dt.extracted_text, rd.document_type_code
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
) VALUES (%(registrant_doc_id)s, %(field_key)s, %(field_value_text)s, %(field_value_numeric)s,
          %(field_value_date)s, 'rule', %(extractor_version)s, %(extracted_at)s)
ON CONFLICT (registrant_doc_id, field_key, extractor_version) DO UPDATE SET
    field_value_text = excluded.field_value_text, field_value_numeric = excluded.field_value_numeric,
    field_value_date = excluded.field_value_date, extracted_at = excluded.extracted_at
"""


@dataclass
class FieldsRulesStageSummary:
    candidates: int
    processed: int
    fields_written: int
    failed: int


def _parse_date(raw: str) -> str | None:
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def run_fields_rules_stage(
    *, conn: psycopg.Connection, mode: str = "new", batch_size: int = 200, from_date: str = "1900-01-01"
) -> FieldsRulesStageSummary:
    document_types = list(_POLITICAL_CONTRIBUTION_DOC_TYPES | _AGREEMENT_DATE_DOC_TYPES)
    sql = _CANDIDATES_SQL_BACKFILL if mode == "backfill" else _CANDIDATES_SQL_NEW
    params = {
        "jurisdiction": JURISDICTION,
        "document_types": document_types,
        "stage": STAGE,
        "extractor_version": RULES_EXTRACTOR_VERSION,
        "batch_size": batch_size,
    }
    if mode == "backfill":
        params["from_date"] = from_date
    with conn.cursor() as cur:
        cur.execute(sql, params)
        candidates = cur.fetchall()

    processed = fields_written = failed = 0

    for registrant_doc_id, extracted_text, document_type_code in candidates:
        try:
            now = datetime.now(timezone.utc)
            with conn.cursor() as cur:
                if document_type_code in _POLITICAL_CONTRIBUTION_DOC_TYPES:
                    rows = extract_political_contributions(extracted_text)
                    for i, row in enumerate(rows):
                        cur.execute(
                            _UPSERT_FIELD_SQL,
                            {
                                "registrant_doc_id": registrant_doc_id,
                                "field_key": f"political_contribution[{i}]",
                                "field_value_text": row.description,
                                "field_value_numeric": row.amount,
                                "field_value_date": _parse_date(row.date_raw),
                                "extractor_version": RULES_EXTRACTOR_VERSION,
                                "extracted_at": now,
                            },
                        )
                        fields_written += 1

                if document_type_code in _AGREEMENT_DATE_DOC_TYPES:
                    agreement_date = extract_agreement_date(extracted_text)
                    if agreement_date is not None:
                        cur.execute(
                            _UPSERT_FIELD_SQL,
                            {
                                "registrant_doc_id": registrant_doc_id,
                                "field_key": "agreement_date",
                                "field_value_text": None,
                                "field_value_numeric": None,
                                "field_value_date": _parse_date(agreement_date),
                                "extractor_version": RULES_EXTRACTOR_VERSION,
                                "extracted_at": now,
                            },
                        )
                        fields_written += 1
        except Exception as e:
            record_run(conn, registrant_doc_id, STAGE, RULES_EXTRACTOR_VERSION, "failed", error_message=str(e))
            conn.commit()
            failed += 1
            continue

        record_run(conn, registrant_doc_id, STAGE, RULES_EXTRACTOR_VERSION, "succeeded")
        conn.commit()
        processed += 1

    return FieldsRulesStageSummary(
        candidates=len(candidates), processed=processed, fields_written=fields_written, failed=failed
    )
