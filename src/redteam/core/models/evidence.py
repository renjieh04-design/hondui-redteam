"""Immutable references to separately persisted execution and evaluation evidence."""

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    Field,
    PositiveInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from redteam.core.models.common import DomainModel, NonEmptyStr


Sha256Digest = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    ),
]


class EvidenceKind(StrEnum):
    """The single kind of material stored by one evidence record."""

    TARGET_REQUEST = "target_request"
    TARGET_RESPONSE = "target_response"
    TARGET_PARTIAL_RESPONSE = "target_partial_response"
    EXECUTION_ERROR = "execution_error"
    EVALUATION_INPUT = "evaluation_input"
    EVALUATION_JUDGMENT = "evaluation_judgment"
    EVALUATION_ERROR = "evaluation_error"


class EvidenceProducerType(StrEnum):
    """The domain record whose processing produced the evidence."""

    EXECUTION_ATTEMPT = "execution_attempt"
    EVALUATION = "evaluation"


class EvidenceRedactionStatus(StrEnum):
    """How sensitive material was handled before persistence."""

    NOT_REQUIRED = "not_required"
    REDACTED = "redacted"
    RAW_RESTRICTED = "raw_restricted"


def _validate_producer_kind(
    producer_type: EvidenceProducerType,
    kind: EvidenceKind,
) -> None:
    execution_kinds = {
        EvidenceKind.TARGET_REQUEST,
        EvidenceKind.TARGET_RESPONSE,
        EvidenceKind.TARGET_PARTIAL_RESPONSE,
        EvidenceKind.EXECUTION_ERROR,
    }
    evaluation_kinds = {
        EvidenceKind.EVALUATION_INPUT,
        EvidenceKind.EVALUATION_JUDGMENT,
        EvidenceKind.EVALUATION_ERROR,
    }
    allowed_kinds = (
        execution_kinds
        if producer_type is EvidenceProducerType.EXECUTION_ATTEMPT
        else evaluation_kinds
    )
    if kind not in allowed_kinds:
        raise ValueError("evidence kind must match its producer type")


class EvidenceWriteRequest(DomainModel):
    """Redacted evidence content and lineage supplied to EvidenceStore."""

    task_id: NonEmptyStr
    test_item_id: NonEmptyStr
    case_id: NonEmptyStr
    step_id: NonEmptyStr
    round_index: PositiveInt

    kind: EvidenceKind
    producer_type: EvidenceProducerType
    producer_id: NonEmptyStr

    content: bytes = Field(min_length=1)
    media_type: NonEmptyStr
    redaction_status: EvidenceRedactionStatus

    @model_validator(mode="after")
    def validate_producer_kind(self) -> Self:
        _validate_producer_kind(self.producer_type, self.kind)
        return self


class EvidenceReference(DomainModel):
    """Metadata and integrity information for one separately stored evidence item."""

    evidence_id: NonEmptyStr
    task_id: NonEmptyStr
    test_item_id: NonEmptyStr
    case_id: NonEmptyStr
    step_id: NonEmptyStr
    round_index: PositiveInt

    kind: EvidenceKind
    producer_type: EvidenceProducerType
    producer_id: NonEmptyStr

    storage_ref: NonEmptyStr
    media_type: NonEmptyStr
    sha256: Sha256Digest
    size_bytes: PositiveInt
    redaction_status: EvidenceRedactionStatus
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def require_utc_recorded_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("recorded_at must be a timezone-aware UTC datetime")
        return value

    @model_validator(mode="after")
    def validate_producer_kind(self) -> Self:
        _validate_producer_kind(self.producer_type, self.kind)
        return self
