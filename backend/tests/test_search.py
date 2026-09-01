from __future__ import annotations


def test_search_across_entity_types(client, seeded):
    resp = client.get("/api/search", params={"q": "iceland"})
    assert resp.status_code == 200
    types = {r["entity_type"] for r in resp.json()}
    assert "foreign_principal" in types
    assert "country" in types


def test_search_finds_country(client, seeded):
    resp = client.get("/api/search", params={"q": "iceland", "type": "country"})
    assert resp.status_code == 200
    results = resp.json()
    assert results == [
        {
            "entity_type": "country", "entity_id": None, "label": "ICELAND", "detail": None,
            "registration_number": None, "group_count": None, "active_count": None,
        }
    ]


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


def test_search_groups_registrants_by_normalized_name(client, conn, seeded):
    # A second registration under the same name (whitespace-variant), distinct
    # registration_number/status — mirrors the real "Ballard Partners" /
    # "Podesta Group, Inc." re-registration cases found live.
    conn.execute(
        "INSERT INTO registrants "
        "(jurisdiction, registration_number, name, registration_date, status, source_row_hash, "
        " first_seen_snapshot_date, last_seen_snapshot_date) "
        "VALUES ('fara', 9999, 'Brownstein  Hyatt Farber Schreck, LLP', '2017-01-01', 'terminated', 'h9', "
        " '2026-01-01', '2026-01-01')"
    )
    resp = client.get("/api/search", params={"q": "brownstein", "type": "registrant"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["group_count"] == 2
    assert results[0]["active_count"] == 1


def test_search_does_not_starve_foreign_principal_hits(client, conn, seeded):
    # Flood registrant matches so the old fixed-order concatenation would have
    # crowded the foreign_principal hit out of a small overall limit.
    for i in range(10):
        conn.execute(
            "INSERT INTO registrants "
            "(jurisdiction, registration_number, name, registration_date, status, source_row_hash, "
            " first_seen_snapshot_date, last_seen_snapshot_date) "
            f"VALUES ('fara', {9000 + i}, 'Iceland Advisors {i}', '2020-01-01', 'active', 'hflood{i}', "
            " '2026-01-01', '2026-01-01')"
        )
    resp = client.get("/api/search", params={"q": "iceland", "limit": 8})
    assert resp.status_code == 200
    types = {r["entity_type"] for r in resp.json()}
    assert "foreign_principal" in types
    assert "country" in types
