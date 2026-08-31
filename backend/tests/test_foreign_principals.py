from __future__ import annotations


def test_list_foreign_principals(client, seeded):
    resp = client.get("/api/foreign-principals")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_get_foreign_principal(client, seeded):
    resp = client.get(f"/api/foreign-principals/{seeded['foreign_principal_id']}")
    assert resp.status_code == 200
    assert resp.json()["foreign_principal_name"] == "The Government of Iceland"


def test_get_foreign_principal_404(client, seeded):
    resp = client.get("/api/foreign-principals/999999")
    assert resp.status_code == 404


def test_by_name_groups_registrants(client, seeded):
    resp = client.get("/api/foreign-principals/by-name", params={"name": "The Government of Iceland"})
    assert resp.status_code == 200
    groups = resp.json()
    assert len(groups) == 1
    assert groups[0]["registrant_count"] == 1
    assert groups[0]["registrants"][0]["registration_number"] == 5870


def test_by_name_is_case_insensitive(client, seeded):
    resp = client.get("/api/foreign-principals/by-name", params={"name": "the government of iceland"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_by_name_no_match_returns_empty_list(client, seeded):
    resp = client.get("/api/foreign-principals/by-name", params={"name": "Nonexistent Principal"})
    assert resp.status_code == 200
    assert resp.json() == []
