"""Tests for initial case generation with a provider-neutral model client."""

import json

import pytest

from redteam.attacker import ModelCaseGenerator
from redteam.attacker.prompts import build_case_generation_request
from redteam.core.interfaces import (
    AttackerError,
    CaseGenerator,
    ModelClientError,
)
from redteam.core.models import (
    AvailableStrategy,
    CaseGenerationRequest,
    GeneratedCaseDraft,
    ModelRequest,
    ModelResponse,
    RetryableErrorType,
    RiskObjective,
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


def make_request() -> CaseGenerationRequest:
    return CaseGenerationRequest(
        task_id="task-001",
        test_item_id="risk-item",
        count=2,
        target_profile=TargetProfile(
            name="Fixture assistant",
            description="Processes local fixture records.",
        ),
        risk_objective=RiskObjective(
            risk_id="fixture-risk",
            name="Fixture risk",
            description="Checks a local fixture condition.",
            objective="Generate two fixture inputs.",
        ),
        available_strategies=(
            AvailableStrategy(
                strategy_id="plain",
                name="Plain fixture",
                description="Use a direct fixture.",
                guidance="Keep the fixture concise.",
            ),
        ),
    )


def model_response(payload: object) -> ModelResponse:
    return ModelResponse(text=json.dumps(payload))


@pytest.mark.asyncio
async def test_generates_exact_typed_drafts_in_model_order() -> None:
    response = model_response(
        {
            "cases": [
                {"initial_prompt": "First fixture input."},
                {"initial_prompt": "Second fixture input."},
            ]
        }
    )
    client = FakeModelClient(response=response)
    generator = ModelCaseGenerator(client)
    request = make_request()

    result = await generator.generate(request)

    assert isinstance(generator, CaseGenerator)
    assert result == (
        GeneratedCaseDraft(initial_prompt="First fixture input."),
        GeneratedCaseDraft(initial_prompt="Second fixture input."),
    )
    assert client.requests == [build_case_generation_request(request)]
    assert request == make_request()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "not-json",
        "```json\n{\"cases\": []}\n```",
        "[]",
        "{}",
        '{"cases": [], "commentary": "extra"}',
        '{"cases": "invalid"}',
        '{"cases": [{"initial_prompt": "only one"}]}',
        (
            '{"cases": ['
            '{"initial_prompt": "one"},'
            '{"initial_prompt": "two"},'
            '{"initial_prompt": "three"}'
            "]}"
        ),
        (
            '{"cases": ['
            '{"initial_prompt": "valid"},'
            '{"initial_prompt": ""}'
            "]}"
        ),
        (
            '{"cases": ['
            '{"initial_prompt": "valid"},'
            '{"initial_prompt": "second", "case_id": "forbidden"}'
            "]}"
        ),
    ],
)
async def test_rejects_invalid_or_partial_model_output(text: str) -> None:
    client = FakeModelClient(response=ModelResponse(text=text))
    generator = ModelCaseGenerator(client)

    with pytest.raises(AttackerError) as error:
        await generator.generate(make_request())

    assert len(client.requests) == 1
    assert error.value.retryable_error_type is None
    assert "invalid generated cases" in str(error.value)
    assert text not in str(error.value)


@pytest.mark.asyncio
async def test_preserves_model_client_retry_classification() -> None:
    client = FakeModelClient(
        error=ModelClientError(
            "The external request timed out.",
            retryable_error_type=RetryableErrorType.TIMEOUT,
        )
    )
    generator = ModelCaseGenerator(client)

    with pytest.raises(AttackerError) as error:
        await generator.generate(make_request())

    assert len(client.requests) == 1
    assert error.value.retryable_error_type is RetryableErrorType.TIMEOUT
    assert str(error.value) == "The external request timed out."
