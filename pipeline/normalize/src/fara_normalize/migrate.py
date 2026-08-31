from __future__ import annotations

from pathlib import Path

import psycopg

_SCHEMA_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
"""


def _migrations_dir() -> Path:
    return Path(__file__).parent / "migrations"


def migrate(conn: psycopg.Connection) -> list[str]:
    """Applies pending .sql files in migrations/ in filename order, each in its
    own transaction, recording what's applied in schema_migrations. Homegrown
    rather than a framework — a handful of linear migrations don't need one.
    """
    with conn.cursor() as cur:
        cur.execute(_SCHEMA_MIGRATIONS_TABLE)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations")
        already_applied = {row[0] for row in cur.fetchall()}

    applied_now = []
    for path in sorted(_migrations_dir().glob("*.sql")):
        if path.name in already_applied:
            continue
        sql = path.read_text(encoding="utf-8")
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
        conn.commit()
        applied_now.append(path.name)
    return applied_now
