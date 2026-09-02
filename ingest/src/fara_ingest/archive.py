from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol, runtime_checkable


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@runtime_checkable
class RawArchive(Protocol):
    """The exists()/write_atomic()/read_bytes() surface every raw-archive
    backend implements — LocalArchive here, ObjectStoreArchive
    (fara_ingest.object_store_archive) in CI/production. Callers type-hint
    against this, not a concrete backend, since
    fara_ingest.archive_factory.get_archive() picks between them."""

    def exists(self, key: str) -> bool: ...
    def write_atomic(self, key: str, data: bytes) -> object: ...
    def read_bytes(self, key: str) -> bytes: ...


class LocalArchive:
    """Object-storage-shaped raw archive backed by the local filesystem.

    Keys are forward-slash-separated strings, e.g.
    "fara/bulk/registrants/date=2026-08-21/FARA_All_Registrants.csv.zip".
    ObjectStoreArchive (any S3-compatible bucket — see docs/deploy.md) implements
    the same exists()/write_atomic()/read_bytes() surface so callers never change.

    Every bulk file here is small enough (a few MB at most) to hold entirely in
    memory, so write_atomic takes the complete bytes rather than streaming: the
    write is a single temp-file-then-rename, which is atomic on the same
    filesystem. A process killed before write_atomic is called leaves nothing on
    disk at all; a process killed during write_atomic leaves only an orphaned
    ".tmp" file next to the real key, never a partially-written file at the real
    key itself.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def write_atomic(self, key: str, data: bytes) -> Path:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        return path

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()
