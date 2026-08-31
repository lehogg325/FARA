from __future__ import annotations


def test_list_documents(client, seeded):
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["registrant_doc_id"] == seeded["registrant_doc_id"]


def test_list_documents_filters_by_document_type(client, seeded):
    resp = client.get("/api/documents", params={"document_type": "REGISTRATION_STATEMENT"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_get_document_text(client, seeded):
    resp = client.get(f"/api/documents/{seeded['registrant_doc_id']}/text")
    assert resp.status_code == 200
    body = resp.json()
    assert "strategic advice" in body["extracted_text"]
    assert body["extraction_method"] == "native"


def test_get_document_text_404_for_unknown_document(client, seeded):
    resp = client.get("/api/documents/999999/text")
    assert resp.status_code == 404


def test_get_document_fields(client, seeded):
    resp = client.get(f"/api/documents/{seeded['registrant_doc_id']}/fields")
    assert resp.status_code == 200
    fields = resp.json()
    assert fields[0]["field_key"] == "nature_of_activities"
    assert fields[0]["extraction_method"] == "llm"


def test_search_documents_matches_extracted_text(client, seeded):
    resp = client.get("/api/documents/search", params={"q": "strategic advice"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["registration_number"] == 5870
    assert "strategic" in body["items"][0]["snippet"].lower()


def test_search_documents_no_match(client, seeded):
    resp = client.get("/api/documents/search", params={"q": "nonexistent phrase xyz"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
