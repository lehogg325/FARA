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


def test_registrants_by_name_single_registration(client, seeded):
    resp = client.get("/api/registrants/by-name", params={"name": "Brownstein Hyatt Farber Schreck, LLP"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["registrant_count"] == 1
    assert body["registrants"][0]["registration_number"] == 5870


def test_registrants_by_name_groups_re_registrations(client, conn, seeded):
    conn.execute(
        "INSERT INTO registrants "
        "(jurisdiction, registration_number, name, registration_date, status, source_row_hash, "
        " first_seen_snapshot_date, last_seen_snapshot_date) "
        "VALUES ('fara', 4894, '  brownstein hyatt farber schreck, llp  ', '2010-01-01', 'terminated', 'h20', "
        " '2026-01-01', '2026-01-01')"
    )
    resp = client.get("/api/registrants/by-name", params={"name": "Brownstein Hyatt Farber Schreck, LLP"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["registrant_count"] == 2
    statuses = {r["status"] for r in body["registrants"]}
    assert statuses == {"active", "terminated"}


def test_registrants_by_name_404_for_unknown_name(client, seeded):
    resp = client.get("/api/registrants/by-name", params={"name": "No Such Firm"})
    assert resp.status_code == 404
