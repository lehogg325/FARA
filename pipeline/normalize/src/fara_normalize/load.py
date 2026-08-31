from __future__ import annotations

import io
import zipfile
from datetime import date as date_

import psycopg
from fara_ingest.archive_factory import get_archive
from fara_ingest.config import Config as IngestConfig
from fara_ingest.manifest import Manifest as IngestManifest
from fara_ingest.sources.fara.bulk import archive_key
from fara_ingest.sources.fara.constants import JURISDICTION

from fara_normalize.csv_readers import read_csv_rows
from fara_normalize.db import get_connection
from fara_normalize.load_foreign_principals import load_foreign_principals
from fara_normalize.load_registrant_docs import load_registrant_docs
from fara_normalize.load_registrants import load_registrants
from fara_normalize.load_short_form_registrants import load_short_form_registrants
from fara_normalize.load_state import finish_load_run_failed, finish_load_run_succeeded, start_load_run

# Every loader takes (conn, raw_rows, snapshot_date) and returns an object with
# at least a .total_rows attribute, used as loaded_row_count for provenance.
# registrants must be loaded before the other three (they FK-resolve against it).
_LOADERS = {
    "registrants": load_registrants,
    "foreign_principals": load_foreign_principals,
    "short_forms": load_short_form_registrants,
    "registrant_docs": load_registrant_docs,
}


class NoVerifiedArchiveError(RuntimeError):
    pass


class UnknownDatasetError(ValueError):
    pass


def load_dataset(dataset: str, *, snapshot_date: str | None = None, conn: psycopg.Connection | None = None):
    if dataset not in _LOADERS:
        raise UnknownDatasetError(f"no normalize loader for dataset {dataset!r} yet; have {sorted(_LOADERS)}")

    snapshot_date = snapshot_date or date_.today().isoformat()

    ingest_cfg = IngestConfig.from_env()
    archive = get_archive(ingest_cfg)
    ingest_manifest = IngestManifest(ingest_cfg.manifest_path)

    status = ingest_manifest.get_status(JURISDICTION, dataset, snapshot_date)
    if status != "verified":
        raise NoVerifiedArchiveError(
            f"no verified bulk archive for dataset={dataset} snapshot_date={snapshot_date} (status={status!r}) "
            f"— run `fara-ingest bulk --dataset {dataset}` first"
        )

    key = archive_key(dataset, snapshot_date)
    with zipfile.ZipFile(io.BytesIO(archive.read_bytes(key))) as zf:
        csv_bytes = zf.read(zf.namelist()[0])
    raw_rows = read_csv_rows(csv_bytes)

    owns_conn = conn is None
    conn = conn or get_connection()
    load_run_id = start_load_run(conn, JURISDICTION, dataset, snapshot_date, key, len(raw_rows))
    conn.commit()
    try:
        result = _LOADERS[dataset](conn, raw_rows, snapshot_date)
        finish_load_run_succeeded(conn, load_run_id, result.total_rows)
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        finish_load_run_failed(conn, load_run_id, str(e))
        conn.commit()
        raise
    finally:
        if owns_conn:
            conn.close()
