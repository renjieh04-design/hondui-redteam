"""Tests for the provider-independent initial-case request builder."""

import json

from redteam.attacker.prompts import build_case_generation_request
from redteam.core.models import (
    AvailableStrategy,
    CaseGenerationRequest,
    MessageRole,
    ModelRequest,
    RiskObjective,
    TargetProfile,
)


def make_request() -> CaseGenerationRequest:
    return CaseGenerationRequest(
        task_id="task-not-exposed",
        test_item_id="item-not-exposed",
        count=2,
        target_profile=TargetProfile(
            name='Support "fixture"',
            description="Answers local fixture questions.\nSecond line.",
        ),
        risk_objective=RiskObjective(
            risk_id="format-risk",
            name="Format risk",
            description="Checks structured fixture handling.",
            objective="Produce two distinct fixture records.",
        ),
        available_strategies=(
            AvailableStrategy(
                strategy_id="plain",
                name="Plain fixture",
                description="Use a direct local example.",
                guidance="Keep the example concise.",
            ),
            AvailableStrategy(
                strategy_id="context",
                name="Context fixture",
                description="Use supplied local context.",
                guidance="Preserve punctuation and line breaks.",
            ),
        ),
    )


def extract_input_data(model_request: ModelRequest) -> dict[str, object]:
    content = model_request.messages[-1].content
    serialized = content.split("Input data (JSON):\n", 1)[1].split(
        "\n\nOutput contract", 1
    )[0]
    return json.loads(serialized)


def test_builds_valid_provider_neutral_model_request() -> None:
    source = make_request()

    result = build_case_generation_request(source)

    assert isinstance(result, ModelRequest)
    assert [message.role for message in result.messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
    ]
    assert result.max_output_tokens is None
    assert source == make_request()


def test_serializes_complete_generation_input() -> None:
    source = make_request()

    data = extract_input_data(build_case_generation_request(source))

    assert data == {
        "target_profile": source.target_profile.model_dump(mode="json"),
        "risk_objective": source.risk_objective.model_dump(mode="json"),
        "available_strategies": [
            strategy.model_dump(mode="json")
            for strategy in source.available_strategies
        ],
        "count": 2,
    }


def test_defines_one_exact_json_output_contract() -> None:
    content = build_case_generation_request(make_request()).messages[-1].content

    assert '{"cases":[{"initial_prompt":"string"}]}' in content
    assert "exactly 2 items" in content
    assert "case_id" not in content


def test_omits_runtime_identity_and_connection_fields() -> None:
    content = "\n".join(
        message.content
        for message in build_case_generation_request(make_request()).messages
    )

    for forbidden in (
        "task-not-exposed",
        "item-not-exposed",
        "api_key",
        "api-key",
        "authorization",
        "endpoint",
    ):
        assert forbidden not in content.casefold()


def test_uses_json_encoding_for_embedded_quotes_and_newlines() -> None:
    result = build_case_generation_request(make_request())

    data = extract_input_data(result)

    assert data["target_profile"] == {
        "name": 'Support "fixture"',
        "description": "Answers local fixture questions.\nSecond line.",
    }
