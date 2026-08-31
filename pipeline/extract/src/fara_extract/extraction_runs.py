from __future__ import annotations

from datetime import datetime, timezone

import psycopg


def already_succeeded(conn: psycopg.Connection, registrant_doc_id: int, stage: str, extractor_version: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM extraction_runs WHERE registrant_doc_id = %s AND stage = %s "
            "AND extractor_version = %s AND status = 'succeeded'",
            (registrant_doc_id, stage, extractor_version),
        )
        return cur.fetchone() is not None


def record_run(
    conn: psycopg.Connection,
    registrant_doc_id: int,
    stage: str,
    extractor_version: str,
    status: str,
    *,
    error_message: str | None = None,
) -> None:
    """Idempotent: re-running the same (doc, stage, version) just updates the
    row, so re-processing with an improved parser version is a normal
    operation, never a special migration."""
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO extraction_runs
                (registrant_doc_id, stage, extractor_version, status, started_at, finished_at, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (registrant_doc_id, stage, extractor_version) DO UPDATE SET
                status = excluded.status, finished_at = excluded.finished_at, error_message = excluded.error_message
            """,
            (registrant_doc_id, stage, extractor_version, status, now, now, error_message),
        )
