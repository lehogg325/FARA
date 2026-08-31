from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date as date_

import httpx

from fara_ingest.archive import RawArchive, sha256_bytes
from fara_ingest.manifest import Manifest
from fara_ingest.sources.fara.constants import BULK_BASE_URL, DATASETS, ENCODING, JURISDICTION

USER_AGENT = "fara-ingest/0.1 (https://github.com/lehogg325/FARA)"


class BulkDownloadError(RuntimeError):
    """Raised when a downloaded bulk file fails integrity or schema verification."""


@dataclass
class BulkDownloadResult:
    dataset: str
    snapshot_date: str
    status: str  # 'verified' | 'already_verified'
    archive_key: str | None
    row_count: int | None
    byte_size: int | None
    sha256: str | None


def archive_key(dataset: str, snapshot_date: str) -> str:
    """Public so pipeline/normalize can locate an already-archived bulk file
    without duplicating this path convention."""
    return f"fara/bulk/{dataset}/date={snapshot_date}/{DATASETS[dataset]['filename']}"


def _verify_zip(raw: bytes, expected_header: list[str]) -> int:
    """Validates zip integrity, member count, and CSV header. Returns data row count."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise BulkDownloadError(f"not a valid zip file: {e}") from e

    bad_member = zf.testzip()
    if bad_member is not None:
        raise BulkDownloadError(f"zip CRC check failed for member {bad_member!r}")

    members = zf.namelist()
    if len(members) != 1:
        raise BulkDownloadError(f"expected exactly one member in zip, found {members!r}")

    csv_text = zf.read(members[0]).decode(ENCODING)
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader, None)
    if header != expected_header:
        raise BulkDownloadError(f"unexpected CSV header {header!r} (expected {expected_header!r})")

    return sum(1 for _ in reader)


def download_bulk_dataset(
    dataset: str,
    *,
    archive: RawArchive,
    manifest: Manifest,
    snapshot_date: str | None = None,
    force: bool = False,
    client: httpx.Client | None = None,
) -> BulkDownloadResult:
    if dataset not in DATASETS:
        raise ValueError(f"unknown dataset {dataset!r}; valid: {sorted(DATASETS)}")

    spec = DATASETS[dataset]
    snapshot_date = snapshot_date or date_.today().isoformat()

    if not force and manifest.get_status(JURISDICTION, dataset, snapshot_date) == "verified":
        return BulkDownloadResult(dataset, snapshot_date, "already_verified", None, None, None, None)

    manifest.start(JURISDICTION, dataset, snapshot_date)

    url = f"{BULK_BASE_URL}/{spec['filename']}"
    owns_client = client is None
    http_client = client or httpx.Client(timeout=60.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    try:
        try:
            response = http_client.get(url)
        except httpx.HTTPError as e:
            manifest.mark_failed(JURISDICTION, dataset, snapshot_date, error_message=str(e))
            raise BulkDownloadError(f"request to {url} failed: {e}") from e
    finally:
        if owns_client:
            http_client.close()

    if response.status_code != 200:
        manifest.mark_failed(
            JURISDICTION,
            dataset,
            snapshot_date,
            error_message=f"HTTP {response.status_code}",
            http_status=response.status_code,
        )
        raise BulkDownloadError(f"HTTP {response.status_code} fetching {url}")

    raw = response.content
    try:
        row_count = _verify_zip(raw, spec["expected_header"])
    except BulkDownloadError as e:
        manifest.mark_failed(
            JURISDICTION, dataset, snapshot_date, error_message=str(e), http_status=response.status_code
        )
        raise

    key = archive_key(dataset, snapshot_date)
    archive.write_atomic(key, raw)
    digest = sha256_bytes(raw)

    manifest.mark_verified(
        JURISDICTION,
        dataset,
        snapshot_date,
        archive_key=key,
        sha256=digest,
        byte_size=len(raw),
        row_count=row_count,
        http_status=response.status_code,
    )
    return BulkDownloadResult(dataset, snapshot_date, "verified", key, row_count, len(raw), digest)
