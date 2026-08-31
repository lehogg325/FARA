from __future__ import annotations

from fara_ingest.archive import LocalArchive
from fara_ingest.config import Config
from fara_ingest.r2_archive import R2Archive


def get_archive(cfg: Config) -> LocalArchive | R2Archive:
    """R2 in CI/production, local disk everywhere else — selected by whether
    R2 credentials are configured at all, so local dev needs zero extra env
    vars beyond what Config already reads (docs/deploy.md)."""
    if cfg.r2_bucket:
        return R2Archive(
            bucket=cfg.r2_bucket,
            endpoint_url=cfg.r2_endpoint_url,
            access_key_id=cfg.r2_access_key_id,
            secret_access_key=cfg.r2_secret_access_key,
        )
    return LocalArchive(cfg.data_root)
