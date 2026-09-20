from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DEFAULT_LOCAL_DSN = "postgresql://fara:fara@localhost:5434/fara"

# Module-level so a single pool survives across warm serverless invocations
# (Vercel) instead of opening a fresh connection per request; sized small
# because the real concurrency limit lives on the hosted Postgres's own
# connection pooler (docs — Deployment), not here.
_pool: ConnectionPool | None = None


def _dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_LOCAL_DSN)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            _dsn(),
            min_size=1,
            max_size=5,
            # Verify a connection still works before handing it out — without this,
            # a warm instance can hand out a connection that died while idle (e.g.
            # after a DB restart), surfacing as a request-level error instead of
            # being caught and replaced here.
            check=ConnectionPool.check_connection,
            # prepare_threshold=None disables psycopg's server-side prepared
            # statements — required in production, where DATABASE_URL points
            # at Supabase's transaction-mode pooler (docs/deploy.md): that
            # pooler hands out a different backend connection per statement,
            # so a server-side prepare from one statement doesn't survive to
            # the next and errors with "prepared statement does not exist".
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
            open=True,
        )
    return _pool


def get_db() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as conn:
        # A per-connect `options=-c statement_timeout=...` doesn't reach the
        # server through Supabase's transaction-mode pooler (verified live —
        # it silently keeps its own default instead), but `SET` issued as the
        # first statement of each request's own transaction does, the same
        # way prepare_threshold=None above works around that pooler's other
        # session-scoping limit. A backstop, not a routine limit (matching
        # graph.py's BACKBONE_CAP/EXPANSION_CAP pattern) — every real query
        # here finishes in well under a second (the worst measured, the
        # unfiltered /api/foreign-principals grouped listing, is ~300ms
        # against today's data), so 10s only ever fires for something
        # pathological. With only 5 connections in this pool, a handful of
        # slow/abusive concurrent requests to a public, unauthenticated
        # endpoint could otherwise exhaust it and start queuing or timing out
        # every other request to the site.
        conn.execute("SET statement_timeout = '10s'")
        yield conn
