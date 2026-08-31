from __future__ import annotations

from pathlib import Path

from fara_ingest.archive import LocalArchive
from fara_ingest.archive_factory import get_archive
from fara_ingest.config import Config
from fara_ingest.r2_archive import R2Archive


def test_no_r2_bucket_configured_uses_local_archive(tmp_path):
    cfg = Config(
        data_root=tmp_path,
        manifest_path=tmp_path / "manifest.sqlite3",
        r2_bucket=None,
        r2_endpoint_url=None,
        r2_access_key_id=None,
        r2_secret_access_key=None,
    )
    assert isinstance(get_archive(cfg), LocalArchive)


def test_r2_bucket_configured_uses_r2_archive(tmp_path):
    cfg = Config(
        data_root=tmp_path,
        manifest_path=tmp_path / "manifest.sqlite3",
        r2_bucket="fara-prod",
        r2_endpoint_url="https://fake-account.r2.cloudflarestorage.com",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
    )
    assert isinstance(get_archive(cfg), R2Archive)
