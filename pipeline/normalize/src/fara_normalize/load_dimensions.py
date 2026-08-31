from __future__ import annotations

import csv
from importlib.resources import files

import psycopg

JURISDICTION_SEED = [
    ("fara", "US Federal — Foreign Agents Registration Act", "federal"),
]


def _seed_csv_rows(filename: str) -> list[dict]:
    path = files("fara_ingest.sources.fara").joinpath("seed_data", filename)
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_jurisdictions(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO jurisdictions (jurisdiction, display_name, level) VALUES (%s, %s, %s) "
            "ON CONFLICT (jurisdiction) DO NOTHING",
            JURISDICTION_SEED,
        )
    return len(JURISDICTION_SEED)


def load_document_types(conn: psycopg.Connection) -> int:
    rows = _seed_csv_rows("document_types.csv")
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO document_types (jurisdiction, document_type_code, document_type_label) "
            "VALUES (%(jurisdiction)s, %(document_type_code)s, %(document_type_label)s) "
            "ON CONFLICT (jurisdiction, document_type_code) "
            "DO UPDATE SET document_type_label = excluded.document_type_label",
            rows,
        )
    return len(rows)


def load_countries(conn: psycopg.Connection) -> int:
    rows = _seed_csv_rows("countries.csv")
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO countries (jurisdiction, country_name) VALUES (%(jurisdiction)s, %(country_name)s) "
            "ON CONFLICT (jurisdiction, country_name) DO NOTHING",
            rows,
        )
    return len(rows)


def register_observed_country(conn: psycopg.Connection, jurisdiction: str, country_name: str) -> None:
    """Countries aren't FK-enforced (docs/api-notes.md — free text with confirmed
    real anomalies); this auto-registers any value the loaders encounter that
    wasn't in the initial seed, so /api/countries stays complete without ever
    failing a load over an unrecognized country string."""
    if not country_name:
        return
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO countries (jurisdiction, country_name) VALUES (%s, %s) "
            "ON CONFLICT (jurisdiction, country_name) DO NOTHING",
            (jurisdiction, country_name),
        )
