"""OpenAI-compatible implementation of the provider-neutral ModelClient."""

from typing import Any, cast

import httpx

from redteam.common import (
    CredentialResolutionError,
    ExternalErrorCode,
    ExternalResponseFormatError,
    classify_external_error,
    redact_sensitive_data,
    resolve_credential,
)
from redteam.core.interfaces import ModelClientError
from redteam.core.models import (
    ModelConfig,
    ModelRequest,
    ModelResponse,
    ModelTokenUsage,
    RetryableErrorType,
)


_RETRYABLE_ERROR_TYPES = {
    ExternalErrorCode.CONNECTION_ERROR: RetryableErrorType.CONNECTION_ERROR,
    ExternalErrorCode.TIMEOUT: RetryableErrorType.TIMEOUT,
    ExternalErrorCode.RATE_LIMIT_ERROR: RetryableErrorType.RATE_LIMIT_ERROR,
    ExternalErrorCode.TEMPORARY_SERVER_ERROR: (
        RetryableErrorType.TEMPORARY_SERVER_ERROR
    ),
}


class OpenAICompatibleModelClient:
    """Perform one physical OpenAI-compatible request per completion call."""

    def __init__(self, config: ModelConfig) -> None:
        self._config = config

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Return a normalized response or one sanitized ModelClientError."""

        try:
            headers = self._build_headers()
            payload = self._build_payload(request)
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._config.endpoint,
                    headers=headers,
                    json=payload,
                )
            response.raise_for_status()
            return _parse_response(response)
        except CredentialResolutionError as error:
            safe_message = cast(str, redact_sensitive_data(str(error)))
            raise ModelClientError(safe_message) from None
        except ModelClientError:
            raise
        except Exception as error:
            classification = classify_external_error(error)
            raise ModelClientError(
                classification.safe_message,
                retryable_error_type=_RETRYABLE_ERROR_TYPES.get(
                    classification.code
                ),
            ) from None

    def _build_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._config.api_key_ref is not None:
            api_key = resolve_credential(self._config.api_key_ref)
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _build_payload(self, request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
        }
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        return payload


def _parse_response(response: httpx.Response) -> ModelResponse:
    payload = response.json()
    if not isinstance(payload, dict):
        raise ExternalResponseFormatError(
            "The model response body must be a JSON object."
        )
    text = _parse_response_text(payload)
    provider_request_id = _parse_provider_request_id(response, payload)
    usage = _parse_usage(payload)
    return ModelResponse(
        text=text,
        provider_request_id=provider_request_id,
        usage=usage,
    )


def _parse_response_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ExternalResponseFormatError(
            "The model response did not contain a choice."
        )
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ExternalResponseFormatError("The model choice was invalid.")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ExternalResponseFormatError("The model message was invalid.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ExternalResponseFormatError("The model response text was empty.")
    return content


def _parse_provider_request_id(
    response: httpx.Response,
    payload: dict[str, Any],
) -> str | None:
    request_id: object = response.headers.get("x-request-id")
    if request_id is None:
        request_id = payload.get("id")
    if request_id is None:
        return None
    if not isinstance(request_id, str) or not request_id.strip():
        raise ExternalResponseFormatError("The provider request ID was invalid.")
    return request_id


def _parse_usage(payload: dict[str, Any]) -> ModelTokenUsage | None:
    raw_usage = payload.get("usage")
    if raw_usage is None:
        return None
    if not isinstance(raw_usage, dict):
        raise ExternalResponseFormatError("The model token usage was invalid.")
    input_tokens = raw_usage.get("prompt_tokens")
    output_tokens = raw_usage.get("completion_tokens")
    if not _is_non_negative_integer(input_tokens) or not _is_non_negative_integer(
        output_tokens
    ):
        raise ExternalResponseFormatError("The model token usage was invalid.")
    return ModelTokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _is_non_negative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
