from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Env-driven config. data_root is only used by the local-disk archive
    backend (dev); when FARA_R2_BUCKET is set, fara_ingest.archive_factory
    hands out an R2-backed archive instead and data_root is ignored
    (docs/deploy.md).
    """

    data_root: Path
    manifest_path: Path
    r2_bucket: str | None
    r2_endpoint_url: str | None
    r2_access_key_id: str | None
    r2_secret_access_key: str | None

    @classmethod
    def from_env(cls) -> "Config":
        data_root = Path(os.environ.get("FARA_INGEST_DATA_ROOT", "data/raw"))
        manifest_path = Path(os.environ.get("FARA_INGEST_MANIFEST_PATH", "data/manifest.sqlite3"))
        return cls(
            data_root=data_root,
            manifest_path=manifest_path,
            r2_bucket=os.environ.get("FARA_R2_BUCKET"),
            r2_endpoint_url=os.environ.get("FARA_R2_ENDPOINT_URL"),
            r2_access_key_id=os.environ.get("FARA_R2_ACCESS_KEY_ID"),
            r2_secret_access_key=os.environ.get("FARA_R2_SECRET_ACCESS_KEY"),
        )
