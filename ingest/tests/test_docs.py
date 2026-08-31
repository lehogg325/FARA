from __future__ import annotations

from datetime import date

import httpx
import respx

from fara_ingest.archive import LocalArchive
from fara_ingest.manifest import Manifest
from fara_ingest.sources.fara.docs import download_one, select_candidates
from fara_ingest.rate_limit import TokenBucket

TODAY = date(2026, 8, 21)

ROWS = [
    {
        "Date Stamped": "08/19/2026",  # 2 days ago — within a 14-day window
        "Registrant Name": "Fresh Filer",
        "Registration Number": "7435",
        "Document Type": "Supplemental Statement",
        "Short Form Name": "",
        "Foreign Principal Name": "",
        "Foreign Principal Country": "",
        "URL": "https://efile.fara.gov/docs/7435-Supplemental-Statement-20260819-5.pdf",
    },
    {
        "Date Stamped": "01/15/2018",  # 8 years old — historical backlog, not "new"
        "Registrant Name": "Old Registrant",
        "Registration Number": "3301",
        "Document Type": "Registration Statement",
        "Short Form Name": "",
        "Foreign Principal Name": "",
        "Foreign Principal Country": "",
        "URL": "https://efile.fara.gov/docs/3301-Registration-Statement-20180115-1.pdf",
    },
    {
        "Date Stamped": "08/20/2026",
        "Registrant Name": "Office Only",
        "Registration Number": "6170",
        "Document Type": "Short-Form",
        "Short Form Name": "Someone, A",
        "Foreign Principal Name": "",
        "Foreign Principal Country": "",
        "URL": "Available-FARA-Public-Office",  # confirmed sentinel — never a download candidate
    },
]

REGISTRANTS_ROWS = [
    {"Registration Number": "7435", "Termination Date": ""},  # active
    {"Registration Number": "3301", "Termination Date": "01/01/2020"},  # terminated
]


def test_new_mode_only_selects_recent_real_urls():
    candidates = select_candidates(ROWS, mode="new", window_days=14, today=TODAY)
    urls = {c.url for c in candidates}

    assert "https://efile.fara.gov/docs/7435-Supplemental-Statement-20260819-5.pdf" in urls
    assert "https://efile.fara.gov/docs/3301-Registration-Statement-20180115-1.pdf" not in urls  # too old
    assert not any(u == "Available-FARA-Public-Office" for u in urls)  # sentinel excluded
    assert len(candidates) == 1


def test_backfill_mode_orders_active_registrants_first():
    active = {7435}  # only the fresh filer is active
    candidates = select_candidates(ROWS, mode="backfill", active_registration_numbers=active, today=TODAY)

    # Both real-URL rows are candidates in backfill mode; the active one comes first.
    assert len(candidates) == 2
    assert candidates[0].registration_number == 7435


def test_backfill_from_date_excludes_older_documents():
    # ROWS has one 2026 filing and one 2018 filing (both real URLs) — scoping
    # to "2025 onward" must drop the 2018 one entirely, not just deprioritize it.
    candidates = select_candidates(
        ROWS, mode="backfill", active_registration_numbers={7435}, today=TODAY, backfill_from_date=date(2025, 1, 1)
    )
    assert len(candidates) == 1
    assert candidates[0].registration_number == 7435


@respx.mock
def test_download_one_verified(tmp_path):
    url = "https://efile.fara.gov/docs/7435-Supplemental-Statement-20260819-5.pdf"
    respx.get(url).mock(return_value=httpx.Response(200, content=b"%PDF-1.4 fake pdf bytes"))

    archive = LocalArchive(tmp_path / "raw")
    manifest = Manifest(tmp_path / "manifest.sqlite3")
    candidates = select_candidates(ROWS, mode="new", window_days=14, today=TODAY)

    with httpx.Client() as client:
        status = download_one(
            candidates[0], archive=archive, manifest=manifest, client=client, bucket=TokenBucket(10, 1.0)
        )

    assert status == "verified"
    assert manifest.get_pdf_status(url) == "verified"
    assert archive.exists("fara/docs/7435/7435-Supplemental-Statement-20260819-5.pdf")


@respx.mock
def test_download_one_404_marks_unavailable_not_failed(tmp_path):
    url = "https://efile.fara.gov/docs/7435-Supplemental-Statement-20260819-5.pdf"
    respx.get(url).mock(return_value=httpx.Response(404))

    archive = LocalArchive(tmp_path / "raw")
    manifest = Manifest(tmp_path / "manifest.sqlite3")
    candidates = select_candidates(ROWS, mode="new", window_days=14, today=TODAY)

    with httpx.Client() as client:
        status = download_one(
            candidates[0], archive=archive, manifest=manifest, client=client, bucket=TokenBucket(10, 1.0)
        )

    assert status == "unavailable"
    assert manifest.get_pdf_status(url) == "unavailable"


@respx.mock
def test_oversized_file_is_skipped_via_content_length_header(tmp_path):
    # Confirmed real (docs/api-notes.md): some Informational Materials filings
    # are enormous multimedia dumps (one observed at 2.3 GB) — must never be
    # downloaded in full just to discover that.
    url = "https://efile.fara.gov/docs/7435-Supplemental-Statement-20260819-5.pdf"
    respx.get(url).mock(
        return_value=httpx.Response(200, headers={"Content-Length": "999999999"}, content=b"irrelevant")
    )

    archive = LocalArchive(tmp_path / "raw")
    manifest = Manifest(tmp_path / "manifest.sqlite3")
    candidates = select_candidates(ROWS, mode="new", window_days=14, today=TODAY)

    with httpx.Client() as client:
        status = download_one(
            candidates[0], archive=archive, manifest=manifest, client=client,
            bucket=TokenBucket(10, 1.0), max_bytes=50_000_000,
        )

    assert status == "too_large"
    assert manifest.get_pdf_status(url) == "too_large"
    assert not archive.exists("fara/docs/7435/7435-Supplemental-Statement-20260819-5.pdf")


@respx.mock
def test_already_verified_url_is_skipped_without_a_network_call(tmp_path):
    url = "https://efile.fara.gov/docs/7435-Supplemental-Statement-20260819-5.pdf"
    route = respx.get(url).mock(return_value=httpx.Response(200, content=b"data"))

    archive = LocalArchive(tmp_path / "raw")
    manifest = Manifest(tmp_path / "manifest.sqlite3")
    candidates = select_candidates(ROWS, mode="new", window_days=14, today=TODAY)

    with httpx.Client() as client:
        download_one(candidates[0], archive=archive, manifest=manifest, client=client, bucket=TokenBucket(10, 1.0))
        status = download_one(
            candidates[0], archive=archive, manifest=manifest, client=client, bucket=TokenBucket(10, 1.0)
        )

    assert status == "skipped"
    assert route.call_count == 1
