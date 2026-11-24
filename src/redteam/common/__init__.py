"""Shared implementation utilities used by framework adapters."""

from redteam.common.credentials import (
    CredentialErrorReason,
    CredentialResolutionError,
    resolve_credential,
)
from redteam.common.errors import (
    ExternalErrorClassification,
    ExternalErrorCode,
    ExternalResponseFormatError,
    classify_external_error,
)
from redteam.common.redaction import REDACTED_VALUE, redact_sensitive_data

__all__ = [
    "CredentialErrorReason",
    "CredentialResolutionError",
    "ExternalErrorClassification",
    "ExternalErrorCode",
    "ExternalResponseFormatError",
    "REDACTED_VALUE",
    "classify_external_error",
    "redact_sensitive_data",
    "resolve_credential",
]
