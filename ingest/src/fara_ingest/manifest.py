from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS bulk_downloads (
    jurisdiction    TEXT NOT NULL,
    dataset         TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('downloading', 'verified', 'failed')),
    archive_key     TEXT,
    sha256          TEXT,
    byte_size       INTEGER,
    row_count       INTEGER,
    http_status     INTEGER,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    error_message   TEXT,
    PRIMARY KEY (jurisdiction, dataset, snapshot_date)
);

CREATE TABLE IF NOT EXISTS pdf_downloads (
    url             TEXT PRIMARY KEY,
    registration_number INTEGER,
    document_type   TEXT,
    date_stamped    TEXT,
    status          TEXT NOT NULL CHECK (status IN ('downloading', 'verified', 'unavailable', 'failed', 'too_large')),
    archive_key     TEXT,
    sha256          TEXT,
    byte_size       INTEGER,
    http_status     INTEGER,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    error_message   TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Manifest:
    """Kill-safe resumability ledger for the raw-archive ingest.

    A row's status is 'downloading' from the moment a fetch is attempted until
    it either succeeds ('verified') or fails cleanly ('failed'). If the process
    is killed at any point, the row is simply left in 'downloading' (or absent,
    if killed before start() ran) — the next run's start() overwrites it and
    retries from scratch. Nothing here assumes partial progress is resumable
    mid-file; only whole-dataset retries are needed at this data volume.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def get_status(self, jurisdiction: str, dataset: str, snapshot_date: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT status FROM bulk_downloads WHERE jurisdiction=? AND dataset=? AND snapshot_date=?",
                (jurisdiction, dataset, snapshot_date),
            ).fetchone()
        return row[0] if row else None

    def start(self, jurisdiction: str, dataset: str, snapshot_date: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO bulk_downloads (jurisdiction, dataset, snapshot_date, status, started_at)
                VALUES (?, ?, ?, 'downloading', ?)
                ON CONFLICT (jurisdiction, dataset, snapshot_date)
                DO UPDATE SET status = 'downloading', started_at = excluded.started_at,
                              finished_at = NULL, error_message = NULL
                """,
                (jurisdiction, dataset, snapshot_date, _now()),
            )
            conn.commit()

    def mark_verified(
        self,
        jurisdiction: str,
        dataset: str,
        snapshot_date: str,
        *,
        archive_key: str,
        sha256: str,
        byte_size: int,
        row_count: int,
        http_status: int,
    ) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE bulk_downloads
                SET status = 'verified', archive_key = ?, sha256 = ?, byte_size = ?,
                    row_count = ?, http_status = ?, finished_at = ?, error_message = NULL
                WHERE jurisdiction = ? AND dataset = ? AND snapshot_date = ?
                """,
                (archive_key, sha256, byte_size, row_count, http_status, _now(), jurisdiction, dataset, snapshot_date),
            )
            conn.commit()

    def get_verified_row_count(self, jurisdiction: str, dataset: str, snapshot_date: str) -> int | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT row_count FROM bulk_downloads "
                "WHERE jurisdiction=? AND dataset=? AND snapshot_date=? AND status='verified'",
                (jurisdiction, dataset, snapshot_date),
            ).fetchone()
        return row[0] if row else None

    def mark_failed(
        self,
        jurisdiction: str,
        dataset: str,
        snapshot_date: str,
        *,
        error_message: str,
        http_status: int | None = None,
    ) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE bulk_downloads
                SET status = 'failed', error_message = ?, http_status = ?, finished_at = ?
                WHERE jurisdiction = ? AND dataset = ? AND snapshot_date = ?
                """,
                (error_message, http_status, _now(), jurisdiction, dataset, snapshot_date),
            )
            conn.commit()

    def get_latest_verified_snapshot(self, jurisdiction: str, dataset: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT max(snapshot_date) FROM bulk_downloads WHERE jurisdiction=? AND dataset=? AND status='verified'",
                (jurisdiction, dataset),
            ).fetchone()
        return row[0] if row and row[0] else None

    # --- PDF downloads: keyed by URL (globally unique), not (jurisdiction, dataset, snapshot_date) ---

    def get_pdf_status(self, url: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT status FROM pdf_downloads WHERE url = ?", (url,)).fetchone()
        return row[0] if row else None

    def get_pdf_download_info(self, url: str) -> tuple[str, str, int] | None:
        """Returns (archive_key, sha256, byte_size) for a verified download, or
        None. The bridge fara-extract uses to locate an already-downloaded PDF
        without fara-ingest ever needing a Postgres dependency."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT archive_key, sha256, byte_size FROM pdf_downloads WHERE url = ? AND status = 'verified'",
                (url,),
            ).fetchone()
        return tuple(row) if row else None

    def start_pdf(self, url: str, *, registration_number: int, document_type: str, date_stamped: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO pdf_downloads (url, registration_number, document_type, date_stamped, status, started_at)
                VALUES (?, ?, ?, ?, 'downloading', ?)
                ON CONFLICT (url) DO UPDATE SET
                    status = 'downloading', started_at = excluded.started_at,
                    finished_at = NULL, error_message = NULL
                """,
                (url, registration_number, document_type, date_stamped, _now()),
            )
            conn.commit()

    def mark_pdf_verified(self, url: str, *, archive_key: str, sha256: str, byte_size: int, http_status: int) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE pdf_downloads
                SET status = 'verified', archive_key = ?, sha256 = ?, byte_size = ?,
                    http_status = ?, finished_at = ?, error_message = NULL
                WHERE url = ?
                """,
                (archive_key, sha256, byte_size, http_status, _now(), url),
            )
            conn.commit()

    def mark_pdf_unavailable(self, url: str, *, http_status: int) -> None:
        """A confirmed 404 — some listed URLs 404 despite being in the CSV
        (docs/api-notes.md) — a known gap, terminal, never auto-retried."""
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE pdf_downloads SET status = 'unavailable', http_status = ?, finished_at = ? WHERE url = ?",
                (http_status, _now(), url),
            )
            conn.commit()

    def mark_pdf_too_large(self, url: str, *, byte_size: int | None) -> None:
        """Confirmed live: some 'Informational Materials' filings are enormous
        multimedia dissemination copies (one observed at 2.3 GB, several at
        100-220 MB) — a deliberate, terminal skip, not a failure, so a weekly
        job's runtime/storage stay predictable (docs/api-notes.md)."""
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE pdf_downloads SET status = 'too_large', byte_size = ?, finished_at = ? WHERE url = ?",
                (byte_size, _now(), url),
            )
            conn.commit()

    def mark_pdf_failed(self, url: str, *, error_message: str, http_status: int | None = None) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE pdf_downloads SET status = 'failed', error_message = ?, http_status = ?, finished_at = ? "
                "WHERE url = ?",
                (error_message, http_status, _now(), url),
            )
            conn.commit()
