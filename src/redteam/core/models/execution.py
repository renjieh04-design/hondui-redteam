"""Results of executing one attack decision against the target model API."""

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    Field,
    NonNegativeInt,
    PositiveInt,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)

from redteam.core.models.task import DomainModel, NonEmptyStr


ErrorMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
HttpStatusCode = Annotated[int, Field(ge=100, le=599)]


class ExecutionStatus(StrEnum):
    """Final status of a completed target-model call or logical execution."""

    SUCCESS = "success"
    ERROR = "error"


class ExecutionErrorType(StrEnum):
    """Provider-independent categories for target-model execution failures."""

    REQUEST_BUILD_ERROR = "request_build_error"
    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    TARGET_CLIENT_ERROR = "target_client_error"
    TARGET_SERVER_ERROR = "target_server_error"
    INVALID_RESPONSE_ERROR = "invalid_response_error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class ExecutionError(DomainModel):
    """A normalized, redacted description of one execution failure."""

    error_type: ExecutionErrorType
    message: ErrorMessage


class ExecutionAttempt(DomainModel):
    """One completed physical request to the target model API."""

    attempt_id: NonEmptyStr
    attempt_no: PositiveInt
    status: ExecutionStatus

    # Normalized text for display. Original material belongs in the evidence store.
    response_text: NonEmptyStr | None = None
    partial_response_text: NonEmptyStr | None = None
    error: ExecutionError | None = None

    # These are identifiers of separately stored EvidenceReference records.
    evidence_refs: tuple[NonEmptyStr, ...] = ()

    started_at: datetime
    duration_ms: NonNegativeInt
    http_status_code: HttpStatusCode | None = None
    provider_request_id: NonEmptyStr | None = None

    @field_validator("started_at")
    @classmethod
    def require_utc_started_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("started_at must be a timezone-aware UTC datetime")
        return value

    @model_validator(mode="after")
    def validate_attempt_outcome(self) -> Self:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence references must be unique within an attempt")

        if self.status is ExecutionStatus.SUCCESS:
            if self.response_text is None:
                raise ValueError("a successful attempt requires response_text")
            if self.partial_response_text is not None:
                raise ValueError(
                    "a successful attempt cannot contain partial_response_text"
                )
            if self.error is not None:
                raise ValueError("a successful attempt cannot contain an error")
        else:
            if self.response_text is not None:
                raise ValueError("a failed attempt cannot contain response_text")
            if self.error is None:
                raise ValueError("a failed attempt requires an error")

        return self


class ExecutionResult(DomainModel):
    """The final outcome of one step's logical target-model execution.

    All physical retries are retained in order. A successful result points to
    the one successful final attempt; a failed result contains only failed
    attempts and has no selected attempt.
    """

    task_id: NonEmptyStr
    test_item_id: NonEmptyStr
    case_id: NonEmptyStr
    step_id: NonEmptyStr
    round_index: PositiveInt
    call_id: NonEmptyStr

    attempts: tuple[ExecutionAttempt, ...] = Field(min_length=1)
    selected_attempt_id: NonEmptyStr | None = None

    def to_archive_json(self) -> str:
        """Serialize only fields accepted by model_validate_json."""
        return self.model_dump_json(round_trip=True)

    @model_validator(mode="after")
    def validate_attempt_sequence_and_selection(self) -> Self:
        attempt_ids = [attempt.attempt_id for attempt in self.attempts]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("attempt IDs must be unique within an execution result")

        attempt_numbers = [attempt.attempt_no for attempt in self.attempts]
        expected_numbers = list(range(1, len(self.attempts) + 1))
        if attempt_numbers != expected_numbers:
            raise ValueError("attempt numbers must be ordered and contiguous from 1")

        for previous, current in zip(self.attempts, self.attempts[1:]):
            previous_finished_at = previous.started_at + timedelta(
                milliseconds=previous.duration_ms
            )
            if current.started_at < previous_finished_at:
                raise ValueError("execution attempts cannot overlap")

        successful_attempts = [
            attempt
            for attempt in self.attempts
            if attempt.status is ExecutionStatus.SUCCESS
        ]
        if len(successful_attempts) > 1:
            raise ValueError("an execution result can contain at most one success")

        if self.selected_attempt_id is None:
            if successful_attempts:
                raise ValueError("a successful attempt must be selected")
            return self

        selected_attempt = next(
            (
                attempt
                for attempt in self.attempts
                if attempt.attempt_id == self.selected_attempt_id
            ),
            None,
        )
        if selected_attempt is None:
            raise ValueError("selected_attempt_id must refer to an existing attempt")
        if selected_attempt.status is not ExecutionStatus.SUCCESS:
            raise ValueError("selected_attempt_id must refer to a successful attempt")
        if selected_attempt is not self.attempts[-1]:
            raise ValueError("the successful attempt must be the final attempt")

        return self

    @computed_field
    @property
    def status(self) -> ExecutionStatus:
        """Derive the logical outcome from whether a successful attempt was selected."""

        if self.selected_attempt_id is None:
            return ExecutionStatus.ERROR
        return ExecutionStatus.SUCCESS

    @computed_field
    @property
    def final_response_text(self) -> str | None:
        """Return the normalized response selected for downstream evaluation."""

        if self.selected_attempt_id is None:
            return None
        return next(
            attempt.response_text
            for attempt in self.attempts
            if attempt.attempt_id == self.selected_attempt_id
        )

    @computed_field
    @property
    def started_at(self) -> datetime:
        """Return the start time of the first physical attempt."""

        return self.attempts[0].started_at

    @computed_field
    @property
    def finished_at(self) -> datetime:
        """Return the completion time of the final physical attempt."""

        final_attempt = self.attempts[-1]
        return final_attempt.started_at + timedelta(
            milliseconds=final_attempt.duration_ms
        )

    @computed_field
    @property
    def total_duration_ms(self) -> int:
        """Return wall time including waits between retry attempts."""

        elapsed = self.finished_at - self.started_at
        return (
            elapsed.days * 86_400_000
            + elapsed.seconds * 1_000
            + elapsed.microseconds // 1_000
        )
