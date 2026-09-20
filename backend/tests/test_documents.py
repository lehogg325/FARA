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


def test_list_documents_filters_by_registrant_id(client, seeded):
    resp = client.get("/api/documents", params={"registrant_id": seeded["registrant_id"]})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_list_documents_filters_by_country(client, conn, seeded):
    # registrant_docs.foreign_principal_country_raw is denormalized from the
    # DOJ CSV directly and isn't populated by the shared fixture -- set it here.
    conn.execute(
        "UPDATE registrant_docs SET foreign_principal_country_raw = 'ICELAND' WHERE registrant_doc_id = %s",
        (seeded["registrant_doc_id"],),
    )
    conn.commit()

    resp = client.get("/api/documents", params={"country": "ICELAND"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp = client.get("/api/documents", params={"country": "NARNIA"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_list_documents_filters_by_date_range(client, seeded):
    # Fixture's document is date_stamped = 2026-08-13.
    resp = client.get("/api/documents", params={"date_from": "2026-08-01", "date_to": "2026-08-31"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp = client.get("/api/documents", params={"date_from": "2026-09-01"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_list_documents_rejects_malformed_date(client, seeded):
    # date_from/date_to used to be plain str, so a malformed value reached
    # Postgres unvalidated and raised an unhandled InvalidDatetimeFormat (500)
    # instead of a clean 422 from FastAPI's own date parsing.
    resp = client.get("/api/documents", params={"date_from": "not-a-date"})
    assert resp.status_code == 422


def test_get_document(client, seeded):
    resp = client.get(f"/api/documents/{seeded['registrant_doc_id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["registration_number"] == 5870
    assert body["document_type_raw_label"] == "Exhibit AB"
    assert body["url"] == "https://efile.fara.gov/docs/5870-Exhibit-AB-20260813-2.pdf"


def test_get_document_404_for_unknown_document(client, seeded):
    resp = client.get("/api/documents/999999")
    assert resp.status_code == 404


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
