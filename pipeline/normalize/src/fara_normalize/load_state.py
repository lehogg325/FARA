from __future__ import annotations

from datetime import datetime, timezone

import psycopg


def start_load_run(
    conn: psycopg.Connection,
    jurisdiction: str,
    dataset: str,
    snapshot_date: str,
    source_archive_key: str,
    source_row_count: int,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO load_runs (
                jurisdiction, dataset, snapshot_date, source_archive_key,
                source_row_count, loaded_row_count, started_at, status
            ) VALUES (%s, %s, %s, %s, %s, 0, %s, 'running')
            ON CONFLICT (jurisdiction, dataset, snapshot_date) DO UPDATE SET
                source_archive_key = excluded.source_archive_key,
                source_row_count = excluded.source_row_count,
                started_at = excluded.started_at,
                status = 'running',
                finished_at = NULL,
                error_message = NULL
            RETURNING load_run_id
            """,
            (jurisdiction, dataset, snapshot_date, source_archive_key, source_row_count, datetime.now(timezone.utc)),
        )
        return cur.fetchone()[0]


def finish_load_run_succeeded(
    conn: psycopg.Connection, load_run_id: int, loaded_row_count: int, unmapped_row_count: int = 0
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE load_runs SET status = 'succeeded', loaded_row_count = %s, "
            "unmapped_row_count = %s, finished_at = %s WHERE load_run_id = %s",
            (loaded_row_count, unmapped_row_count, datetime.now(timezone.utc), load_run_id),
        )


def finish_load_run_failed(conn: psycopg.Connection, load_run_id: int, error_message: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE load_runs SET status = 'failed', error_message = %s, finished_at = %s WHERE load_run_id = %s",
            (error_message, datetime.now(timezone.utc), load_run_id),
        )
