from __future__ import annotations


def test_list_countries_includes_counts(client, seeded):
    resp = client.get("/api/countries")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [{"country_name": "ICELAND", "registrant_count": 1, "foreign_principal_count": 1}]


def test_get_country_detail(client, seeded):
    resp = client.get("/api/countries/ICELAND")
    assert resp.status_code == 200
    body = resp.json()
    assert body["active_registrant_count"] == 1
    assert body["total_registrant_count"] == 1
    assert body["foreign_principal_count"] == 1
    assert body["contact_count"] == 1
    assert body["contribution_count"] == 1
    assert body["contribution_total"] == 2500.0


def test_get_country_detail_404_for_unknown_country(client, seeded):
    resp = client.get("/api/countries/NARNIA")
    assert resp.status_code == 404


def test_country_topics(client, seeded):
    resp = client.get("/api/countries/ICELAND/topics")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [{"topic": "diplomacy_bilateral", "topic_label": "Diplomatic & Bilateral Relations", "document_count": 1}]


def test_country_topics_empty_for_country_with_no_topics(client, seeded):
    resp = client.get("/api/countries/NARNIA/topics")
    assert resp.status_code == 200
    assert resp.json() == []


def test_topics_taxonomy_list(client, seeded):
    resp = client.get("/api/topics")
    assert resp.status_code == 200
    assert {"topic": "diplomacy_bilateral", "topic_label": "Diplomatic & Bilateral Relations"} in resp.json()


def test_country_graph_is_backbone_only(client, seeded):
    resp = client.get("/api/countries/ICELAND/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["country_name"] == "ICELAND"
    assert body["omitted_registrant_count"] == 0

    node_types = {n["node_type"] for n in body["nodes"]}
    assert node_types == {"foreign_principal", "registrant"}  # no contact/recipient nodes by default

    edge_types = {e["edge_type"] for e in body["edges"]}
    assert edge_types == {"represents"}

    registrant_node = next(n for n in body["nodes"] if n["node_type"] == "registrant")
    assert registrant_node["registration_number"] == 5870
    assert registrant_node["contact_count"] == 1
    assert registrant_node["contribution_count"] == 1
    assert registrant_node["contribution_total"] == 2500.0


def test_country_graph_empty_for_country_with_no_data(client, seeded):
    resp = client.get("/api/countries/NARNIA/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["nodes"] == []
    assert body["edges"] == []
    assert body["omitted_registrant_count"] == 0


def test_expand_registrant_returns_contact_and_recipient_nodes(client, seeded):
    resp = client.get(f"/api/countries/ICELAND/graph/registrants/{seeded['registrant_id']}/expand")
    assert resp.status_code == 200
    body = resp.json()
    assert body["registrant_id"] == seeded["registrant_id"]

    node_types = {n["node_type"] for n in body["nodes"]}
    assert node_types == {"contact", "recipient"}

    edge_types = {e["edge_type"] for e in body["edges"]}
    assert edge_types == {"contacted", "contributed"}

    contact_edge = next(e for e in body["edges"] if e["edge_type"] == "contacted")
    assert contact_edge["detail"] == "U.S.-Iceland relations"

    contribution_edge = next(e for e in body["edges"] if e["edge_type"] == "contributed")
    assert contribution_edge["amount"] == 2500.0


def test_expand_registrant_404_when_not_linked_to_country(client, seeded):
    resp = client.get(f"/api/countries/NARNIA/graph/registrants/{seeded['registrant_id']}/expand")
    assert resp.status_code == 404


def test_expand_registrant_404_for_unknown_registrant(client, seeded):
    resp = client.get("/api/countries/ICELAND/graph/registrants/999999/expand")
    assert resp.status_code == 404


def test_top_contacts(client, seeded):
    resp = client.get("/api/countries/ICELAND/top-contacts")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [
        {
            "contact_name_raw": "Rachel Oglesby, Dept of Education",
            "occurrence_count": 1,
            "sample_registrant_doc_ids": [seeded["registrant_doc_id"]],
        }
    ]


def test_top_recipients(client, seeded):
    resp = client.get("/api/countries/ICELAND/top-recipients")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [
        {
            "recipient_raw": "Friends of a Senator",
            "occurrence_count": 1,
            "total_amount": 2500.0,
            "sample_registrant_doc_ids": [seeded["registrant_doc_id"]],
        }
    ]


def test_top_contacts_empty_for_country_with_no_data(client, seeded):
    resp = client.get("/api/countries/NARNIA/top-contacts")
    assert resp.status_code == 200
    assert resp.json() == []
