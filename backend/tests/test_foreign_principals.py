from __future__ import annotations


def test_list_foreign_principals(client, seeded):
    resp = client.get("/api/foreign-principals")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_get_foreign_principal(client, seeded):
    resp = client.get(f"/api/foreign-principals/{seeded['foreign_principal_id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["foreign_principal_name"] == "The Government of Iceland"
    assert body["registrant_name"] == "Brownstein Hyatt Farber Schreck, LLP"
    assert body["registrant_status"] == "active"


def test_list_foreign_principals_includes_registrant_name(client, seeded):
    resp = client.get("/api/foreign-principals", params={"group_by_name": "false"})
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["registrant_name"] == "Brownstein Hyatt Farber Schreck, LLP"
    assert item["registrant_status"] == "active"


def test_list_foreign_principals_grouped_by_default(client, seeded):
    resp = client.get("/api/foreign-principals")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["foreign_principal_name"] == "The Government of Iceland"
    assert item["registrant_count"] == 1
    assert item["sample_registrant_names"] == ["Brownstein Hyatt Farber Schreck, LLP"]
    assert "registrant_name" not in item


def test_list_foreign_principals_grouped_collapses_multiple_registrants(client, conn, seeded):
    conn.execute(
        "INSERT INTO registrants "
        "(jurisdiction, registration_number, name, registration_date, status, source_row_hash, "
        " first_seen_snapshot_date, last_seen_snapshot_date) "
        "VALUES ('fara', 6001, 'Second Firm LLC', '2021-01-01', 'active', 'h10', '2026-01-01', '2026-01-01') "
        "RETURNING registrant_id"
    )
    second_registrant_id = conn.execute("SELECT registrant_id FROM registrants WHERE registration_number = 6001").fetchone()[
        "registrant_id"
    ]
    conn.execute(
        "INSERT INTO foreign_principals "
        "(jurisdiction, registrant_id, registration_number, foreign_principal_name, country_raw, "
        " registration_date, source_row_hash, first_seen_snapshot_date, last_seen_snapshot_date) "
        "VALUES ('fara', %s, 6001, 'the government of iceland', 'ICELAND', '2021-01-01', 'h11', "
        " '2026-01-01', '2026-01-01')",
        (second_registrant_id,),
    )
    resp = client.get("/api/foreign-principals")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["registrant_count"] == 2


def test_list_foreign_principals_filters_by_status(client, seeded):
    resp = client.get("/api/foreign-principals", params={"status": "terminated"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    resp = client.get("/api/foreign-principals", params={"status": "active"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_list_foreign_principals_sort_name_asc(client, seeded):
    resp = client.get("/api/foreign-principals", params={"sort": "name_asc"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


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
