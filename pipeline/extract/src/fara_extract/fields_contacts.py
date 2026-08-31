from __future__ import annotations

import re

import anthropic
from pydantic import BaseModel, Field

CONTACTS_EXTRACTOR_VERSION = "contacts-llm-v1"

# Confirmed real (docs/phase2.md): Item 11's "political activities" table is
# headed by this exact phrase across Exhibit AB and Supplemental Statement.
_HEADER_RE = re.compile(r"Date\s+Contact\s+Method\s+Purpose", re.IGNORECASE)

# Confirmed real: a populated table is immediately followed by the page's
# "Received by NSD/FARA" stamp; an unpopulated one goes straight from the
# header to the next numbered item. Both make reliable stop points.
_STOP_RE = re.compile(r"Received by NSD/FARA|\n\s*1[23]\.\s")

_WINDOW_SIZE = 2000

# Confirmed real: a date token inside the window is the actual row content —
# blank tables have no date until the *next* item's own table (12/13's
# contribution tables), which this window's stop point already excludes.
_DATE_TOKEN_RE = re.compile(r"\b\d{1,2}/\d{1,2}/20\d\d\b")


def _looks_populated(window: str) -> bool:
    stripped = window.strip()
    if len(stripped) < 15:
        return False
    if "appendix" in stripped.lower():
        return False
    return bool(_DATE_TOKEN_RE.search(stripped))


def find_populated_contact_windows(full_text: str) -> list[str]:
    """Rule-based pre-filter, not the extractor itself: confirmed real
    (docs/phase2.md) that only ~4% of documents with the Item 11 table
    actually have inline data — the other ~96% defer to a separate appendix
    or leave it blank. Screening those out here means the LLM is only ever
    called on documents that plausibly have something to extract, cutting
    real cost by roughly the same ~96% instead of sending every document."""
    windows = []
    for match in _HEADER_RE.finditer(full_text):
        after = full_text[match.end() :]
        stop = _STOP_RE.search(after)
        window = after[: stop.start()] if stop else after[:_WINDOW_SIZE]
        if _looks_populated(window):
            windows.append(window.strip())
    return windows


class ReportableContact(BaseModel):
    date: str | None = Field(default=None, description="The date of the contact, as written (any format). Null if not given.")
    contact_name: str | None = Field(
        default=None, description="The name and/or title of the person or office contacted, as written. Null if not given."
    )
    contact_method: str | None = Field(
        default=None, description="How the contact was made, e.g. 'Email', 'In person', 'Phone call'. Null if not given."
    )
    purpose: str | None = Field(default=None, description="The stated purpose of the contact. Null if not given.")


class ReportableContactsExtraction(BaseModel):
    contacts: list[ReportableContact] = Field(
        default_factory=list,
        description="Every distinct contact row found in the table text. One entry per row, even if some fields are null.",
    )


_PROMPT_TEMPLATE = (
    "Below is an excerpt from a FARA (Foreign Agents Registration Act) filing's "
    "'Date / Contact Method / Purpose' table, which lists specific contacts the "
    "registrant made with government officials or others as part of political "
    "activity. The excerpt may contain PDF-extraction noise (stray page-stamp text, "
    "line-wrap artifacts) — ignore that and extract only real contact rows. If the "
    "excerpt contains no real contact rows, return an empty list.\n\n"
    "--- TABLE EXCERPT ---\n{window_text}"
)


def build_contacts_prompt(window_text: str) -> str:
    return _PROMPT_TEMPLATE.format(window_text=window_text)


class NoParsedOutputError(RuntimeError):
    """Raised when the model didn't return structured output — e.g. a refusal
    (`stop_reason == 'refusal'`) or a stop before any text block was parsed."""


def extract_reportable_contacts(
    window_text: str, *, client: anthropic.Anthropic, model: str
) -> list[ReportableContact]:
    response = client.messages.parse(
        model=model,
        # Confirmed real (docs/phase2.md): some PR-campaign filings list 100+
        # contact rows in one table — 2048 truncated mid-JSON on real backfill
        # documents (doc 402 alone has 105 rows).
        max_tokens=8192,
        messages=[{"role": "user", "content": build_contacts_prompt(window_text)}],
        output_format=ReportableContactsExtraction,
    )
    if response.parsed_output is None:
        raise NoParsedOutputError(f"no parsed output (stop_reason={response.stop_reason!r})")
    return response.parsed_output.contacts
