from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg
from fara_ingest.archive import RawArchive
from fara_ingest.manifest import Manifest as IngestManifest

from fara_extract.extraction_runs import record_run
from fara_extract.text import EXTRACTOR_VERSION, METADATA_COVER_EXTRACTOR_VERSION, extract_pdf_text

JURISDICTION = "fara"
STAGE = "text"

# `new` mode default: whatever's available and not yet processed, no
# prioritization needed — the candidate pool here is already small because the
# ingest downloader itself only ever fetched a recent/scoped set of PDFs.
_CANDIDATES_SQL_NEW = """
SELECT rd.registrant_doc_id, rd.url
FROM registrant_docs rd
WHERE rd.jurisdiction = %(jurisdiction)s AND rd.url_available = true
  AND NOT EXISTS (
      SELECT 1 FROM extraction_runs er
      WHERE er.registrant_doc_id = rd.registrant_doc_id AND er.stage = %(stage)s
        AND er.extractor_version = %(extractor_version)s AND er.status = 'succeeded'
  )
ORDER BY rd.registrant_doc_id
LIMIT %(batch_size)s
"""

# `backfill` mode: active registrants first, most recently filed within each
# group first — same ordering convention as the ingest docs downloader.
# from_date bounds it to a specific window (e.g. "2025-2026 only, nothing
# older") — defaults to a no-op floor when the caller wants the whole backlog.
_CANDIDATES_SQL_BACKFILL = """
SELECT rd.registrant_doc_id, rd.url
FROM registrant_docs rd
JOIN registrants r ON r.registrant_id = rd.registrant_id
WHERE rd.jurisdiction = %(jurisdiction)s AND rd.url_available = true
  AND rd.date_stamped >= %(from_date)s
  AND NOT EXISTS (
      SELECT 1 FROM extraction_runs er
      WHERE er.registrant_doc_id = rd.registrant_doc_id AND er.stage = %(stage)s
        AND er.extractor_version = %(extractor_version)s AND er.status = 'succeeded'
  )
ORDER BY (r.status = 'active') DESC, rd.date_stamped DESC NULLS LAST
LIMIT %(batch_size)s
"""

_UPSERT_DOCUMENT_TEXT_SQL = """
INSERT INTO document_text (
    registrant_doc_id, extracted_text, extraction_method, page_count, char_count,
    quality_flag, extractor_version, extracted_at
) VALUES (%(registrant_doc_id)s, %(extracted_text)s, %(extraction_method)s, %(page_count)s, %(char_count)s,
          %(quality_flag)s, %(extractor_version)s, %(extracted_at)s)
ON CONFLICT (registrant_doc_id) DO UPDATE SET
    extracted_text = excluded.extracted_text, extraction_method = excluded.extraction_method,
    page_count = excluded.page_count, char_count = excluded.char_count,
    quality_flag = excluded.quality_flag, extractor_version = excluded.extractor_version,
    extracted_at = excluded.extracted_at
"""

_UPSERT_METADATA_COVER_FIELD_SQL = """
INSERT INTO document_extracted_fields (
    registrant_doc_id, field_key, field_value_text, extraction_method, extractor_version, extracted_at
) VALUES (%(registrant_doc_id)s, %(field_key)s, %(field_value_text)s, 'rule', %(extractor_version)s, %(extracted_at)s)
ON CONFLICT (registrant_doc_id, field_key, extractor_version) DO UPDATE SET
    field_value_text = excluded.field_value_text, extracted_at = excluded.extracted_at
"""

_SYNC_PDF_PROVENANCE_SQL = """
UPDATE registrant_docs SET
    pdf_object_key = %(archive_key)s, pdf_sha256 = %(sha256)s, pdf_byte_size = %(byte_size)s,
    pdf_http_status = 200, pdf_downloaded_at = %(downloaded_at)s
WHERE registrant_doc_id = %(registrant_doc_id)s
"""


@dataclass
class TextStageSummary:
    candidates: int
    extracted: int
    no_pdf_available: int
    failed: int


def run_text_stage(
    *,
    conn: psycopg.Connection,
    ingest_archive: RawArchive,
    ingest_manifest: IngestManifest,
    mode: str = "new",
    batch_size: int = 200,
    from_date: str = "1900-01-01",
) -> TextStageSummary:
    sql = _CANDIDATES_SQL_BACKFILL if mode == "backfill" else _CANDIDATES_SQL_NEW
    params = {
        "jurisdiction": JURISDICTION,
        "stage": STAGE,
        "extractor_version": EXTRACTOR_VERSION,
        "batch_size": batch_size,
    }
    if mode == "backfill":
        params["from_date"] = from_date
    with conn.cursor() as cur:
        cur.execute(sql, params)
        candidates = cur.fetchall()

    extracted = no_pdf_available = failed = 0

    for registrant_doc_id, url in candidates:
        download_info = ingest_manifest.get_pdf_download_info(url)
        if download_info is None:
            no_pdf_available += 1
            continue
        archive_key, sha256, byte_size = download_info

        try:
            pdf_bytes = ingest_archive.read_bytes(archive_key)
            result = extract_pdf_text(pdf_bytes)
        except Exception as e:
            record_run(conn, registrant_doc_id, STAGE, EXTRACTOR_VERSION, "failed", error_message=str(e))
            conn.commit()
            failed += 1
            continue

        now = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                _UPSERT_DOCUMENT_TEXT_SQL,
                {
                    "registrant_doc_id": registrant_doc_id,
                    "extracted_text": result.extracted_text,
                    "extraction_method": result.extraction_method,
                    "page_count": result.page_count,
                    "char_count": result.char_count,
                    "quality_flag": result.quality_flag,
                    "extractor_version": EXTRACTOR_VERSION,
                    "extracted_at": now,
                },
            )
            for key, value in (result.metadata_cover_fields or {}).items():
                cur.execute(
                    _UPSERT_METADATA_COVER_FIELD_SQL,
                    {
                        "registrant_doc_id": registrant_doc_id,
                        "field_key": f"doc_metadata.{key.lower().replace(' ', '_')}",
                        "field_value_text": value,
                        "extractor_version": METADATA_COVER_EXTRACTOR_VERSION,
                        "extracted_at": now,
                    },
                )
            cur.execute(
                _SYNC_PDF_PROVENANCE_SQL,
                {
                    "registrant_doc_id": registrant_doc_id,
                    "archive_key": archive_key,
                    "sha256": sha256,
                    "byte_size": byte_size,
                    "downloaded_at": now,
                },
            )
        record_run(conn, registrant_doc_id, STAGE, EXTRACTOR_VERSION, "succeeded")
        conn.commit()
        extracted += 1

    return TextStageSummary(
        candidates=len(candidates), extracted=extracted, no_pdf_available=no_pdf_available, failed=failed
    )
