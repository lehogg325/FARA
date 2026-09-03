from __future__ import annotations

import psycopg

from fara_backend.schemas import CountryGraph, GraphEdge, GraphNode, RegistrantExpansion, TopContact, TopRecipient
from fara_backend.text_normalize import NORM_SQL, norm

# Comfortably above every real country's backbone measured live (docs/phase2.md) —
# Japan, the busiest, is 136 registrant+foreign-principal nodes. A genuine backstop,
# not a routine truncation; when it does trigger, registrants are kept by activity
# (contact_count + contribution_count), not list order.
BACKBONE_CAP = 150

# A single registrant's own contact/recipient activity is inherently bounded (even
# the largest real PR-campaign filing found live has 105 contact rows) — this is a
# defensive backstop, not an expected truncation.
EXPANSION_CAP = 500


def _registrant_activity(conn: psycopg.Connection, registrant_ids: list[int]) -> dict[int, dict]:
    """contact_count / contribution_count / contribution_total per registrant —
    two separate grouped queries, not one multi-join, so that joining both
    reportable_contacts and document_extracted_fields on the same doc doesn't
    fan out and double-count/double-sum either side."""
    if not registrant_ids:
        return {}

    stats: dict[int, dict] = {rid: {"contact_count": 0, "contribution_count": 0, "contribution_total": None} for rid in registrant_ids}

    for row in conn.execute(
        """
        SELECT rd.registrant_id, count(*) AS n
        FROM reportable_contacts rc
        JOIN registrant_docs rd ON rd.registrant_doc_id = rc.registrant_doc_id
        WHERE rd.registrant_id = ANY(%s)
        GROUP BY rd.registrant_id
        """,
        (registrant_ids,),
    ).fetchall():
        stats[row["registrant_id"]]["contact_count"] = row["n"]

    for row in conn.execute(
        """
        SELECT rd.registrant_id, count(*) AS n, sum(def.field_value_numeric) AS total
        FROM document_extracted_fields def
        JOIN registrant_docs rd ON rd.registrant_doc_id = def.registrant_doc_id
        WHERE rd.registrant_id = ANY(%s) AND def.field_key LIKE 'political_contribution[%%'
        GROUP BY rd.registrant_id
        """,
        (registrant_ids,),
    ).fetchall():
        stats[row["registrant_id"]]["contribution_count"] = row["n"]
        stats[row["registrant_id"]]["contribution_total"] = row["total"]

    return stats


def _active_registrant_ids(conn: psycopg.Connection, jurisdiction: str, country_name: str) -> list[int]:
    # Checks existence once per candidate registrant (deduplicated up front), not
    # once per document — the previous shape joined in every document a matching
    # registrant ever filed and ran both EXISTS checks per document row, so cost
    # scaled with registrants x documents-per-registrant instead of registrants alone
    # (measured: 284ms/218k buffers -> 28ms/11k buffers for FARA's busiest country).
    row = conn.execute(
        """
        WITH candidate_registrants AS (
            SELECT DISTINCT registrant_id
            FROM foreign_principals
            WHERE jurisdiction = %(j)s AND country_raw = %(country)s
        )
        SELECT array_agg(cr.registrant_id) AS ids
        FROM candidate_registrants cr
        WHERE EXISTS (
            SELECT 1 FROM registrant_docs rd
            JOIN reportable_contacts rc ON rc.registrant_doc_id = rd.registrant_doc_id
            WHERE rd.registrant_id = cr.registrant_id AND rd.jurisdiction = %(j)s
        ) OR EXISTS (
            SELECT 1 FROM registrant_docs rd
            JOIN document_extracted_fields def ON def.registrant_doc_id = rd.registrant_doc_id
            WHERE rd.registrant_id = cr.registrant_id AND rd.jurisdiction = %(j)s
              AND def.field_key LIKE %(fk)s
        )
        """,
        {"j": jurisdiction, "country": country_name, "fk": "political_contribution[%"},
    ).fetchone()
    return row["ids"] or []


def build_country_graph(conn: psycopg.Connection, jurisdiction: str, country_name: str) -> CountryGraph:
    all_ids = _active_registrant_ids(conn, jurisdiction, country_name)
    activity = _registrant_activity(conn, all_ids)

    ranked = sorted(all_ids, key=lambda rid: -(activity[rid]["contact_count"] + activity[rid]["contribution_count"]))
    shown_ids = ranked[:BACKBONE_CAP]
    omitted_registrant_count = max(0, len(ranked) - BACKBONE_CAP)

    registrants = (
        conn.execute(
            "SELECT registrant_id, name, registration_number FROM registrants WHERE registrant_id = ANY(%s)",
            (shown_ids,),
        ).fetchall()
        if shown_ids
        else []
    )
    fps = (
        conn.execute(
            "SELECT foreign_principal_id, registrant_id, foreign_principal_name, registration_number "
            "FROM foreign_principals WHERE jurisdiction = %(j)s AND country_raw = %(country)s "
            "AND registrant_id = ANY(%(ids)s)",
            {"j": jurisdiction, "country": country_name, "ids": shown_ids},
        ).fetchall()
        if shown_ids
        else []
    )

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    for r in registrants:
        node_id = f"registrant:{r['registrant_id']}"
        a = activity[r["registrant_id"]]
        nodes[node_id] = GraphNode(
            id=node_id, node_type="registrant", label=r["name"], registration_number=r["registration_number"],
            contact_count=a["contact_count"], contribution_count=a["contribution_count"],
            contribution_total=a["contribution_total"],
        )

    for fp in fps:
        node_id = f"fp:{fp['foreign_principal_id']}"
        nodes[node_id] = GraphNode(
            id=node_id, node_type="foreign_principal", label=fp["foreign_principal_name"],
            registration_number=fp["registration_number"],
        )
        target = f"registrant:{fp['registrant_id']}"
        if target in nodes:
            edges.append(GraphEdge(source=node_id, target=target, edge_type="represents", registrant_doc_id=None))

    return CountryGraph(
        country_name=country_name, nodes=list(nodes.values()), edges=edges,
        omitted_registrant_count=omitted_registrant_count,
    )


