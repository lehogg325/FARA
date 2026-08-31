from __future__ import annotations

from pathlib import Path

import pytest

from fara_extract.text import extract_pdf_text, is_garbled, parse_metadata_cover

FIXTURES = Path(__file__).parent / "fixtures" / "pdfs"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_parse_metadata_cover_real_format():
    fields = parse_metadata_cover(
        "Document Metadata\n"
        "REGISTRATION NUMBER=536\n"
        "REGISTRANT NAME=IRISH TOURIST BOARD\n"
        "DOCUMENT TYPE=Exhibit AB\n"
        "The Department of Justice recognizes that some of the FARA documents..."
    )
    assert fields == {
        "REGISTRATION NUMBER": "536",
        "REGISTRANT NAME": "IRISH TOURIST BOARD",
        "DOCUMENT TYPE": "Exhibit AB",
    }


def test_parse_metadata_cover_returns_none_for_born_digital_page():
    assert parse_metadata_cover("Received by NSD/FARA Registration Unit 05/14/2013...") is None


def test_is_garbled_calibrated_against_real_samples():
    # Confirmed real (docs/extraction.md): every clean sample (native or OCR)
    # scores 0.844-0.915; the one confirmed-garbled sample scores 0.740.
    assert is_garbled("*__I>_rf_i«^^ jFrankte Reed Gzo .Roiiseo bO 03") is True
    assert is_garbled("Received by NSD/FARA Registration Unit for the Foreign Agents Registration Act") is False


@pytest.mark.parametrize(
    "filename,expected_method,expected_quality,expects_cover",
    [
        ("era1-earliest-1942.pdf", "ocr", "ok", True),
        ("era1-metadata-cover-scanned-body.pdf", "ocr", "ok", True),
        ("era2-transitional-garbled.pdf", "native", "low_confidence", False),
        ("era3-registration-statement.pdf", "native", "ok", False),
        ("era3-supplemental-statement.pdf", "native", "ok", False),
        ("era3-exhibit-ab.pdf", "native", "ok", False),
        ("era3-short-form.pdf", "native", "ok", False),
        ("era3-amendment.pdf", "native", "ok", False),
    ],
)
def test_extract_pdf_text_across_real_eras(filename, expected_method, expected_quality, expects_cover):
    result = extract_pdf_text(_read(filename))
    assert result.extraction_method == expected_method
    assert result.quality_flag == expected_quality
    assert (result.metadata_cover_fields is not None) == expects_cover
    assert result.char_count > 0


def test_metadata_cover_excluded_from_body_text():
    result = extract_pdf_text(_read("era1-metadata-cover-scanned-body.pdf"))
    assert "Document Metadata" not in result.extracted_text
    assert "REGISTRATION NUMBER=" not in result.extracted_text


def test_metadata_cover_fields_contain_real_registrant_data():
    result = extract_pdf_text(_read("era1-earliest-1942.pdf"))
    assert result.metadata_cover_fields["REGISTRATION NUMBER"] == "55"
    assert result.metadata_cover_fields["REGISTRANT NAME"] == "SWITZERLAND TOURISM"


def test_ocr_recovers_real_historical_content():
    # This page returns 0 native characters (confirmed live) — if OCR is
    # broken, char_count would be 0 too.
    result = extract_pdf_text(_read("era1-metadata-cover-scanned-body.pdf"))
    assert result.char_count > 500
