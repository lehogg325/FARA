from __future__ import annotations

from fara_ingest.archive import LocalArchive
from fara_ingest.config import Config
from fara_ingest.object_store_archive import ObjectStoreArchive


def get_archive(cfg: Config) -> LocalArchive | ObjectStoreArchive:
    """Object storage in CI/production, local disk everywhere else — selected
    by whether storage credentials are configured at all, so local dev needs
    zero extra env vars beyond what Config already reads (docs/deploy.md)."""
    if cfg.storage_bucket:
        return ObjectStoreArchive(
            bucket=cfg.storage_bucket,
            endpoint_url=cfg.storage_endpoint_url,
            access_key_id=cfg.storage_access_key_id,
            secret_access_key=cfg.storage_secret_access_key,
        )
    return LocalArchive(cfg.data_root)
