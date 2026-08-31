from __future__ import annotations

import re
from dataclasses import dataclass

RULES_EXTRACTOR_VERSION = "rules-v1"

# Confirmed real across all 4 target document types (docs/extraction.md build step 9):
# Registration Statement Item 10(c), Supplemental Statement Item 15(c), and Short-Form
# Item 15 all ask this near-identical statutory question before disclosing political
# contributions. Anchoring on the *question text* rather than the table header row is
# deliberate: the header row's column labels get scrambled by column-wrap in at least one
# real case (an appendix table split "Political" from "Organization/Candidate" with
# "Method Amount!" inserted between them by the text-flow order) — this fixed legal phrase
# is prose and doesn't suffer that.
_QUESTION_ANCHOR_RE = re.compile(r"primary election,?\s*convention,?\s*or\s*caucus", re.IGNORECASE)

# Confirmed real, Registration Statement specifically: unlike Supplemental Statement and
# Short-Form (whose populated tables restate the full statutory question inline), a
# Registration Statement's actual contribution data lives on separate attachment pages
# thousands of characters later, linked back only by a heading like "Registration
# Statement Item 10 c." — the statutory-question anchor alone never reaches it.
_ATTACHMENT_HEADING_RE = re.compile(r"item\s*(?:10\s*\(?c\)?|15\s*\(?c\)?)\b", re.IGNORECASE)

# Confirmed real: rows sometimes wrap across lines with the amount appearing before the
# organization name (Registration Statement style: Date/Amount/Org/Location) or after it
# (Supplemental/Short-Form style: Date/Donor/Org/Method/Amount) — so a row's boundary is
# "up to the next date token," not a fixed column count.
_DATE_TOKEN_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b")
# Confirmed real: a font/encoding quirk occasionally renders "$" as "$s" or similar —
# tolerate 0-3 stray letters between the dollar sign and the digits.
_AMOUNT_TOKEN_RE = re.compile(r"\$\s*[A-Za-z]{0,3}\s*([\d,]+\.\d{2})")

_WINDOW_SIZE = 3000

# Confirmed real (docs/extraction.md): a short or empty contributions section
# lets the fixed window run past its own table into the next section (V -
# INFORMATIONAL MATERIALS) and misread that section's budget-amount figures as
# political contributions. This heading is stable across doc types and always
# follows the contributions item, so it's a safe hard stop.
_SECTION_END_RE = re.compile(r"V\s*-?\s*INFORMATIONAL MATERIALS", re.IGNORECASE)

# A row with no following date token runs to the end of the window by default —
# confirmed real: this can bleed into the page's received-stamp footer or the
# EXECUTION/signature block. Truncate there rather than keep irrelevant tail text.
_TRAILING_BOILERPLATE_RE = re.compile(r"\b(Received by NSD/FARA|EXECUTION)\b")


@dataclass
class ContributionRow:
    date_raw: str
    amount: float
    description: str


def find_contribution_table_windows(full_text: str) -> list[str]:
    """One bounded window of text after each occurrence of either anchor —
    both can appear more than once (an empty in-form placeholder and a
    populated appendix/attachment both reference the same item)."""
    offsets = {m.end() for m in _QUESTION_ANCHOR_RE.finditer(full_text)}
    offsets |= {m.end() for m in _ATTACHMENT_HEADING_RE.finditer(full_text)}

    windows = []
    for offset in sorted(offsets):
        candidate = full_text[offset : offset + _WINDOW_SIZE]
        end_match = _SECTION_END_RE.search(candidate)
        windows.append(candidate[: end_match.start()] if end_match else candidate)
    return windows


def extract_contribution_rows(block: str) -> list[ContributionRow]:
    dates = list(_DATE_TOKEN_RE.finditer(block))
    rows = []

    for i, date_match in enumerate(dates):
        row_end = dates[i + 1].start() if i + 1 < len(dates) else len(block)
        row_text = block[date_match.end() : row_end]

        amount_match = _AMOUNT_TOKEN_RE.search(row_text)
        if amount_match is None:
            continue

        boilerplate_match = _TRAILING_BOILERPLATE_RE.search(row_text)
        if boilerplate_match:
            row_text = row_text[: boilerplate_match.start()]

        description = _AMOUNT_TOKEN_RE.sub(" ", row_text)
        description = re.sub(r"\s+", " ", description).strip(" :|")

        rows.append(
            ContributionRow(
                date_raw=date_match.group(1),
                amount=float(amount_match.group(1).replace(",", "")),
                description=description,
            )
        )
    return rows


_AGREEMENT_DATE_RE = re.compile(
    r"date of the contract or agreement with the foreign principal\?\s*(\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)


def extract_agreement_date(full_text: str) -> str | None:
    """Exhibit AB Item 7 — confirmed real, reliably anchored: a single clean
    date immediately following this exact question text."""
    match = _AGREEMENT_DATE_RE.search(full_text)
    return match.group(1) if match else None


def extract_political_contributions(full_text: str) -> list[ContributionRow]:
    """Multiple anchors can produce overlapping windows (e.g. three attachment
    pages each headed 'Registration Statement Item 10 c.' only a page apart) —
    dedupe by content, since the same real row would otherwise be captured
    once per overlapping window."""
    seen: set[tuple[str, float, str]] = set()
    rows: list[ContributionRow] = []
    for window in find_contribution_table_windows(full_text):
        for row in extract_contribution_rows(window):
            key = (row.date_raw, row.amount, row.description)
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return rows
