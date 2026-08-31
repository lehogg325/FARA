from __future__ import annotations


def test_list_registrants(client, seeded):
    resp = client.get("/api/registrants")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["registration_number"] == 5870


def test_list_registrants_filters_by_status(client, seeded):
    resp = client.get("/api/registrants", params={"status": "terminated"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_get_registrant_includes_related_counts(client, seeded):
    resp = client.get(f"/api/registrants/{seeded['registrant_id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Brownstein Hyatt Farber Schreck, LLP"
    assert body["foreign_principal_count"] == 1
    assert body["short_form_registrant_count"] == 1
    assert body["document_count"] == 1


def test_get_registrant_404(client, seeded):
    resp = client.get("/api/registrants/999999")
    assert resp.status_code == 404


def test_registrant_foreign_principals(client, seeded):
    resp = client.get(f"/api/registrants/{seeded['registrant_id']}/foreign-principals")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["foreign_principal_name"] == "The Government of Iceland"


def test_registrant_short_form_registrants(client, seeded):
    resp = client.get(f"/api/registrants/{seeded['registrant_id']}/short-form-registrants")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["last_name"] == "Buckner"


def test_registrant_documents(client, seeded):
    resp = client.get(f"/api/registrants/{seeded['registrant_id']}/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["document_type_raw_label"] == "Exhibit AB"


def test_registrant_sub_resource_404_for_unknown_registrant(client, seeded):
    resp = client.get("/api/registrants/999999/documents")
    assert resp.status_code == 404
