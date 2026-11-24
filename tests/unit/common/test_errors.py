"""Tests for provider-independent external error classification."""

from dataclasses import FrozenInstanceError
import json

import httpx
import pytest

from redteam.common.errors import (
    ExternalErrorCode,
    ExternalResponseFormatError,
    classify_external_error,
)


REQUEST = httpx.Request("POST", "https://example.invalid/v1/test")


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (
            httpx.ConnectError("Bearer synthetic-connect-secret", request=REQUEST),
            ExternalErrorCode.CONNECTION_ERROR,
            True,
        ),
        (
            httpx.ReadError("synthetic-read-secret", request=REQUEST),
            ExternalErrorCode.CONNECTION_ERROR,
            True,
        ),
        (
            httpx.ProxyError("synthetic-proxy-secret", request=REQUEST),
            ExternalErrorCode.CONNECTION_ERROR,
            True,
        ),
        (
            httpx.ConnectTimeout("synthetic-timeout-secret", request=REQUEST),
            ExternalErrorCode.TIMEOUT,
            True,
        ),
        (
            httpx.ReadTimeout("synthetic-read-timeout", request=REQUEST),
            ExternalErrorCode.TIMEOUT,
            True,
        ),
        (
            httpx.InvalidURL("synthetic-invalid-url-secret"),
            ExternalErrorCode.INVALID_REQUEST_ERROR,
            False,
        ),
        (
            httpx.UnsupportedProtocol(
                "synthetic-protocol-secret", request=REQUEST
            ),
            ExternalErrorCode.INVALID_REQUEST_ERROR,
            False,
        ),
    ],
)
def test_classifies_transport_errors(
    error: Exception,
    code: ExternalErrorCode,
    retryable: bool,
) -> None:
    result = classify_external_error(error)

    assert result.code is code
    assert result.retryable is retryable
    assert result.exception_type == type(error).__name__


@pytest.mark.parametrize(
    ("status_code", "code", "retryable"),
    [
        (400, ExternalErrorCode.INVALID_REQUEST_ERROR, False),
        (401, ExternalErrorCode.AUTHENTICATION_ERROR, False),
        (403, ExternalErrorCode.PERMISSION_DENIED, False),
        (404, ExternalErrorCode.INVALID_REQUEST_ERROR, False),
        (407, ExternalErrorCode.AUTHENTICATION_ERROR, False),
        (408, ExternalErrorCode.TIMEOUT, True),
        (422, ExternalErrorCode.INVALID_REQUEST_ERROR, False),
        (429, ExternalErrorCode.RATE_LIMIT_ERROR, True),
        (500, ExternalErrorCode.TEMPORARY_SERVER_ERROR, True),
        (503, ExternalErrorCode.TEMPORARY_SERVER_ERROR, True),
        (599, ExternalErrorCode.TEMPORARY_SERVER_ERROR, True),
    ],
)
def test_classifies_http_status_codes(
    status_code: int,
    code: ExternalErrorCode,
    retryable: bool,
) -> None:
    result = classify_external_error(RuntimeError("synthetic"), status_code=status_code)

    assert result.code is code
    assert result.retryable is retryable


def test_reads_status_from_http_status_error() -> None:
    response = httpx.Response(429, request=REQUEST)
    error = httpx.HTTPStatusError(
        "Bearer synthetic-status-secret",
        request=REQUEST,
        response=response,
    )

    result = classify_external_error(error)

    assert result.code is ExternalErrorCode.RATE_LIMIT_ERROR
    assert result.retryable is True
    assert result.exception_type == "HTTPStatusError"


@pytest.mark.parametrize(
    "error",
    [
        ExternalResponseFormatError("Bearer synthetic-schema-secret"),
        json.JSONDecodeError("synthetic-json-secret", "", 0),
        UnicodeDecodeError("utf-8", b"x", 0, 1, "synthetic-decode-secret"),
        httpx.DecodingError("synthetic-http-decode", request=REQUEST),
        httpx.RemoteProtocolError("synthetic-protocol-response", request=REQUEST),
    ],
)
def test_classifies_invalid_responses(error: Exception) -> None:
    result = classify_external_error(error)

    assert result.code is ExternalErrorCode.INVALID_RESPONSE_ERROR
    assert result.retryable is False


def test_unknown_errors_are_safe_and_not_retryable() -> None:
    result = classify_external_error(
        RuntimeError("Authorization: Bearer synthetic-unknown-secret")
    )

    assert result.code is ExternalErrorCode.UNKNOWN_ERROR
    assert result.retryable is False
    assert result.exception_type == "RuntimeError"


def test_classification_does_not_retain_raw_exception_details() -> None:
    secrets = (
        "synthetic-api-key-secret",
        "synthetic-bearer-secret",
    )
    error = RuntimeError(
        f"api_key={secrets[0]} Authorization: Bearer {secrets[1]}"
    )

    result = classify_external_error(error)
    serialized = repr(result)

    assert str(error) not in serialized
    for secret in secrets:
        assert secret not in serialized


def test_classification_is_immutable() -> None:
    result = classify_external_error(RuntimeError("synthetic"))

    with pytest.raises(FrozenInstanceError):
        result.retryable = True  # type: ignore[misc]
