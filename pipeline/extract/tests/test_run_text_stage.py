from __future__ import annotations

from pathlib import Path

from fara_ingest.archive import LocalArchive, sha256_bytes
from fara_ingest.manifest import Manifest as IngestManifest

from fara_extract.extraction_runs import already_succeeded
from fara_extract.run_text_stage import run_text_stage
from fara_extract.text import EXTRACTOR_VERSION, METADATA_COVER_EXTRACTOR_VERSION

from conftest import seed_registrant, seed_registrant_doc

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "pdfs"


def _seed_pdf_download(ingest_manifest: IngestManifest, url: str, filename: str) -> None:
    raw = (FIXTURES_DIR / filename).read_bytes()
    ingest_manifest.start_pdf(url, registration_number=1, document_type="Registration Statement", date_stamped="08/01/2026")
    ingest_manifest.mark_pdf_verified(
        url, archive_key=filename, sha256=sha256_bytes(raw), byte_size=len(raw), http_status=200
    )


def test_real_born_digital_pdf_is_extracted_and_recorded(migrated_conn, tmp_path):
    registrant_id = seed_registrant(migrated_conn, 6170, "Mercury Public Affairs, LLC")
    url = "https://efile.fara.gov/docs/6170-Registration-Statement-20130514-1.pdf"
    doc_id = seed_registrant_doc(migrated_conn, registrant_id, 6170, url)
    migrated_conn.commit()

    archive = LocalArchive(FIXTURES_DIR)
    ingest_manifest = IngestManifest(tmp_path / "ingest_manifest.sqlite3")
    _seed_pdf_download(ingest_manifest, url, "era3-registration-statement.pdf")

    summary = run_text_stage(conn=migrated_conn, ingest_archive=archive, ingest_manifest=ingest_manifest)

    assert summary.extracted == 1
    assert summary.no_pdf_available == 0
    assert summary.failed == 0

    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT extraction_method, quality_flag, char_count FROM document_text WHERE registrant_doc_id = %s",
            (doc_id,),
        )
        method, quality, char_count = cur.fetchone()
    assert method == "native"
    assert quality == "ok"
    assert char_count > 1000

    assert already_succeeded(migrated_conn, doc_id, "text", EXTRACTOR_VERSION)

    with migrated_conn.cursor() as cur:
        cur.execute("SELECT pdf_object_key, pdf_sha256 FROM registrant_docs WHERE registrant_doc_id = %s", (doc_id,))
        object_key, sha256 = cur.fetchone()
    assert object_key == "era3-registration-statement.pdf"
    assert sha256 is not None


def test_real_scanned_pdf_ocr_and_metadata_cover_are_recorded_separately(migrated_conn, tmp_path):
    registrant_id = seed_registrant(migrated_conn, 536, "Irish Tourist Board")
    url = "https://efile.fara.gov/docs/536-Exhibit-AB-19530801-CY1A4G06.pdf"
    doc_id = seed_registrant_doc(migrated_conn, registrant_id, 536, url, document_type_code="EXHIBIT_AB")
    migrated_conn.commit()

    archive = LocalArchive(FIXTURES_DIR)
    ingest_manifest = IngestManifest(tmp_path / "ingest_manifest.sqlite3")
    _seed_pdf_download(ingest_manifest, url, "era1-metadata-cover-scanned-body.pdf")

    summary = run_text_stage(conn=migrated_conn, ingest_archive=archive, ingest_manifest=ingest_manifest)
    assert summary.extracted == 1

    with migrated_conn.cursor() as cur:
        cur.execute("SELECT extraction_method FROM document_text WHERE registrant_doc_id = %s", (doc_id,))
        assert cur.fetchone()[0] == "ocr"

        cur.execute(
            "SELECT field_key, field_value_text FROM document_extracted_fields "
            "WHERE registrant_doc_id = %s AND extractor_version = %s ORDER BY field_key",
            (doc_id, METADATA_COVER_EXTRACTOR_VERSION),
        )
        fields = dict(cur.fetchall())
    assert fields["doc_metadata.registration_number"] == "536"
    assert fields["doc_metadata.registrant_name"] == "IRISH TOURIST BOARD"


def test_rerun_skips_already_succeeded_docs(migrated_conn, tmp_path):
    registrant_id = seed_registrant(migrated_conn, 6170, "Mercury Public Affairs, LLC")
    url = "https://efile.fara.gov/docs/6170-Registration-Statement-20130514-1.pdf"
    seed_registrant_doc(migrated_conn, registrant_id, 6170, url)
    migrated_conn.commit()

    archive = LocalArchive(FIXTURES_DIR)
    ingest_manifest = IngestManifest(tmp_path / "ingest_manifest.sqlite3")
    _seed_pdf_download(ingest_manifest, url, "era3-registration-statement.pdf")

    run_text_stage(conn=migrated_conn, ingest_archive=archive, ingest_manifest=ingest_manifest)
    summary2 = run_text_stage(conn=migrated_conn, ingest_archive=archive, ingest_manifest=ingest_manifest)

    assert summary2.candidates == 0  # already succeeded at this extractor_version, excluded from candidates


def test_doc_without_downloaded_pdf_is_counted_not_crashed_on(migrated_conn, tmp_path):
    registrant_id = seed_registrant(migrated_conn, 9999, "No PDF Yet Inc")
    seed_registrant_doc(migrated_conn, registrant_id, 9999, "https://efile.fara.gov/docs/9999-Registration-Statement-1.pdf")
    migrated_conn.commit()

    archive = LocalArchive(FIXTURES_DIR)
    ingest_manifest = IngestManifest(tmp_path / "ingest_manifest.sqlite3")  # nothing recorded — never downloaded

    summary = run_text_stage(conn=migrated_conn, ingest_archive=archive, ingest_manifest=ingest_manifest)

    assert summary.no_pdf_available == 1
    assert summary.extracted == 0
