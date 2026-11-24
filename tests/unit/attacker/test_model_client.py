"""Tests for the OpenAI-compatible model client."""

import json

import httpx
import pytest
import respx

from redteam.attacker import OpenAICompatibleModelClient
from redteam.core.interfaces import ModelClient, ModelClientError
from redteam.core.models import (
    ConversationMessage,
    MessageRole,
    ModelConfig,
    ModelRequest,
    RetryableErrorType,
)


ENDPOINT = "https://model.example.test/v1/chat/completions"
SYNTHETIC_API_KEY = "synthetic-model-key"


def make_config(*, with_credential: bool = True) -> ModelConfig:
    return ModelConfig(
        adapter_type="openai-compatible",
        endpoint=ENDPOINT,
        model="fixture-model",
        api_key_ref="env:ATTACKER_TEST_API_KEY" if with_credential else None,
    )


def make_request(*, max_output_tokens: int | None = 128) -> ModelRequest:
    return ModelRequest(
        messages=(
            ConversationMessage(role=MessageRole.SYSTEM, content="System fixture."),
            ConversationMessage(role=MessageRole.USER, content="User fixture."),
        ),
        max_output_tokens=max_output_tokens,
    )


def success_payload() -> dict[str, object]:
    return {
        "id": "completion-from-body",
        "choices": [{"message": {"content": "fixture response"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }


@pytest.mark.asyncio
@respx.mock
async def test_sends_one_openai_compatible_request_and_normalizes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATTACKER_TEST_API_KEY", SYNTHETIC_API_KEY)
    route = respx.post(ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json=success_payload(),
            headers={"x-request-id": "request-from-header"},
        )
    )
    client = OpenAICompatibleModelClient(make_config())

    result = await client.complete(make_request())

    assert isinstance(client, ModelClient)
    assert route.call_count == 1
    sent = route.calls[0].request
    assert sent.headers["authorization"] == f"Bearer {SYNTHETIC_API_KEY}"
    assert json.loads(sent.content) == {
        "model": "fixture-model",
        "messages": [
            {"role": "system", "content": "System fixture."},
            {"role": "user", "content": "User fixture."},
        ],
        "max_tokens": 128,
    }
    assert result.text == "fixture response"
    assert result.provider_request_id == "request-from-header"
    assert result.usage is not None
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7


@pytest.mark.asyncio
@respx.mock
async def test_supports_anonymous_endpoint_and_optional_response_metadata() -> None:
    route = respx.post(ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "fixture response"}}]},
        )
    )
    client = OpenAICompatibleModelClient(make_config(with_credential=False))

    result = await client.complete(make_request(max_output_tokens=None))

    sent = route.calls[0].request
    assert "authorization" not in sent.headers
    assert "max_tokens" not in json.loads(sent.content)
    assert result.provider_request_id is None
    assert result.usage is None


@pytest.mark.asyncio
@respx.mock
async def test_falls_back_to_response_id_when_request_header_is_absent() -> None:
    route = respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json=success_payload())
    )
    client = OpenAICompatibleModelClient(make_config(with_credential=False))

    result = await client.complete(make_request())

    assert route.call_count == 1
    assert result.provider_request_id == "completion-from-body"


@pytest.mark.asyncio
@respx.mock
async def test_missing_credential_fails_before_http_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ATTACKER_TEST_API_KEY", raising=False)
    route = respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json=success_payload())
    )
    client = OpenAICompatibleModelClient(make_config())

    with pytest.raises(ModelClientError) as error:
        await client.complete(make_request())

    assert route.call_count == 0
    assert error.value.retryable_error_type is None
    assert SYNTHETIC_API_KEY not in str(error.value)


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("exception", "error_type"),
    [
        (
            httpx.ConnectError("Bearer synthetic-connect-secret"),
            RetryableErrorType.CONNECTION_ERROR,
        ),
        (
            httpx.ReadTimeout("Bearer synthetic-timeout-secret"),
            RetryableErrorType.TIMEOUT,
        ),
    ],
)
async def test_maps_network_failures_without_retrying(
    exception: Exception,
    error_type: RetryableErrorType,
) -> None:
    route = respx.post(ENDPOINT).mock(side_effect=exception)
    client = OpenAICompatibleModelClient(make_config(with_credential=False))

    with pytest.raises(ModelClientError) as error:
        await client.complete(make_request())

    assert route.call_count == 1
    assert error.value.retryable_error_type is error_type
    assert "synthetic" not in str(error.value)


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, None),
        (429, RetryableErrorType.RATE_LIMIT_ERROR),
        (503, RetryableErrorType.TEMPORARY_SERVER_ERROR),
    ],
)
async def test_maps_http_failures_without_retrying(
    status_code: int,
    error_type: RetryableErrorType | None,
) -> None:
    route = respx.post(ENDPOINT).mock(
        return_value=httpx.Response(
            status_code,
            text=f"Authorization: Bearer {SYNTHETIC_API_KEY}",
        )
    )
    client = OpenAICompatibleModelClient(make_config(with_credential=False))

    with pytest.raises(ModelClientError) as error:
        await client.complete(make_request())

    assert route.call_count == 1
    assert error.value.retryable_error_type is error_type
    assert SYNTHETIC_API_KEY not in str(error.value)


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": " "}}]}),
        httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "fixture"}}],
                "usage": {"prompt_tokens": "11", "completion_tokens": 7},
            },
        ),
    ],
)
async def test_rejects_invalid_response_without_retrying(
    response: httpx.Response,
) -> None:
    route = respx.post(ENDPOINT).mock(return_value=response)
    client = OpenAICompatibleModelClient(make_config(with_credential=False))

    with pytest.raises(ModelClientError) as error:
        await client.complete(make_request())

    assert route.call_count == 1
    assert error.value.retryable_error_type is None
    assert "invalid response" in str(error.value).casefold()
