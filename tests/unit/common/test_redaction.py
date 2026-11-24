"""Tests for generic sensitive-data redaction."""

from copy import deepcopy

import pytest

from redteam.common.redaction import REDACTED_VALUE, redact_sensitive_data


@pytest.mark.parametrize(
    "field",
    [
        "api_key",
        "api-key",
        "authorization",
        "access_token",
        "secret",
        "password",
        "API_KEY",
        "Authorization",
    ],
)
def test_redacts_sensitive_dictionary_fields(field: str) -> None:
    result = redact_sensitive_data({field: "synthetic-secret", "safe": "value"})

    assert result == {field: REDACTED_VALUE, "safe": "value"}


def test_recursively_redacts_nested_dictionaries_lists_and_tuples() -> None:
    source = {
        "items": [
            {"api_key": "first-secret"},
            ("safe", {"password": "second-secret"}),
        ]
    }

    result = redact_sensitive_data(source)

    assert result == {
        "items": [
            {"api_key": REDACTED_VALUE},
            ("safe", {"password": REDACTED_VALUE}),
        ]
    }
    assert isinstance(result["items"], list)
    assert isinstance(result["items"][1], tuple)


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
def test_redacts_bearer_credentials_in_text(scheme: str) -> None:
    source = f"Authorization: {scheme} synthetic.token-123, request failed"

    result = redact_sensitive_data(source)

    assert result == f"Authorization: {scheme} {REDACTED_VALUE}, request failed"
    assert "synthetic.token-123" not in result


def test_redacts_multiple_bearer_credentials_in_one_string() -> None:
    source = "Bearer first-token then bearer second.token"

    result = redact_sensitive_data(source)

    assert result == (
        f"Bearer {REDACTED_VALUE} then bearer {REDACTED_VALUE}"
    )


def test_preserves_non_sensitive_content_and_credential_references() -> None:
    source = {
        "prompt": "How can I secure an account after a password leak?",
        "password_hint": "Use the approved recovery process.",
        "api_key_ref": "env:TARGET_API_KEY",
        "count": 2,
        "enabled": True,
        "optional": None,
    }

    assert redact_sensitive_data(source) == source


def test_does_not_modify_the_input_object() -> None:
    source = {
        "headers": {"authorization": "Bearer synthetic-token"},
        "values": [{"secret": "synthetic-secret"}],
    }
    original = deepcopy(source)

    result = redact_sensitive_data(source)

    assert source == original
    assert result is not source
    assert result["headers"] is not source["headers"]
    assert result["values"] is not source["values"]


def test_result_contains_no_original_sensitive_values() -> None:
    source = {
        "api_key": "synthetic-key-value",
        "message": "request used Bearer synthetic-bearer-value",
        "nested": [{"password": "synthetic-password-value"}],
    }

    result = repr(redact_sensitive_data(source))

    for secret in (
        "synthetic-key-value",
        "synthetic-bearer-value",
        "synthetic-password-value",
    ):
        assert secret not in result


def test_redaction_is_idempotent() -> None:
    source = {
        "authorization": "Bearer synthetic-token",
        "message": "Bearer synthetic-token",
    }

    first = redact_sensitive_data(source)

    assert redact_sensitive_data(first) == first
