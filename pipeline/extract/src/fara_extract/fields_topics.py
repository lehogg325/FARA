from __future__ import annotations

from typing import Literal

import anthropic
from pydantic import BaseModel, Field

TOPICS_PROMPT_VERSION = "v1"

# Must exactly match ingest/src/fara_ingest/sources/fara/seed_data/topics.csv —
# finalized against a real random sample of extracted nature_of_activities text
# (docs/phase2.md), not guessed. Kept as a Literal (not a free-text field) so the
# model can only ever return a value the `topics` table's FK actually accepts.
TopicCode = Literal[
    "trade_economic",
    "investment_business",
    "defense_security",
    "technology_export_controls",
    "energy",
    "telecommunications",
    "agriculture",
    "health",
    "diplomacy_bilateral",
    "legislation_congress",
    "elections_political",
    "sanctions_legal",
    "human_rights",
    "immigration",
    "tourism_culture",
    "media_pr",
    "informational_materials",
    "think_tank_academic",
    "general_representation",
    "other",
]


def extractor_version(model: str) -> str:
    return f"topics-{model}-{TOPICS_PROMPT_VERSION}"


class TopicClassification(BaseModel):
    topics: list[TopicCode] = Field(
        description="The 1-3 topic categories that best describe the substance of this "
        "filing's activities. Prefer specific categories over 'general_representation' or "
        "'other' whenever the text actually names a substantive subject (e.g. a specific "
        "industry, policy area, or issue) — those two are catch-alls for genuinely generic "
        "text with no identifiable substance. Never return more than 3.",
    )


_PROMPT_TEMPLATE = (
    "Below are narrative fields extracted from a FARA (Foreign Agents Registration Act) "
    "filing, describing a registrant's activities on behalf of a foreign principal. "
    "Classify the substantive topic(s) of these activities.\n\n"
    "--- NATURE OF ACTIVITIES ---\n{nature_of_activities}\n\n"
    "--- POLITICAL ACTIVITY DESCRIPTION ---\n{political_activity_description}\n\n"
    "--- COMPENSATION TERMS ---\n{compensation_terms}"
)


def build_topics_prompt(
    *, nature_of_activities: str | None, political_activity_description: str | None, compensation_terms: str | None
) -> str:
    return _PROMPT_TEMPLATE.format(
        nature_of_activities=nature_of_activities or "(not stated)",
        political_activity_description=political_activity_description or "(not stated)",
        compensation_terms=compensation_terms or "(not stated)",
    )


class NoParsedOutputError(RuntimeError):
    """Raised when the model didn't return structured output — e.g. a refusal
    (`stop_reason == 'refusal'`) or a stop before any text block was parsed."""


def classify_topics(
    *,
    nature_of_activities: str | None,
    political_activity_description: str | None,
    compensation_terms: str | None,
    client: anthropic.Anthropic,
    model: str,
) -> list[str]:
    prompt = build_topics_prompt(
        nature_of_activities=nature_of_activities,
        political_activity_description=political_activity_description,
        compensation_terms=compensation_terms,
    )
    response = client.messages.parse(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
        output_format=TopicClassification,
    )
    if response.parsed_output is None:
        raise NoParsedOutputError(f"no parsed output (stop_reason={response.stop_reason!r})")
    return list(response.parsed_output.topics)
