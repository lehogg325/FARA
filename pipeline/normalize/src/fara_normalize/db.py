from __future__ import annotations

import os

import psycopg

DEFAULT_LOCAL_DSN = "postgresql://fara:fara@localhost:5434/fara"


def get_connection(dsn: str | None = None) -> psycopg.Connection:
    return psycopg.connect(dsn or os.environ.get("DATABASE_URL", DEFAULT_LOCAL_DSN))
