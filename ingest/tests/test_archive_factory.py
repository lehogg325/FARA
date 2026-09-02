from __future__ import annotations

from pathlib import Path

from fara_ingest.archive import LocalArchive
from fara_ingest.archive_factory import get_archive
from fara_ingest.config import Config
from fara_ingest.object_store_archive import ObjectStoreArchive


def test_no_bucket_configured_uses_local_archive(tmp_path):
    cfg = Config(
        data_root=tmp_path,
        manifest_path=tmp_path / "manifest.sqlite3",
        storage_bucket=None,
        storage_endpoint_url=None,
        storage_access_key_id=None,
        storage_secret_access_key=None,
    )
    assert isinstance(get_archive(cfg), LocalArchive)


def test_bucket_configured_uses_object_store_archive(tmp_path):
    cfg = Config(
        data_root=tmp_path,
        manifest_path=tmp_path / "manifest.sqlite3",
        storage_bucket="fara-prod",
        storage_endpoint_url="https://fake-project.supabase.co/storage/v1/s3",
        storage_access_key_id="key",
        storage_secret_access_key="secret",
    )
    assert isinstance(get_archive(cfg), ObjectStoreArchive)
