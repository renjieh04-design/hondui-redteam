"""Resolved retry configuration consumed by TaskRunner."""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    Field,
    NonNegativeInt,
    model_validator,
)

from redteam.core.models.common import DomainModel


NonNegativeSeconds = Annotated[
    float,
    Field(ge=0.0, allow_inf_nan=False),
]
PositiveSeconds = Annotated[
    float,
    Field(gt=0.0, allow_inf_nan=False),
]
BackoffMultiplier = Annotated[
    float,
    Field(gt=1.0, allow_inf_nan=False),
]
JitterRatio = Annotated[
    float,
    Field(gt=0.0, le=1.0, allow_inf_nan=False),
]


class RetryableErrorType(StrEnum):
    """Normalized transient failures that may be explicitly retried."""

    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    RATE_LIMIT_ERROR = "rate_limit_error"
    TEMPORARY_SERVER_ERROR = "temporary_server_error"
    TEMPORARY_IO_ERROR = "temporary_io_error"
    EVIDENCE_PERSISTENCE_ERROR = "evidence_persistence_error"


EXTERNAL_RETRYABLE_ERRORS = frozenset(
    {
        RetryableErrorType.CONNECTION_ERROR,
        RetryableErrorType.TIMEOUT,
        RetryableErrorType.RATE_LIMIT_ERROR,
        RetryableErrorType.TEMPORARY_SERVER_ERROR,
    }
)
INTERNAL_RETRYABLE_ERRORS = frozenset(
    {
        RetryableErrorType.TEMPORARY_IO_ERROR,
        RetryableErrorType.EVIDENCE_PERSISTENCE_ERROR,
    }
)


class BackoffConfig(DomainModel):
    """Exponential backoff parameters; TaskRunner performs the actual wait."""

    base_delay_seconds: NonNegativeSeconds = 0.5
    max_delay_seconds: NonNegativeSeconds = 30.0
    multiplier: BackoffMultiplier = 2.0
    jitter_ratio: JitterRatio = 0.2

    @model_validator(mode="after")
    def validate_delay_bounds(self) -> Self:
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError(
                "max_delay_seconds cannot be less than base_delay_seconds"
            )
        return self


def _validate_retry_config(
    *,
    max_retries: int,
    retryable_errors: tuple[RetryableErrorType, ...],
    allowed_errors: frozenset[RetryableErrorType],
) -> None:
    if len(retryable_errors) != len(set(retryable_errors)):
        raise ValueError("retryable error types must be unique")
    if any(error not in allowed_errors for error in retryable_errors):
        raise ValueError("retryable error type is not valid for this operation")
    if max_retries > 0 and not retryable_errors:
        raise ValueError("enabled retries require at least one retryable error type")


class CallRetryConfig(DomainModel):
    """Retry policy for one category of external model or target calls."""

    timeout_seconds: PositiveSeconds = 30.0
    max_retries: NonNegativeInt = 0
    retryable_errors: tuple[RetryableErrorType, ...] = ()
    backoff: BackoffConfig = Field(default_factory=BackoffConfig)

    @model_validator(mode="after")
    def validate_retryable_errors(self) -> Self:
        _validate_retry_config(
            max_retries=self.max_retries,
            retryable_errors=self.retryable_errors,
            allowed_errors=EXTERNAL_RETRYABLE_ERRORS,
        )
        return self


class InternalRetryConfig(DomainModel):
    """Retry policy for bounded, recoverable framework-internal operations."""

    max_retries: NonNegativeInt = 0
    retryable_errors: tuple[RetryableErrorType, ...] = ()
    backoff: BackoffConfig = Field(default_factory=BackoffConfig)

    @model_validator(mode="after")
    def validate_retryable_errors(self) -> Self:
        _validate_retry_config(
            max_retries=self.max_retries,
            retryable_errors=self.retryable_errors,
            allowed_errors=INTERNAL_RETRYABLE_ERRORS,
        )
        return self


class RetryPolicy(DomainModel):
    """The four independent, resolved retry configurations for one task."""

    attacker_model: CallRetryConfig = Field(default_factory=CallRetryConfig)
    target: CallRetryConfig = Field(default_factory=CallRetryConfig)
    judge_model: CallRetryConfig = Field(default_factory=CallRetryConfig)
    internal_execution: InternalRetryConfig = Field(
        default_factory=InternalRetryConfig
    )
