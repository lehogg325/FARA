from __future__ import annotations

import psycopg

from fara_backend.schemas import CountryGraph, GraphEdge, GraphNode

# Defensive backstop, not a routine truncation — the graph is scoped to
# registrants with actual reportable-contact activity (below), which keeps
# even the busiest country's real network small.
NODE_CAP = 1500


def _norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


def build_country_graph(conn: psycopg.Connection, jurisdiction: str, country_name: str) -> CountryGraph:
    # Confirmed live (docs/phase2.md): a populous country's foreign-principal
    # roster (e.g. China: 277) is dominated by registrants with nothing beyond
    # a bare "represents" relationship — no contact or contribution activity
    # at all. That full roster is already served by /registrants and
    # /foreign-principals; this graph is specifically the *reportable-contact*
    # network the plan asked for, so it's scoped to registrants that actually
    # have a contact or contribution row, not every registration on file.
    active_registrant_ids_row = conn.execute(
        """
        SELECT array_agg(DISTINCT rd.registrant_id) AS ids
        FROM registrant_docs rd
        JOIN foreign_principals fp ON fp.registrant_id = rd.registrant_id AND fp.jurisdiction = rd.jurisdiction
        WHERE fp.jurisdiction = %(j)s AND fp.country_raw = %(country)s
          AND (
              EXISTS (SELECT 1 FROM reportable_contacts rc WHERE rc.registrant_doc_id = rd.registrant_doc_id)
              OR EXISTS (
                  SELECT 1 FROM document_extracted_fields def
                  WHERE def.registrant_doc_id = rd.registrant_doc_id AND def.field_key LIKE 'political_contribution[%%'
              )
          )
        """,
        {"j": jurisdiction, "country": country_name},
    ).fetchone()
    registrant_ids = active_registrant_ids_row["ids"] or []

    fps = (
        conn.execute(
            "SELECT foreign_principal_id, registrant_id, foreign_principal_name, registration_number "
            "FROM foreign_principals WHERE jurisdiction = %(j)s AND country_raw = %(country)s "
            "AND registrant_id = ANY(%(ids)s)",
            {"j": jurisdiction, "country": country_name, "ids": registrant_ids},
        ).fetchall()
        if registrant_ids
        else []
    )
    registrants = (
        conn.execute(
            "SELECT registrant_id, name, registration_number FROM registrants WHERE registrant_id = ANY(%s)",
            (registrant_ids,),
        ).fetchall()
        if registrant_ids
        else []
    )
    contacts = (
        conn.execute(
            """
            SELECT rc.registrant_doc_id, rd.registrant_id, rc.contact_date, rc.contact_date_raw,
                   rc.contact_name_raw, rc.purpose
            FROM reportable_contacts rc
            JOIN registrant_docs rd ON rd.registrant_doc_id = rc.registrant_doc_id
            WHERE rd.registrant_id = ANY(%s)
            """,
            (registrant_ids,),
        ).fetchall()
        if registrant_ids
        else []
    )
    contributions = (
        conn.execute(
            """
            SELECT def.registrant_doc_id, rd.registrant_id, def.field_value_text,
                   def.field_value_numeric, def.field_value_date
            FROM document_extracted_fields def
            JOIN registrant_docs rd ON rd.registrant_doc_id = def.registrant_doc_id
            WHERE rd.registrant_id = ANY(%s) AND def.field_key LIKE 'political_contribution[%%'
            """,
            (registrant_ids,),
        ).fetchall()
        if registrant_ids
        else []
    )

    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    for r in registrants:
        node_id = f"registrant:{r['registrant_id']}"
        nodes[node_id] = GraphNode(
            id=node_id, node_type="registrant", label=r["name"], registration_number=r["registration_number"]
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

    for c in contacts:
        source = f"registrant:{c['registrant_id']}"
        if source not in nodes or not c["contact_name_raw"]:
            continue
        target = f"contact:{_norm(c['contact_name_raw'])}"
        if target not in nodes:
            nodes[target] = GraphNode(id=target, node_type="contact", label=c["contact_name_raw"])
        edges.append(
            GraphEdge(
                source=source, target=target, edge_type="contacted", registrant_doc_id=c["registrant_doc_id"],
                edge_date=c["contact_date"], detail=c["purpose"],
            )
        )

    for con in contributions:
        source = f"registrant:{con['registrant_id']}"
        if source not in nodes or not con["field_value_text"]:
            continue
        target = f"recipient:{_norm(con['field_value_text'])}"
        if target not in nodes:
            nodes[target] = GraphNode(id=target, node_type="recipient", label=con["field_value_text"])
        edges.append(
            GraphEdge(
                source=source, target=target, edge_type="contributed", registrant_doc_id=con["registrant_doc_id"],
                edge_date=con["field_value_date"], amount=con["field_value_numeric"], detail=con["field_value_text"],
            )
        )

    node_list = list(nodes.values())
    truncated = len(node_list) > NODE_CAP
    if truncated:
        kept_ids = {n.id for n in node_list[:NODE_CAP]}
        node_list = node_list[:NODE_CAP]
        edges = [e for e in edges if e.source in kept_ids and e.target in kept_ids]

    return CountryGraph(country_name=country_name, nodes=node_list, edges=edges, truncated=truncated)
