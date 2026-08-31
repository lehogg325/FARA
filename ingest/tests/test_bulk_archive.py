from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from fara_ingest.archive import LocalArchive
from fara_ingest.manifest import Manifest
from fara_ingest.sources.fara.bulk import BulkDownloadError, download_bulk_dataset
from fara_ingest.sources.fara.constants import BULK_BASE_URL, DATASETS

FIXTURES = Path(__file__).parent / "fixtures"


def _zip_bytes(csv_path: Path, member_name: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member_name, csv_path.read_bytes())
    return buf.getvalue()


@pytest.fixture
def registrants_zip_bytes() -> bytes:
    # Built from a real 50-row excerpt of the live FARA_All_Registrants.csv.zip
    # (see docs/api-notes.md) — same header, same encoding, real data.
    return _zip_bytes(FIXTURES / "FARA_All_Registrants.sample.csv", "FARA_All_Registrants.csv")


@respx.mock
def test_download_bulk_dataset_verifies_and_archives(tmp_path, registrants_zip_bytes):
    url = f"{BULK_BASE_URL}/{DATASETS['registrants']['filename']}"
    respx.get(url).mock(return_value=httpx.Response(200, content=registrants_zip_bytes))

    archive = LocalArchive(tmp_path / "raw")
    manifest = Manifest(tmp_path / "manifest.sqlite3")

    result = download_bulk_dataset(
        "registrants", archive=archive, manifest=manifest, snapshot_date="2026-08-21"
    )

    assert result.status == "verified"
    assert result.row_count == 50  # the fixture excerpt has 50 data rows
    assert archive.exists(result.archive_key)
    assert manifest.get_status("fara", "registrants", "2026-08-21") == "verified"

    archived = archive.read_bytes(result.archive_key)
    with zipfile.ZipFile(io.BytesIO(archived)) as zf:
        assert zf.namelist() == ["FARA_All_Registrants.csv"]


@respx.mock
def test_rerun_without_force_skips_network(tmp_path, registrants_zip_bytes):
    url = f"{BULK_BASE_URL}/{DATASETS['registrants']['filename']}"
    route = respx.get(url).mock(return_value=httpx.Response(200, content=registrants_zip_bytes))

    archive = LocalArchive(tmp_path / "raw")
    manifest = Manifest(tmp_path / "manifest.sqlite3")

    download_bulk_dataset("registrants", archive=archive, manifest=manifest, snapshot_date="2026-08-21")
    result2 = download_bulk_dataset(
        "registrants", archive=archive, manifest=manifest, snapshot_date="2026-08-21"
    )

    assert result2.status == "already_verified"
    assert route.call_count == 1


@respx.mock
def test_force_redownloads_even_if_verified(tmp_path, registrants_zip_bytes):
    url = f"{BULK_BASE_URL}/{DATASETS['registrants']['filename']}"
    route = respx.get(url).mock(return_value=httpx.Response(200, content=registrants_zip_bytes))

    archive = LocalArchive(tmp_path / "raw")
    manifest = Manifest(tmp_path / "manifest.sqlite3")

    download_bulk_dataset("registrants", archive=archive, manifest=manifest, snapshot_date="2026-08-21")
    result2 = download_bulk_dataset(
        "registrants", archive=archive, manifest=manifest, snapshot_date="2026-08-21", force=True
    )

    assert result2.status == "verified"
    assert route.call_count == 2


@respx.mock
def test_corrupt_zip_marks_failed_not_verified(tmp_path):
    url = f"{BULK_BASE_URL}/{DATASETS['registrants']['filename']}"
    respx.get(url).mock(return_value=httpx.Response(200, content=b"not a zip file at all"))

    archive = LocalArchive(tmp_path / "raw")
    manifest = Manifest(tmp_path / "manifest.sqlite3")

    with pytest.raises(BulkDownloadError):
        download_bulk_dataset("registrants", archive=archive, manifest=manifest, snapshot_date="2026-08-21")

    assert manifest.get_status("fara", "registrants", "2026-08-21") == "failed"
    assert not archive.exists("fara/bulk/registrants/date=2026-08-21/FARA_All_Registrants.csv.zip")


@respx.mock
def test_unexpected_header_marks_failed(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("FARA_All_Registrants.csv", "Wrong,Header\n1,2\n")
    url = f"{BULK_BASE_URL}/{DATASETS['registrants']['filename']}"
    respx.get(url).mock(return_value=httpx.Response(200, content=buf.getvalue()))

    archive = LocalArchive(tmp_path / "raw")
    manifest = Manifest(tmp_path / "manifest.sqlite3")

    with pytest.raises(BulkDownloadError):
        download_bulk_dataset("registrants", archive=archive, manifest=manifest, snapshot_date="2026-08-21")

    assert manifest.get_status("fara", "registrants", "2026-08-21") == "failed"


@respx.mock
def test_http_error_status_marks_failed(tmp_path):
    url = f"{BULK_BASE_URL}/{DATASETS['registrants']['filename']}"
    respx.get(url).mock(return_value=httpx.Response(404))

    archive = LocalArchive(tmp_path / "raw")
    manifest = Manifest(tmp_path / "manifest.sqlite3")

    with pytest.raises(BulkDownloadError):
        download_bulk_dataset("registrants", archive=archive, manifest=manifest, snapshot_date="2026-08-21")

    assert manifest.get_status("fara", "registrants", "2026-08-21") == "failed"


def test_write_atomic_leaves_no_partial_file_on_crash(tmp_path):
    from fara_ingest.archive import LocalArchive

    archive = LocalArchive(tmp_path / "raw")
    key = "fara/bulk/registrants/date=2026-08-21/FARA_All_Registrants.csv.zip"

    # Simulate a crash mid-write: only the .tmp sibling exists, never the real key.
    tmp_sibling = (tmp_path / "raw" / key).with_name("FARA_All_Registrants.csv.zip.tmp")
    tmp_sibling.parent.mkdir(parents=True, exist_ok=True)
    tmp_sibling.write_bytes(b"partial garbage")

    assert not archive.exists(key)

    archive.write_atomic(key, b"complete real content")
    assert archive.exists(key)
    assert archive.read_bytes(key) == b"complete real content"
