from __future__ import annotations

from pathlib import Path

from fara_extract.fields_rules import extract_agreement_date, extract_political_contributions
from fara_extract.text import extract_pdf_text

FIXTURES = Path(__file__).parent / "fixtures" / "pdfs"


def _text_of(name: str) -> str:
    return extract_pdf_text((FIXTURES / name).read_bytes()).extracted_text


def test_registration_statement_political_contributions():
    # Confirmed real: 14 contributions across two attachment pages, summing to $10,300.00.
    rows = extract_political_contributions(_text_of("era3-registration-statement.pdf"))
    assert len(rows) == 14
    assert round(sum(r.amount for r in rows), 2) == 10_300.00
    assert rows[0].date_raw == "2/07/2013"
    assert rows[0].amount == 1000.00
    assert "Friends of Kelly Ayotte" in rows[0].description


def test_supplemental_statement_political_contributions():
    # Confirmed real: 38 contributions from the Appendix table, summing to $30,436.63.
    rows = extract_political_contributions(_text_of("era3-supplemental-statement.pdf"))
    assert len(rows) == 38
    assert round(sum(r.amount for r in rows), 2) == 30_436.63
    assert rows[0].date_raw == "01/07/2026"
    assert "Tom DiNapoli" in rows[0].description


def test_short_form_political_contributions():
    # Confirmed real: 3 personal contributions from the individual short-form filer.
    rows = extract_political_contributions(_text_of("era3-short-form.pdf"))
    assert len(rows) == 3
    assert round(sum(r.amount for r in rows), 2) == 550.00
    assert rows[0].date_raw == "06/16/2026"
    assert "KH Atwood" in rows[0].description


def test_no_contributions_found_in_documents_without_the_item():
    # Amendment and Exhibit AB fixtures don't carry this item at all.
    assert extract_political_contributions(_text_of("era3-amendment.pdf")) == []


def test_exhibit_ab_agreement_date():
    # Confirmed real: Item 7, "07/24/2026" for Mercury/Croatian Democratic Union.
    date = extract_agreement_date(_text_of("era3-exhibit-ab.pdf"))
    assert date == "07/24/2026"


def test_agreement_date_absent_in_unrelated_document():
    assert extract_agreement_date(_text_of("era3-short-form.pdf")) is None
