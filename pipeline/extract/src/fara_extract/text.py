from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes

EXTRACTOR_VERSION = "text-v1"
METADATA_COVER_EXTRACTOR_VERSION = "metadata-cover-v1"

# Confirmed live (docs/extraction.md): pre-~2011 documents carry a DOJ-generated
# page-1 cover sheet in this exact format — 18 fixed KEY=VALUE lines, then a
# boilerplate ADA-accessibility paragraph. 100% reliable to parse directly.
_METADATA_COVER_SIGNATURE = "Document Metadata"

# Body pages with fewer than this many native characters are treated as image-only
# and routed through OCR (confirmed live: genuinely scanned pages return exactly 0).
_NATIVE_TEXT_MIN_CHARS = 20

_CLEAN_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z'.,-]*$")


@dataclass
class ExtractionResult:
    extracted_text: str
    extraction_method: str  # 'native' | 'ocr' | 'mixed'
    page_count: int
    char_count: int
    quality_flag: str  # 'ok' | 'low_confidence' | 'failed'
    metadata_cover_fields: dict[str, str] | None = field(default=None)


def parse_metadata_cover(page_text: str) -> dict[str, str] | None:
    lines = page_text.splitlines()
    if not lines or lines[0].strip() != _METADATA_COVER_SIGNATURE:
        return None
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if "=" not in line:
            break  # reached the boilerplate ADA-accessibility paragraph
        key, _, value = line.partition("=")
        fields[key.strip()] = value.strip()
    return fields


def _clean_token_ratio(text: str) -> float:
    tokens = text.split()
    if not tokens:
        return 1.0  # empty text is judged 'failed' separately, not 'low_confidence'
    clean = sum(1 for t in tokens if _CLEAN_TOKEN_RE.match(t) or t.isdigit())
    return clean / len(tokens)


def is_garbled(text: str, threshold: float = 0.80) -> bool:
    """Catches text that's technically 'present' but not trustworthy — confirmed
    live in the ~2011 transitional era, where DOJ's own embedded OCR layer can be
    low quality even though native extraction finds real characters. Threshold
    calibrated against real fixtures spanning all three eras (docs/extraction.md):
    every clean sample (born-digital native AND our own OCR on genuinely scanned
    pages) scored 0.844-0.915; the one confirmed-garbled real sample scored 0.740
    — a full 0.10 below the floor of every good sample, not a close call.
    """
    return _clean_token_ratio(text) < threshold


def _ocr_page(pdf_bytes: bytes, page_number: int) -> str:
    images = convert_from_bytes(pdf_bytes, first_page=page_number, last_page=page_number, dpi=200)
    if not images:
        return ""
    return pytesseract.image_to_string(images[0])


def extract_pdf_text(pdf_bytes: bytes) -> ExtractionResult:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page_count = len(pdf.pages)
        page_texts = [p.extract_text() or "" for p in pdf.pages]

    metadata_cover_fields = parse_metadata_cover(page_texts[0]) if page_texts else None
    body_page_indices = range(1, page_count) if metadata_cover_fields is not None else range(page_count)

    body_parts = []
    used_native = False
    used_ocr = False

    for i in body_page_indices:
        native_text = page_texts[i]
        if len(native_text.strip()) >= _NATIVE_TEXT_MIN_CHARS:
            body_parts.append(native_text)
            used_native = True
        else:
            ocr_text = _ocr_page(pdf_bytes, i + 1)  # pdf2image pages are 1-indexed
            body_parts.append(ocr_text)
            used_ocr = True

    extracted_text = "\n".join(body_parts)

    if used_native and used_ocr:
        extraction_method = "mixed"
    elif used_ocr:
        extraction_method = "ocr"
    else:
        extraction_method = "native"

    if not extracted_text.strip():
        quality_flag = "failed"
    elif is_garbled(extracted_text):
        quality_flag = "low_confidence"
    else:
        quality_flag = "ok"

    return ExtractionResult(
        extracted_text=extracted_text,
        extraction_method=extraction_method,
        page_count=page_count,
        char_count=len(extracted_text),
        quality_flag=quality_flag,
        metadata_cover_fields=metadata_cover_fields,
    )
