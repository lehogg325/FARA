from __future__ import annotations

from unittest.mock import MagicMock

import anthropic
import pytest

from fara_extract.fields_llm import (
    DEFAULT_MODEL,
    ExhibitABFields,
    NoParsedOutputError,
    build_prompt,
    extract_exhibit_ab_fields,
    extractor_version,
)


def _mock_client(parsed_output, stop_reason: str = "end_turn") -> MagicMock:
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.parse.return_value = MagicMock(parsed_output=parsed_output, stop_reason=stop_reason)
    return client


def test_extractor_version_encodes_model_and_prompt_version():
    assert extractor_version("claude-opus-5") == "llm-claude-opus-5-v1"
    assert extractor_version() == f"llm-{DEFAULT_MODEL}-v1"


def test_build_prompt_includes_document_text():
    prompt = build_prompt("REAL DOCUMENT CONTENT HERE")
    assert "REAL DOCUMENT CONTENT HERE" in prompt
    assert "Exhibit AB" in prompt


def test_build_prompt_truncates_long_documents():
    huge_text = "x" * 50_000
    prompt = build_prompt(huge_text)
    assert len(prompt) < 20_000


def test_extract_exhibit_ab_fields_returns_parsed_output():
    expected = ExhibitABFields(
        nature_of_activities="Public relations and government relations advice",
        includes_political_activity=True,
        political_activity_description="Lobbying on trade policy",
        compensation_terms="Monthly retainer per Schedule 2",
    )
    client = _mock_client(expected)

    result = extract_exhibit_ab_fields("some document text", client=client)

    assert result == expected
    client.messages.parse.assert_called_once()
    call_kwargs = client.messages.parse.call_args.kwargs
    assert call_kwargs["output_format"] is ExhibitABFields
    assert call_kwargs["model"] == DEFAULT_MODEL


def test_extract_exhibit_ab_fields_respects_model_override():
    client = _mock_client(ExhibitABFields())
    extract_exhibit_ab_fields("text", client=client, model="claude-sonnet-5")
    assert client.messages.parse.call_args.kwargs["model"] == "claude-sonnet-5"


def test_null_fields_are_preserved_when_not_determinable():
    expected = ExhibitABFields(
        nature_of_activities="Consulting services",
        includes_political_activity=None,
        political_activity_description=None,
        compensation_terms=None,
    )
    client = _mock_client(expected)

    result = extract_exhibit_ab_fields("text", client=client)

    assert result.includes_political_activity is None
    assert result.political_activity_description is None


def test_no_parsed_output_raises_clear_error():
    client = _mock_client(None, stop_reason="refusal")
    with pytest.raises(NoParsedOutputError, match="refusal"):
        extract_exhibit_ab_fields("text", client=client)
