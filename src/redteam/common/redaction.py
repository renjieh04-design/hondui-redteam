"""Create sanitized copies of text and JSON-like data structures."""

import re
from typing import Any


REDACTED_VALUE = "[REDACTED]"

_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "api_key",
        "api-key",
        "authorization",
        "access_token",
        "secret",
        "password",
    }
)
_BEARER_CREDENTIAL = re.compile(
    r"\b(Bearer[ \t]+)[A-Za-z0-9._~+/=-]+",
    flags=re.IGNORECASE,
)


def _redact_text(value: str) -> str:
    return _BEARER_CREDENTIAL.sub(
        lambda match: f"{match.group(1)}{REDACTED_VALUE}",
        value,
    )


def redact_sensitive_data(value: Any) -> Any:
    """Return a sanitized copy while preserving supported container types."""

    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {
            key: (
                REDACTED_VALUE
                if isinstance(key, str)
                and key.casefold() in _SENSITIVE_FIELD_NAMES
                else redact_sensitive_data(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    return value