def build_registrant_expansion(conn: psycopg.Connection, registrant_id: int) -> RegistrantExpansion:
    source = f"registrant:{registrant_id}"
    contacts = conn.execute(
        """
        SELECT rc.registrant_doc_id, rc.contact_date, rc.contact_name_raw, rc.purpose
        FROM reportable_contacts rc
        JOIN registrant_docs rd ON rd.registrant_doc_id = rc.registrant_doc_id
        WHERE rd.registrant_id = %s
        LIMIT %s
        """,
        (registrant_id, EXPANSION_CAP),
    ).fetchall()
    contributions = conn.execute(
        """
        SELECT def.registrant_doc_id, def.field_value_text, def.field_value_numeric, def.field_value_date
        FROM document_extracted_fields def
        JOIN registrant_docs rd ON rd.registrant_doc_id = def.registrant_doc_id
        WHERE rd.registrant_id = %s AND def.field_key LIKE 'political_contribution[%%'
        LIMIT %s
        """,
        (registrant_id, EXPANSION_CAP),
    ).fetchall()

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    for c in contacts:
        if not c["contact_name_raw"]:
            continue
        target = f"contact:{norm(c['contact_name_raw'])}"
        if target not in nodes:
            nodes[target] = GraphNode(id=target, node_type="contact", label=c["contact_name_raw"])
        edges.append(
            GraphEdge(
                source=source, target=target, edge_type="contacted", registrant_doc_id=c["registrant_doc_id"],
                edge_date=c["contact_date"], detail=c["purpose"],
            )
        )

    for con in contributions:
        if not con["field_value_text"]:
            continue
        target = f"recipient:{norm(con['field_value_text'])}"
        if target not in nodes:
            nodes[target] = GraphNode(id=target, node_type="recipient", label=con["field_value_text"])
        edges.append(
            GraphEdge(
                source=source, target=target, edge_type="contributed", registrant_doc_id=con["registrant_doc_id"],
                edge_date=con["field_value_date"], amount=con["field_value_numeric"], detail=con["field_value_text"],
            )
        )

    return RegistrantExpansion(registrant_id=registrant_id, nodes=list(nodes.values()), edges=edges)


def top_contacts(conn: psycopg.Connection, jurisdiction: str, country_name: str, limit: int) -> list[TopContact]:
    rows = conn.execute(
        f"""
        SELECT (array_agg(contact_name_raw))[1] AS contact_name_raw, count(*) AS occurrence_count,
               (array_agg(DISTINCT registrant_doc_id))[1:5] AS sample_registrant_doc_ids
        FROM (
            SELECT rc.registrant_doc_id, rc.contact_name_raw, {NORM_SQL.format(col='rc.contact_name_raw')} AS norm_name
            FROM reportable_contacts rc
            JOIN registrant_docs rd ON rd.registrant_doc_id = rc.registrant_doc_id
            JOIN foreign_principals fp ON fp.registrant_id = rd.registrant_id
            WHERE fp.jurisdiction = %(j)s AND fp.country_raw = %(country)s
        ) t
        GROUP BY norm_name
        ORDER BY occurrence_count DESC
        LIMIT %(limit)s
        """,
        {"j": jurisdiction, "country": country_name, "limit": limit},
    ).fetchall()
    return [TopContact(**r) for r in rows]


def top_recipients(conn: psycopg.Connection, jurisdiction: str, country_name: str, limit: int) -> list[TopRecipient]:
    rows = conn.execute(
        f"""
        SELECT (array_agg(field_value_text))[1] AS recipient_raw, count(*) AS occurrence_count,
               sum(field_value_numeric) AS total_amount,
               (array_agg(DISTINCT registrant_doc_id))[1:5] AS sample_registrant_doc_ids
        FROM (
            SELECT def.registrant_doc_id, def.field_value_text, def.field_value_numeric,
                   {NORM_SQL.format(col='def.field_value_text')} AS norm_name
            FROM document_extracted_fields def
            JOIN registrant_docs rd ON rd.registrant_doc_id = def.registrant_doc_id
            JOIN foreign_principals fp ON fp.registrant_id = rd.registrant_id
            WHERE fp.jurisdiction = %(j)s AND fp.country_raw = %(country)s AND def.field_key LIKE 'political_contribution[%%'
        ) t
        GROUP BY norm_name
        ORDER BY occurrence_count DESC
        LIMIT %(limit)s
        """,
        {"j": jurisdiction, "country": country_name, "limit": limit},
    ).fetchall()
    return [TopRecipient(**r) for r in rows]
