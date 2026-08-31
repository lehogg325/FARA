from __future__ import annotations


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_document_types(client, seeded):
    resp = client.get("/api/document-types")
    assert resp.status_code == 200
    codes = {d["document_type_code"] for d in resp.json()}
    assert codes == {"EXHIBIT_AB"}


def test_countries(client, seeded):
    resp = client.get("/api/countries")
    assert resp.status_code == 200
    assert resp.json() == [{"country_name": "ICELAND"}]


def test_meta_reports_coverage_and_data_as_of(client, seeded):
    resp = client.get("/api/meta")
    assert resp.status_code == 200
    body = resp.json()
    assert body["jurisdiction"] == "fara"
    assert body["data_as_of"] == "2026-08-01"
    assert body["datasets"][0]["dataset"] == "registrants"

    coverage_by_stage = {c["stage"]: c for c in body["extraction_coverage"]}
    # The seeded document has succeeded fields_llm extraction and one eligible
    # EXHIBIT_AB document with text — coverage should reflect exactly that.
    assert coverage_by_stage["fields_llm"]["succeeded_count"] == 1
    assert coverage_by_stage["fields_llm"]["eligible_count"] == 1
