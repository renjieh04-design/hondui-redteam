"""EvidenceReference metadata, integrity, and producer constraints."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from redteam.core.models import (
    EvidenceKind,
    EvidenceProducerType,
    EvidenceRedactionStatus,
    EvidenceReference,
)


NOW = datetime(2026, 11, 22, 14, 0, tzinfo=UTC)
DIGEST = "a" * 64


def _evidence() -> dict[str, object]:
    return {
        "evidence_id": "evidence-001",
        "task_id": "task-001",
        "test_item_id": "privacy-test",
        "case_id": "case-007",
        "step_id": "step-003",
        "round_index": 3,
        "kind": "target_response",
        "producer_type": "execution_attempt",
        "producer_id": "attempt-003",
        "storage_ref": "blob:task-001/evidence-001",
        "media_type": "application/json",
        "sha256": DIGEST,
        "size_bytes": 512,
        "redaction_status": "redacted",
        "recorded_at": NOW,
    }


def test_execution_evidence_records_lineage_storage_and_integrity() -> None:
    evidence = EvidenceReference.model_validate(_evidence())

    assert evidence.kind is EvidenceKind.TARGET_RESPONSE
    assert evidence.producer_type is EvidenceProducerType.EXECUTION_ATTEMPT
    assert evidence.redaction_status is EvidenceRedactionStatus.REDACTED
    assert evidence.sha256 == DIGEST


def test_evaluation_evidence_uses_an_evaluation_producer() -> None:
    data = _evidence()
    data.update(
        kind="evaluation_judgment",
        producer_type="evaluation",
        producer_id="evaluation-001",
    )

    evidence = EvidenceReference.model_validate(data)
    assert evidence.kind is EvidenceKind.EVALUATION_JUDGMENT


@pytest.mark.parametrize(
    ("producer_type", "kind"),
    [
        ("execution_attempt", "evaluation_input"),
        ("evaluation", "target_request"),
    ],
)
def test_evidence_kind_must_match_its_producer(
    producer_type: str,
    kind: str,
) -> None:
    data = _evidence()
    data.update(producer_type=producer_type, kind=kind)

    with pytest.raises(ValidationError, match="kind must match"):
        EvidenceReference.model_validate(data)


@pytest.mark.parametrize("digest", ["A" * 64, "a" * 63, "g" * 64])
def test_sha256_must_be_64_lowercase_hex_characters(digest: str) -> None:
    data = _evidence()
    data["sha256"] = digest

    with pytest.raises(ValidationError):
        EvidenceReference.model_validate(data)


def test_evidence_size_must_be_positive_and_timestamp_must_be_utc() -> None:
    data = _evidence()
    data["size_bytes"] = 0
    with pytest.raises(ValidationError, match="greater than 0"):
        EvidenceReference.model_validate(data)

    data = _evidence()
    data["recorded_at"] = datetime(2026, 11, 22, 14, 0)
    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        EvidenceReference.model_validate(data)


def test_evidence_reference_rejects_inline_content_and_unknown_fields() -> None:
    data = _evidence()
    data["content"] = "Evidence content must be stored separately."

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvidenceReference.model_validate(data)
