from __future__ import annotations

import psycopg


def get_registrant_id(conn: psycopg.Connection, jurisdiction: str, registration_number: int) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT registrant_id FROM registrants WHERE jurisdiction = %s AND registration_number = %s",
            (jurisdiction, registration_number),
        )
        row = cur.fetchone()
    return row[0] if row else None


def load_registrant_id_map(conn: psycopg.Connection, jurisdiction: str) -> dict[int, int]:
    """Loads the full registration_number -> registrant_id mapping once. At real
    scale (100K+ rows in registrant_docs/foreign_principals/short_forms), doing
    this lookup as a per-row round trip is too slow — confirmed live, a
    per-row-query load of registrant_docs didn't finish in 2 minutes; the full
    map is a few thousand rows and fits trivially in memory.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT registration_number, registrant_id FROM registrants WHERE jurisdiction = %s", (jurisdiction,)
        )
        return dict(cur.fetchall())
