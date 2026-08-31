from __future__ import annotations

import csv
import hashlib
import io
from datetime import date, datetime

# Confirmed live and required (docs/api-notes.md) — never UTF-8 or guessed.
ENCODING = "iso-8859-1"


def read_csv_rows(raw_bytes: bytes) -> list[dict[str, str]]:
    """Raw dict rows, values NOT trimmed — callers hash the exact raw row before
    cleaning, so a pure whitespace fix upstream still registers as a real change.
    """
    text = raw_bytes.decode(ENCODING)
    return list(csv.DictReader(io.StringIO(text)))


def is_malformed_row(row: dict[str, str]) -> bool:
    """True when csv.DictReader captured extra unexpected columns under its
    restkey (None) — a strong signal of unescaped-quote corruption elsewhere in
    the row that shifts every later field (confirmed live in ForeignPrincipals,
    14 of 17,739 rows: docs/api-notes.md). Any field value in such a row may be
    misaligned, so the whole row is unusable, not just whichever field
    happened to look wrong first.
    """
    return None in row


def row_hash(row: dict[str, str]) -> str:
    canonical = "\x1f".join(f"{k}={row.get(k, '')}" for k in sorted(row))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def clean_str(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def normalize_zip(value: str | None) -> str | None:
    # Never fails or drops the value — zip is never a join key (docs/api-notes.md
    # confirms real CSVs have no coded zip scheme to validate against, only
    # trailing-whitespace mess from the source export). A value that doesn't match
    # the 5 or 5+4 shape is kept as-is rather than rejected.
    return clean_str(value)


def parse_mmddyyyy(value: str | None) -> date | None:
    value = clean_str(value)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        # Confirmed live: exactly one malformed Date Stamped value across 153,603
        # RegistrantDocs rows (docs/api-notes.md) — log-and-flag, never raise.
        return None
