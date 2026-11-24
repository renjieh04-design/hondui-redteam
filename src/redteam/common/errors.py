"""Classify external-call failures without exposing raw exception details."""

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

import httpx

from redteam.common.redaction import redact_sensitive_data


class ExternalErrorCode(StrEnum):
    """Provider-independent categories for external-call failures."""

    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    AUTHENTICATION_ERROR = "authentication_error"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMIT_ERROR = "rate_limit_error"
    INVALID_REQUEST_ERROR = "invalid_request_error"
    TEMPORARY_SERVER_ERROR = "temporary_server_error"
    INVALID_RESPONSE_ERROR = "invalid_response_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(frozen=True, slots=True)
class ExternalErrorClassification:
    """A stable, sanitized description of one external-call failure."""

    code: ExternalErrorCode
    safe_message: str
    retryable: bool
    exception_type: str


class ExternalResponseFormatError(Exception):
    """A provider response was present but did not match its expected schema."""


_SAFE_MESSAGES = {
    ExternalErrorCode.CONNECTION_ERROR: "Could not connect to the external service.",
    ExternalErrorCode.TIMEOUT: "The external request timed out.",
    ExternalErrorCode.AUTHENTICATION_ERROR: (
        "The external service rejected authentication."
    ),
    ExternalErrorCode.PERMISSION_DENIED: (
        "The external service denied permission for the request."
    ),
    ExternalErrorCode.RATE_LIMIT_ERROR: (
        "The external service rate limit was reached."
    ),
    ExternalErrorCode.INVALID_REQUEST_ERROR: (
        "The external service rejected the request."
    ),
    ExternalErrorCode.TEMPORARY_SERVER_ERROR: (
        "The external service reported a server error."
    ),
    ExternalErrorCode.INVALID_RESPONSE_ERROR: (
        "The external service returned an invalid response."
    ),
    ExternalErrorCode.UNKNOWN_ERROR: "The external request failed.",
}
_RETRYABLE_CODES = frozenset(
    {
        ExternalErrorCode.CONNECTION_ERROR,
        ExternalErrorCode.TIMEOUT,
        ExternalErrorCode.RATE_LIMIT_ERROR,
        ExternalErrorCode.TEMPORARY_SERVER_ERROR,
    }
)


def _classify_status_code(status_code: int) -> ExternalErrorCode:
    if status_code == 408:
        return ExternalErrorCode.TIMEOUT
    if status_code in {401, 407}:
        return ExternalErrorCode.AUTHENTICATION_ERROR
    if status_code == 403:
        return ExternalErrorCode.PERMISSION_DENIED
    if status_code == 429:
        return ExternalErrorCode.RATE_LIMIT_ERROR
    if 400 <= status_code < 500:
        return ExternalErrorCode.INVALID_REQUEST_ERROR
    if 500 <= status_code < 600:
        return ExternalErrorCode.TEMPORARY_SERVER_ERROR
    return ExternalErrorCode.UNKNOWN_ERROR


def _status_code_from_error(error: Exception) -> int | None:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    return None


def _classify_exception(error: Exception) -> ExternalErrorCode:
    if isinstance(error, httpx.TimeoutException):
        return ExternalErrorCode.TIMEOUT
    if isinstance(error, (httpx.NetworkError, httpx.ProxyError)):
        return ExternalErrorCode.CONNECTION_ERROR
    if isinstance(
        error,
        (
            ExternalResponseFormatError,
            httpx.DecodingError,
            httpx.RemoteProtocolError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ),
    ):
        return ExternalErrorCode.INVALID_RESPONSE_ERROR
    if isinstance(
        error,
        (
            httpx.InvalidURL,
            httpx.UnsupportedProtocol,
            httpx.LocalProtocolError,
            httpx.TooManyRedirects,
        ),
    ):
        return ExternalErrorCode.INVALID_REQUEST_ERROR
    return ExternalErrorCode.UNKNOWN_ERROR


def classify_external_error(
    error: Exception,
    *,
    status_code: int | None = None,
) -> ExternalErrorClassification:
    """Return one stable classification without retaining the raw exception."""

    resolved_status = status_code
    if resolved_status is None:
        resolved_status = _status_code_from_error(error)

    code = (
        _classify_status_code(resolved_status)
        if resolved_status is not None
        else _classify_exception(error)
    )
    safe_message = cast(str, redact_sensitive_data(_SAFE_MESSAGES[code]))
    return ExternalErrorClassification(
        code=code,
        safe_message=safe_message,
        retryable=code in _RETRYABLE_CODES,
        exception_type=type(error).__name__,
    )
