"""Tests for environment-backed credential reference resolution."""

import os

import pytest

from redteam.common.credentials import (
    CredentialErrorReason,
    CredentialResolutionError,
    resolve_credential,
)


def test_resolves_environment_variable_without_modifying_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synthetic_secret = "synthetic-test-secret"
    monkeypatch.setenv("ATTACKER_API_KEY", synthetic_secret)

    result = resolve_credential("env:ATTACKER_API_KEY")

    assert result == synthetic_secret
    assert os.environ["ATTACKER_API_KEY"] == synthetic_secret


@pytest.mark.parametrize("reference", ["ATTACKER_API_KEY", "", None, 123])
def test_rejects_invalid_reference_format(reference: object) -> None:
    with pytest.raises(CredentialResolutionError) as error:
        resolve_credential(reference)  # type: ignore[arg-type]

    assert error.value.reason is CredentialErrorReason.INVALID_REFERENCE


def test_rejects_missing_source() -> None:
    with pytest.raises(CredentialResolutionError) as error:
        resolve_credential(":ATTACKER_API_KEY")

    assert error.value.reason is CredentialErrorReason.INVALID_REFERENCE


@pytest.mark.parametrize("reference", ["file:key.txt", "vault:secret", "ENV:KEY"])
def test_rejects_unsupported_source(reference: str) -> None:
    with pytest.raises(CredentialResolutionError) as error:
        resolve_credential(reference)

    assert error.value.reason is CredentialErrorReason.UNSUPPORTED_SOURCE


@pytest.mark.parametrize(
    "reference",
    ["env:", "env:1KEY", "env:KEY-NAME", "env:KEY NAME", "env:KEY:EXTRA"],
)
def test_rejects_invalid_environment_variable_name(reference: str) -> None:
    with pytest.raises(CredentialResolutionError) as error:
        resolve_credential(reference)

    assert error.value.reason is CredentialErrorReason.INVALID_ENVIRONMENT_VARIABLE


def test_rejects_missing_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING_TEST_CREDENTIAL", raising=False)

    with pytest.raises(CredentialResolutionError) as error:
        resolve_credential("env:MISSING_TEST_CREDENTIAL")

    assert error.value.reason is CredentialErrorReason.ENVIRONMENT_VARIABLE_NOT_FOUND


@pytest.mark.parametrize("value", ["", " ", "\t\r\n"])
def test_rejects_empty_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("EMPTY_TEST_CREDENTIAL", value)

    with pytest.raises(CredentialResolutionError) as error:
        resolve_credential("env:EMPTY_TEST_CREDENTIAL")

    assert error.value.reason is CredentialErrorReason.EMPTY_CREDENTIAL


def test_error_messages_do_not_echo_reference_or_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synthetic_secret = "synthetic-secret-must-not-leak"
    monkeypatch.setenv("LEAK_TEST_CREDENTIAL", synthetic_secret)

    with pytest.raises(CredentialResolutionError) as error:
        resolve_credential(synthetic_secret)

    message = str(error.value)
    assert synthetic_secret not in message
    assert "LEAK_TEST_CREDENTIAL" not in message
