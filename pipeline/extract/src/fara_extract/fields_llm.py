from __future__ import annotations

import anthropic
from pydantic import BaseModel, Field

# Per current Claude API guidance: default to the most capable model unless the
# user explicitly chooses otherwise — cost-driven downgrades are the user's
# call, not this pipeline's. Configurable per-call for exactly that reason.
DEFAULT_MODEL = "claude-opus-5"
PROMPT_VERSION = "v1"

# Bounds cost/latency per call — confirmed real (docs/extraction.md): the
# targeted items (7-10) sit early in Exhibit AB; an attached contract can run
# long, but the fields asked for here don't need the whole thing.
MAX_DOCUMENT_CHARS = 12_000


def extractor_version(model: str = DEFAULT_MODEL) -> str:
    """Identifies model+prompt version, so upgrading either is a normal
    versioned re-run (extraction_runs keyed on this), never a special
    migration."""
    return f"llm-{model}-{PROMPT_VERSION}"


class ExhibitABFields(BaseModel):
    """Narrative fields from a FARA Exhibit AB (Form NSD-4) that resist regex
    because they're free text (docs/extraction.md) — the checkbox itself
    (Item 10 Yes/No) is not parsed here; only the narrative it's paired with.
    """

    nature_of_activities: str | None = Field(
        default=None,
        description="The nature and method of performance of the agreement, or the "
        "activities the registrant engages in or proposes to engage in on behalf of the "
        "foreign principal, from Items 8-9. Null if not stated in the text.",
    )
    includes_political_activity: bool | None = Field(
        default=None,
        description="Whether Item 10 discloses that activities include political activity "
        "as defined in the Act. Null if not determinable from the text.",
    )
    political_activity_description: str | None = Field(
        default=None,
        description="The description of political activities from Item 10, if disclosed. "
        "Null if none disclosed or not applicable.",
    )
    compensation_terms: str | None = Field(
        default=None,
        description="Any description of compensation, fees, or payment terms mentioned in "
        "the agreement text or an attached contract (e.g. a 'Payment Terms' clause). "
        "Null if no such terms are described in the text.",
    )


_PROMPT_TEMPLATE = (
    "Below is the extracted text of a FARA (Foreign Agents Registration Act) Exhibit AB "
    "filing (Form NSD-4), which describes the agreement between a registrant and a foreign "
    "principal. Extract the requested fields from the text. If a field genuinely cannot be "
    "determined from the text, return null rather than guessing.\n\n"
    "--- DOCUMENT TEXT ---\n{document_text}"
)


def build_prompt(document_text: str) -> str:
    return _PROMPT_TEMPLATE.format(document_text=document_text[:MAX_DOCUMENT_CHARS])


class NoParsedOutputError(RuntimeError):
    """Raised when the model didn't return structured output — e.g. a refusal
    (`stop_reason == 'refusal'`) or a stop before any text block was parsed."""


def extract_exhibit_ab_fields(
    document_text: str, *, client: anthropic.Anthropic, model: str = DEFAULT_MODEL
) -> ExhibitABFields:
    response = client.messages.parse(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": build_prompt(document_text)}],
        output_format=ExhibitABFields,
    )
    if response.parsed_output is None:
        raise NoParsedOutputError(f"no parsed output (stop_reason={response.stop_reason!r})")
    return response.parsed_output
