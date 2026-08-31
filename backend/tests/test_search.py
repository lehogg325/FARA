from __future__ import annotations


def test_search_across_entity_types(client, seeded):
    resp = client.get("/api/search", params={"q": "iceland"})
    assert resp.status_code == 200
    types = {r["entity_type"] for r in resp.json()}
    assert "foreign_principal" in types


def test_search_finds_registrant_by_name(client, seeded):
    resp = client.get("/api/search", params={"q": "brownstein"})
    assert resp.status_code == 200
    results = resp.json()
    assert any(r["entity_type"] == "registrant" and r["registration_number"] == 5870 for r in results)


def test_search_finds_short_form_registrant(client, seeded):
    resp = client.get("/api/search", params={"q": "buckner"})
    assert resp.status_code == 200
    results = resp.json()
    assert any(r["entity_type"] == "short_form_registrant" for r in results)


def test_search_restricts_by_type(client, seeded):
    resp = client.get("/api/search", params={"q": "iceland", "type": "registrant"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_search_no_match(client, seeded):
    resp = client.get("/api/search", params={"q": "zzz_no_such_entity"})
    assert resp.status_code == 200
    assert resp.json() == []
