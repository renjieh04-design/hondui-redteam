"""Resolve credential references without exposing credential values."""

import os
import re
from enum import StrEnum


_ENVIRONMENT_VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class CredentialErrorReason(StrEnum):
    """Stable reasons for a credential reference resolution failure."""

    INVALID_REFERENCE = "invalid_reference"
    UNSUPPORTED_SOURCE = "unsupported_source"
    INVALID_ENVIRONMENT_VARIABLE = "invalid_environment_variable"
    ENVIRONMENT_VARIABLE_NOT_FOUND = "environment_variable_not_found"
    EMPTY_CREDENTIAL = "empty_credential"


class CredentialResolutionError(Exception):
    """A credential reference could not be resolved safely."""

    def __init__(self, message: str, *, reason: CredentialErrorReason) -> None:
        super().__init__(message)
        self.reason = reason


def resolve_credential(reference: str) -> str:
    """Resolve one ``env:VARIABLE_NAME`` reference to its exact value."""

    if not isinstance(reference, str) or ":" not in reference:
        raise CredentialResolutionError(
            "Credential reference must use the env:VARIABLE_NAME format.",
            reason=CredentialErrorReason.INVALID_REFERENCE,
        )

    source, _, variable_name = reference.partition(":")
    if not source:
        raise CredentialResolutionError(
            "Credential reference must include a source.",
            reason=CredentialErrorReason.INVALID_REFERENCE,
        )
    if source != "env":
        raise CredentialResolutionError(
            "Credential reference source is not supported.",
            reason=CredentialErrorReason.UNSUPPORTED_SOURCE,
        )
    if _ENVIRONMENT_VARIABLE_NAME.fullmatch(variable_name) is None:
        raise CredentialResolutionError(
            "Credential environment variable name is invalid.",
            reason=CredentialErrorReason.INVALID_ENVIRONMENT_VARIABLE,
        )

    value = os.environ.get(variable_name)
    if value is None:
        raise CredentialResolutionError(
            "Credential environment variable is not set.",
            reason=CredentialErrorReason.ENVIRONMENT_VARIABLE_NOT_FOUND,
        )
    if not value.strip():
        raise CredentialResolutionError(
            "Credential environment variable is empty.",
            reason=CredentialErrorReason.EMPTY_CREDENTIAL,
        )
    return value
