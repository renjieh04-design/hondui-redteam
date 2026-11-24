"""Tests for one-step attacker decisions."""

import json

import pytest

from redteam.attacker import ModelAttacker
from redteam.attacker.prompts import build_attack_decision_request
from redteam.core.interfaces import Attacker, AttackerError, ModelClientError
from redteam.core.models import (
    AttackDecision,
    AvailableStrategy,
    EvaluationFeedback,
    ModelRequest,
    ModelResponse,
    RetryableErrorType,
    RiskObjective,
    StepContext,
    StepHistoryEntry,
    TargetProfile,
)


class FakeModelClient:
    def __init__(
        self,
        *,
        response: ModelResponse | None = None,
        error: ModelClientError | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def make_context(round_index: int = 1) -> StepContext:
    history = (
        StepHistoryEntry(
            step_id="completed-step-1",
            round_index=1,
            strategy_id="plain",
            attack_prompt="First fixture input.",
            target_response="First local response.",
            evaluation_feedback=EvaluationFeedback(
                attack_succeeded=False,
                score=0.2,
                reason="The fixture condition was not observed.",
            ),
        ),
        StepHistoryEntry(
            step_id="completed-step-2",
            round_index=2,
            strategy_id="context",
            attack_prompt="Second fixture input.",
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
        task_id="task-001",
        test_item_id="risk-item",
        case_id="case-001",
        round_index=round_index,
        max_rounds=3,
        target_profile=TargetProfile(
            name="Fixture assistant",
            description="Handles local test records.",
        ),
        risk_objective=RiskObjective(
            risk_id="fixture-risk",
            name="Fixture risk",
            description="Checks a local fixture condition.",
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


def model_response(payload: object) -> ModelResponse:
    return ModelResponse(text=json.dumps(payload))


@pytest.mark.asyncio
@pytest.mark.parametrize("round_index", [1, 3])
async def test_generates_typed_decision_for_first_and_later_rounds(
    round_index: int,
) -> None:
    client = FakeModelClient(
        response=model_response(
            {
                "strategy_id": "context",
                "attack_prompt": "Next fixture input.",
                "decision_summary": "Use prior context.",
            }
        )
    )
    attacker = ModelAttacker(client)
    context = make_context(round_index)

    result = await attacker.decide(context)

    assert isinstance(attacker, Attacker)
    assert result == AttackDecision(
        task_id=context.task_id,
        test_item_id=context.test_item_id,
        case_id=context.case_id,
        step_id=context.step_id,
        round_index=context.round_index,
        strategy_id="context",
        attack_prompt="Next fixture input.",
        decision_summary="Use prior context.",
    )
    assert client.requests == [build_attack_decision_request(context)]
    assert context == make_context(round_index)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "not-json",
        "```json\n{}\n```",
        "[]",
        "{}",
        json.dumps(
            {
                "strategy_id": "unknown",
                "attack_prompt": "Fixture input.",
                "decision_summary": "Unknown strategy.",
            }
        ),
        json.dumps(
            {
                "strategy_id": "plain",
                "attack_prompt": "",
                "decision_summary": "Empty input.",
            }
        ),
        json.dumps(
            {
                "strategy_id": "plain",
                "attack_prompt": "Fixture input.",
                "decision_summary": "x" * 201,
            }
        ),
        json.dumps(
            {
                "strategy_id": "plain",
                "attack_prompt": "Fixture input.",
                "decision_summary": "Tries to replace an identifier.",
                "task_id": "forbidden",
            }
        ),
    ],
)
async def test_rejects_invalid_model_output(text: str) -> None:
    client = FakeModelClient(response=ModelResponse(text=text))
    attacker = ModelAttacker(client)

    with pytest.raises(AttackerError) as error:
        await attacker.decide(make_context())

    assert len(client.requests) == 1
    assert error.value.retryable_error_type is None
    assert "invalid attack decision" in str(error.value)
    assert text not in str(error.value)


@pytest.mark.asyncio
async def test_preserves_model_client_retry_classification() -> None:
    client = FakeModelClient(
        error=ModelClientError(
            "The external request timed out.",
            retryable_error_type=RetryableErrorType.TIMEOUT,
        )
    )
    attacker = ModelAttacker(client)

    with pytest.raises(AttackerError) as error:
        await attacker.decide(make_context())

    assert len(client.requests) == 1
    assert error.value.retryable_error_type is RetryableErrorType.TIMEOUT
    assert str(error.value) == "The external request timed out."
