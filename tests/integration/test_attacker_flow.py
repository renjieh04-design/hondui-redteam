"""Integration tests for strategy loading through attacker decisions."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from redteam.attacker import (
    LocalAttackStrategyProvider,
    ModelAttacker,
    ModelCaseGenerator,
    OpenAICompatibleModelClient,
)
from redteam.core.interfaces import AttackerError
from redteam.core.models import (
    AvailableStrategy,
    CaseGenerationRequest,
    EvaluationFeedback,
    GeneratedCaseDraft,
    GeneratedCaseSource,
    ModelConfig,
    RetryableErrorType,
    RiskObjective,
    StepContext,
    StepHistoryEntry,
    TargetProfile,
    TestCase as RedTeamTestCase,
)


ENDPOINT = "https://model.example.test/v1/chat/completions"
STRATEGY_CATALOG = (
    Path(__file__).parents[1] / "fixtures" / "strategies" / "strategies.yaml"
)


def make_model_client() -> OpenAICompatibleModelClient:
    return OpenAICompatibleModelClient(
        ModelConfig(
            adapter_type="openai-compatible",
            endpoint=ENDPOINT,
            model="integration-fixture-model",
            api_key_ref=None,
        )
    )


def make_target_profile() -> TargetProfile:
    return TargetProfile(
        name="Integration fixture assistant",
        description="Processes local integration-test records.",
    )


def make_risk_objective() -> RiskObjective:
    return RiskObjective(
        risk_id="integration-risk",
        name="Integration risk",
        description="Checks the local attacker integration flow.",
        objective="Produce and adapt one synthetic test input.",
    )


def completion_response(model_output: object) -> httpx.Response:
    text = model_output if isinstance(model_output, str) else json.dumps(model_output)
    return httpx.Response(
        200,
        json={
            "id": "integration-completion",
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        },
    )


def request_payload(call: Any) -> dict[str, Any]:
    payload = json.loads(call.request.content)
    assert isinstance(payload, dict)
    return payload


def embedded_input(call: Any) -> dict[str, Any]:
    payload = request_payload(call)
    messages = payload["messages"]
    content = messages[-1]["content"]
    serialized = content.split("Input data (JSON):\n", 1)[1].split(
        "\n\nOutput contract", 1
    )[0]
    result = json.loads(serialized)
    assert isinstance(result, dict)
    return result


def make_first_step_context(
    test_case: RedTeamTestCase,
    *,
    available_strategies: tuple[AvailableStrategy, ...],
) -> StepContext:
    return StepContext(
        step_id="step-001",
        task_id=test_case.task_id,
        test_item_id=test_case.test_item_id,
        case_id=test_case.case_id,
        round_index=1,
        max_rounds=2,
        target_profile=make_target_profile(),
        risk_objective=make_risk_objective(),
        available_strategies=available_strategies,
    )


@pytest.mark.asyncio
@respx.mock
async def test_runs_strategy_case_generation_and_multiround_decision_flow() -> None:
    provider = LocalAttackStrategyProvider(STRATEGY_CATALOG)
    available_strategies = (
        provider.resolve("direct"),
        provider.resolve("contextual"),
    )
    route = respx.post(ENDPOINT).mock(
        side_effect=[
            completion_response(
                {"cases": [{"initial_prompt": "Generated fixture seed."}]}
            ),
            completion_response(
                {
                    "strategy_id": "direct",
                    "attack_prompt": "First integration attack input.",
                    "decision_summary": "Start with the direct strategy.",
                }
            ),
            completion_response(
                {
                    "strategy_id": "contextual",
                    "attack_prompt": "Adapted integration attack input.",
                    "decision_summary": "Adapt using the evaluated first round.",
                }
            ),
        ]
    )
    client = make_model_client()
    generator = ModelCaseGenerator(client)
    attacker = ModelAttacker(client)

    drafts = await generator.generate(
        CaseGenerationRequest(
            task_id="task-001",
            test_item_id="risk-item",
            count=1,
            target_profile=make_target_profile(),
            risk_objective=make_risk_objective(),
            available_strategies=available_strategies,
        )
    )
    assert drafts == (GeneratedCaseDraft(initial_prompt="Generated fixture seed."),)
    test_case = RedTeamTestCase(
        case_id="case-001",
        task_id="task-001",
        test_item_id="risk-item",
        initial_prompt=drafts[0].initial_prompt,
        source=GeneratedCaseSource(),
    )

    first_context = make_first_step_context(
        test_case,
        available_strategies=available_strategies,
    )
    first_decision = await attacker.decide(first_context)
    second_context = StepContext(
        step_id="step-002",
        task_id=test_case.task_id,
        test_item_id=test_case.test_item_id,
        case_id=test_case.case_id,
        round_index=2,
        max_rounds=2,
        target_profile=make_target_profile(),
        risk_objective=make_risk_objective(),
        available_strategies=available_strategies,
        history=(
            StepHistoryEntry(
                step_id=first_decision.step_id,
                round_index=first_decision.round_index,
                strategy_id=first_decision.strategy_id,
                attack_prompt=first_decision.attack_prompt,
                target_response="Synthetic target response.",
                evaluation_feedback=EvaluationFeedback(
                    attack_succeeded=False,
                    score=0.25,
                    reason="The synthetic risk condition was not observed.",
                ),
            ),
        ),
    )
    second_decision = await attacker.decide(second_context)

    assert route.call_count == 3
    assert [strategy.strategy_id for strategy in available_strategies] == [
        "direct",
        "contextual",
    ]
    assert first_decision.strategy_id == "direct"
    assert second_decision.strategy_id == "contextual"
    assert first_decision.case_id == test_case.case_id
    assert second_decision.case_id == test_case.case_id
    assert first_decision.round_index == 1
    assert second_decision.round_index == 2

    generation_input = embedded_input(route.calls[0])
    first_round_input = embedded_input(route.calls[1])
    second_round_input = embedded_input(route.calls[2])
    assert generation_input["available_strategies"] == [
        strategy.model_dump(mode="json") for strategy in available_strategies
    ]
    assert first_round_input["history"] == []
    assert second_round_input["history"] == [
        {
            "round_index": 1,
            "strategy_id": "direct",
            "attack_prompt": "First integration attack input.",
            "target_response": "Synthetic target response.",
            "evaluation_feedback": {
                "attack_succeeded": False,
                "score": 0.25,
                "reason": "The synthetic risk condition was not observed.",
            },
        }
    ]
    for call in route.calls:
        payload = request_payload(call)
        assert payload["model"] == "integration-fixture-model"
        assert "authorization" not in call.request.headers


@pytest.mark.asyncio
@respx.mock
async def test_rejects_invalid_case_generation_output_over_http() -> None:
    route = respx.post(ENDPOINT).mock(
        return_value=completion_response("not-json")
    )
    provider = LocalAttackStrategyProvider(STRATEGY_CATALOG)
    generator = ModelCaseGenerator(make_model_client())

    with pytest.raises(AttackerError, match="invalid generated cases"):
        await generator.generate(
            CaseGenerationRequest(
                task_id="task-001",
                test_item_id="risk-item",
                count=1,
                target_profile=make_target_profile(),
                risk_objective=make_risk_objective(),
                available_strategies=(provider.resolve("direct"),),
            )
        )

    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_rejects_unknown_decision_strategy_over_http() -> None:
    route = respx.post(ENDPOINT).mock(
        return_value=completion_response(
            {
                "strategy_id": "not-available",
                "attack_prompt": "Synthetic input.",
                "decision_summary": "Select an unavailable strategy.",
            }
        )
    )
    provider = LocalAttackStrategyProvider(STRATEGY_CATALOG)
    available_strategies = (provider.resolve("direct"),)
    test_case = RedTeamTestCase(
        case_id="case-001",
        task_id="task-001",
        test_item_id="risk-item",
        initial_prompt="Synthetic seed.",
        source=GeneratedCaseSource(),
    )

    with pytest.raises(AttackerError, match="invalid attack decision"):
        await ModelAttacker(make_model_client()).decide(
            make_first_step_context(
                test_case,
                available_strategies=available_strategies,
            )
        )

    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("failure", "expected_error_type"),
    [
        ("timeout", RetryableErrorType.TIMEOUT),
        (429, RetryableErrorType.RATE_LIMIT_ERROR),
        (503, RetryableErrorType.TEMPORARY_SERVER_ERROR),
    ],
)
async def test_maps_http_failures_without_hidden_retry(
    failure: str | int,
    expected_error_type: RetryableErrorType,
) -> None:
    route = respx.post(ENDPOINT)
    if failure == "timeout":
        route.mock(side_effect=httpx.ReadTimeout("synthetic timeout secret"))
    else:
        route.mock(
            return_value=httpx.Response(
                failure,
                text="Authorization: Bearer synthetic-server-secret",
            )
        )
    provider = LocalAttackStrategyProvider(STRATEGY_CATALOG)
    test_case = RedTeamTestCase(
        case_id="case-001",
        task_id="task-001",
        test_item_id="risk-item",
        initial_prompt="Synthetic seed.",
        source=GeneratedCaseSource(),
    )

    with pytest.raises(AttackerError) as error:
        await ModelAttacker(make_model_client()).decide(
            make_first_step_context(
                test_case,
                available_strategies=(provider.resolve("direct"),),
            )
        )

    assert route.call_count == 1
    assert error.value.retryable_error_type is expected_error_type
    assert "synthetic" not in str(error.value)
