from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import anthropic
import psycopg

from fara_extract.extraction_runs import record_run
from fara_extract.fields_llm import DEFAULT_MODEL
from fara_extract.fields_topics import classify_topics, extractor_version

JURISDICTION = "fara"
STAGE = "topics"

# Any document with narrative fields already extracted is a candidate — not
# scoped to a specific document type, unlike fields_llm/contacts, since this
# stage classifies whatever narrative text exists rather than parsing a
# specific form item.
_CANDIDATES_SQL_NEW = """
SELECT rd.registrant_doc_id,
       max(def.field_value_text) FILTER (WHERE def.field_key = 'nature_of_activities') AS nature_of_activities,
       max(def.field_value_text) FILTER (WHERE def.field_key = 'political_activity_description') AS political_activity_description,
       max(def.field_value_text) FILTER (WHERE def.field_key = 'compensation_terms') AS compensation_terms
FROM registrant_docs rd
JOIN document_extracted_fields def ON def.registrant_doc_id = rd.registrant_doc_id
WHERE rd.jurisdiction = %(jurisdiction)s
  AND def.field_key IN ('nature_of_activities', 'political_activity_description', 'compensation_terms')
  AND NOT EXISTS (
      SELECT 1 FROM extraction_runs er
      WHERE er.registrant_doc_id = rd.registrant_doc_id AND er.stage = %(stage)s
        AND er.extractor_version = %(extractor_version)s AND er.status = 'succeeded'
  )
GROUP BY rd.registrant_doc_id
ORDER BY rd.registrant_doc_id
LIMIT %(batch_size)s
"""

_CANDIDATES_SQL_BACKFILL = """
SELECT rd.registrant_doc_id,
       max(def.field_value_text) FILTER (WHERE def.field_key = 'nature_of_activities') AS nature_of_activities,
       max(def.field_value_text) FILTER (WHERE def.field_key = 'political_activity_description') AS political_activity_description,
       max(def.field_value_text) FILTER (WHERE def.field_key = 'compensation_terms') AS compensation_terms
FROM registrant_docs rd
JOIN document_extracted_fields def ON def.registrant_doc_id = rd.registrant_doc_id
JOIN registrants r ON r.registrant_id = rd.registrant_id
WHERE rd.jurisdiction = %(jurisdiction)s
  AND def.field_key IN ('nature_of_activities', 'political_activity_description', 'compensation_terms')
  AND rd.date_stamped >= %(from_date)s
  AND NOT EXISTS (
      SELECT 1 FROM extraction_runs er
      WHERE er.registrant_doc_id = rd.registrant_doc_id AND er.stage = %(stage)s
        AND er.extractor_version = %(extractor_version)s AND er.status = 'succeeded'
  )
GROUP BY rd.registrant_doc_id, r.status
ORDER BY (r.status = 'active') DESC, rd.date_stamped DESC NULLS LAST
LIMIT %(batch_size)s
"""

_INSERT_TOPIC_SQL = """
INSERT INTO document_topics (registrant_doc_id, topic, extractor_version, extracted_at)
VALUES (%(registrant_doc_id)s, %(topic)s, %(extractor_version)s, %(extracted_at)s)
ON CONFLICT (registrant_doc_id, topic, extractor_version) DO NOTHING
"""


@dataclass
class TopicsStageSummary:
    candidates: int
    processed: int
    topics_written: int
    failed: int


def run_topics_stage(
    *,
    conn: psycopg.Connection,
    llm_client: anthropic.Anthropic,
    mode: str = "new",
    batch_size: int = 50,
    model: str = DEFAULT_MODEL,
    from_date: str = "1900-01-01",
) -> TopicsStageSummary:
    version = extractor_version(model)
    sql = _CANDIDATES_SQL_BACKFILL if mode == "backfill" else _CANDIDATES_SQL_NEW
    params = {"jurisdiction": JURISDICTION, "stage": STAGE, "extractor_version": version, "batch_size": batch_size}
    if mode == "backfill":
        params["from_date"] = from_date
    with conn.cursor() as cur:
        cur.execute(sql, params)
        candidates = cur.fetchall()

    processed = topics_written = failed = 0

    for registrant_doc_id, nature_of_activities, political_activity_description, compensation_terms in candidates:
        try:
            topics = classify_topics(
                nature_of_activities=nature_of_activities,
                political_activity_description=political_activity_description,
                compensation_terms=compensation_terms,
                client=llm_client,
                model=model,
            )
        except anthropic.AuthenticationError:
            raise
        except Exception as e:
            record_run(conn, registrant_doc_id, STAGE, version, "failed", error_message=str(e))
            conn.commit()
            failed += 1
            continue

        now = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            for topic in topics:
                cur.execute(
                    _INSERT_TOPIC_SQL,
                    {"registrant_doc_id": registrant_doc_id, "topic": topic, "extractor_version": version, "extracted_at": now},
                )
                topics_written += 1
        record_run(conn, registrant_doc_id, STAGE, version, "succeeded")
        conn.commit()
        processed += 1

    return TopicsStageSummary(candidates=len(candidates), processed=processed, topics_written=topics_written, failed=failed)
