"""Tests for the provider-independent attack-decision request builder."""

import json

from redteam.attacker.prompts import build_attack_decision_request
from redteam.core.models import (
    AvailableStrategy,
    EvaluationFeedback,
    MessageRole,
    ModelRequest,
    RiskObjective,
    StepContext,
    StepHistoryEntry,
    TargetProfile,
)


def make_context(round_index: int = 1) -> StepContext:
    history = (
        StepHistoryEntry(
            step_id="history-step-1",
            round_index=1,
            strategy_id="plain",
            attack_prompt='First "fixture" input.',
            target_response="First local response.",
            evaluation_feedback=EvaluationFeedback(
                attack_succeeded=False,
                score=0.2,
                reason="The fixture condition was not observed.",
            ),
        ),
        StepHistoryEntry(
            step_id="history-step-2",
            round_index=2,
            strategy_id="context",
            attack_prompt="Second fixture input.\nWith context.",
            target_response="Second local response.",
            evaluation_feedback=EvaluationFeedback(
                attack_succeeded=None,
                score=None,
                reason="The fixture result was inconclusive.",
            ),
        ),
    )[: round_index - 1]
    return StepContext(
        step_id=f"current-step-{round_index}",
        task_id="task-not-exposed",
        test_item_id="item-not-exposed",
        case_id="case-not-exposed",
        round_index=round_index,
        max_rounds=3,
        target_profile=TargetProfile(
            name="Fixture assistant",
            description="Handles local test records.",
        ),
        risk_objective=RiskObjective(
            risk_id="fixture-risk",
            name="Fixture risk",
            description="Checks a local test condition.",
            objective="Exercise the defined fixture condition.",
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
                guidance="Preserve the prior result context.",
            ),
        ),
        history=history,
    )


def extract_input_data(model_request: ModelRequest) -> dict[str, object]:
    content = model_request.messages[-1].content
    serialized = content.split("Input data (JSON):\n", 1)[1].split(
        "\n\nOutput contract", 1
    )[0]
    return json.loads(serialized)


def test_builds_first_round_request_with_empty_history() -> None:
    context = make_context()

    result = build_attack_decision_request(context)

    assert isinstance(result, ModelRequest)
    assert [message.role for message in result.messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
    ]
    assert extract_input_data(result)["history"] == []
    assert context == make_context()


def test_serializes_complete_current_step_input() -> None:
    context = make_context(round_index=3)

    data = extract_input_data(build_attack_decision_request(context))

    assert data["round_index"] == 3
    assert data["max_rounds"] == 3
    assert data["target_profile"] == context.target_profile.model_dump(mode="json")
    assert data["risk_objective"] == context.risk_objective.model_dump(mode="json")
    assert data["available_strategies"] == [
        item.model_dump(mode="json") for item in context.available_strategies
    ]


def test_serializes_ordered_history_and_feedback() -> None:
    context = make_context(round_index=3)

    history = extract_input_data(build_attack_decision_request(context))["history"]

    assert [entry["round_index"] for entry in history] == [1, 2]
    assert [entry["attack_prompt"] for entry in history] == [
        context.history[0].attack_prompt,
        context.history[1].attack_prompt,
    ]
    assert [entry["target_response"] for entry in history] == [
        context.history[0].target_response,
        context.history[1].target_response,
    ]
    assert history[0]["evaluation_feedback"] == {
        "attack_succeeded": False,
        "score": 0.2,
        "reason": "The fixture condition was not observed.",
    }
    assert history[1]["evaluation_feedback"] == {
        "attack_succeeded": None,
        "score": None,
        "reason": "The fixture result was inconclusive.",
    }


def test_defines_exact_attack_decision_output_contract() -> None:
    content = build_attack_decision_request(make_context()).messages[-1].content

    assert (
        '{"strategy_id":"string","attack_prompt":"string",'
        '"decision_summary":"string"}'
    ) in content
    assert "no longer than 200 characters" in content
    assert "must match one available strategy" in content


def test_omits_system_and_history_identifiers() -> None:
    context = make_context(round_index=3)

    request = build_attack_decision_request(context)
    content = "\n".join(message.content for message in request.messages)

    for forbidden in (
        context.task_id,
        context.test_item_id,
        context.case_id,
        context.step_id,
        context.history[0].step_id,
        context.history[1].step_id,
        "api_key",
        "api-key",
        "authorization",
        "endpoint",
    ):
        assert forbidden.casefold() not in content.casefold()
