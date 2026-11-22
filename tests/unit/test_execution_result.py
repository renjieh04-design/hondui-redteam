"""ExecutionResult and physical target-call attempt constraints."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from redteam.core.models import (
    ExecutionAttempt,
    ExecutionErrorType,
    ExecutionResult,
    ExecutionStatus,
)


NOW = datetime(2026, 11, 22, 10, 0, tzinfo=UTC)


def _error(error_type: str = "timeout") -> dict[str, str]:
    return {
        "error_type": error_type,
        "message": "The target model request timed out after 30 seconds.",
    }


def _failed_attempt(
    *,
    attempt_id: str = "attempt-001",
    attempt_no: int = 1,
    started_at: datetime = NOW,
    duration_ms: int = 1_000,
) -> dict[str, object]:
    return {
        "attempt_id": attempt_id,
        "attempt_no": attempt_no,
        "status": "error",
        "error": _error(),
        "started_at": started_at,
        "duration_ms": duration_ms,
        "evidence_refs": [f"evidence-{attempt_no}-request"],
    }


def _successful_attempt(
    *,
    attempt_id: str = "attempt-002",
    attempt_no: int = 2,
    started_at: datetime = NOW + timedelta(seconds=2),
    duration_ms: int = 500,
) -> dict[str, object]:
    return {
        "attempt_id": attempt_id,
        "attempt_no": attempt_no,
        "status": "success",
        "response_text": "Normalized target response.",
        "started_at": started_at,
        "duration_ms": duration_ms,
        "http_status_code": 200,
        "provider_request_id": "provider-request-002",
        "evidence_refs": [
            f"evidence-{attempt_no}-request",
            f"evidence-{attempt_no}-response",
        ],
    }


def _result_data() -> dict[str, object]:
    return {
        "task_id": "task-001",
        "test_item_id": "privacy-test",
        "case_id": "case-001",
        "step_id": "step-002",
        "round_index": 2,
        "call_id": "call-001",
        "attempts": [_failed_attempt(), _successful_attempt()],
        "selected_attempt_id": "attempt-002",
    }


def test_successful_result_keeps_all_attempts_and_derives_final_values() -> None:
    result = ExecutionResult.model_validate(_result_data())

    assert result.status is ExecutionStatus.SUCCESS
    assert result.final_response_text == "Normalized target response."
    assert result.started_at == NOW
    assert result.finished_at == NOW + timedelta(milliseconds=2_500)
    assert result.total_duration_ms == 2_500
    assert [attempt.attempt_no for attempt in result.attempts] == [1, 2]


def test_failed_result_has_no_selected_response() -> None:
    data = _result_data()
    data["attempts"] = [_failed_attempt()]
    data["selected_attempt_id"] = None

    result = ExecutionResult.model_validate(data)

    assert result.status is ExecutionStatus.ERROR
    assert result.final_response_text is None


def test_failed_attempt_can_retain_a_partial_response() -> None:
    attempt = ExecutionAttempt.model_validate(
        {
            **_failed_attempt(),
            "partial_response_text": "Partially received response",
        }
    )

    assert attempt.partial_response_text == "Partially received response"
    assert attempt.response_text is None


def test_attempt_outcome_fields_must_match_its_status() -> None:
    with pytest.raises(ValidationError, match="requires response_text"):
        ExecutionAttempt.model_validate(
            {
                "attempt_id": "attempt-001",
                "attempt_no": 1,
                "status": "success",
                "started_at": NOW,
                "duration_ms": 100,
            }
        )

    with pytest.raises(ValidationError, match="requires an error"):
        ExecutionAttempt.model_validate(
            {
                "attempt_id": "attempt-001",
                "attempt_no": 1,
                "status": "error",
                "started_at": NOW,
                "duration_ms": 100,
            }
        )


def test_successful_attempt_cannot_contain_error_or_partial_response() -> None:
    data = _successful_attempt(attempt_no=1, attempt_id="attempt-001", started_at=NOW)
    data["error"] = _error()

    with pytest.raises(ValidationError, match="cannot contain an error"):
        ExecutionAttempt.model_validate(data)

    data = _successful_attempt(attempt_no=1, attempt_id="attempt-001", started_at=NOW)
    data["partial_response_text"] = "unexpected partial text"

    with pytest.raises(ValidationError, match="partial_response_text"):
        ExecutionAttempt.model_validate(data)


def test_attempt_time_must_be_utc_and_http_status_must_be_valid() -> None:
    data = _failed_attempt()
    data["started_at"] = datetime(2026, 11, 22, 10, 0)

    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        ExecutionAttempt.model_validate(data)

    data = _failed_attempt()
    data["http_status_code"] = 700

    with pytest.raises(ValidationError, match="less than or equal to 599"):
        ExecutionAttempt.model_validate(data)


def test_error_message_is_trimmed_and_limited_to_500_characters() -> None:
    data = _failed_attempt()
    data["error"] = {
        "error_type": ExecutionErrorType.TIMEOUT,
        "message": "  Target timed out.  ",
    }

    attempt = ExecutionAttempt.model_validate(data)
    assert attempt.error is not None
    assert attempt.error.message == "Target timed out."

    data["error"] = {
        "error_type": ExecutionErrorType.TIMEOUT,
        "message": "x" * 501,
    }
    with pytest.raises(ValidationError, match="at most 500 characters"):
        ExecutionAttempt.model_validate(data)


def test_evidence_references_must_be_unique_within_an_attempt() -> None:
    data = _failed_attempt()
    data["evidence_refs"] = ["evidence-001", "evidence-001"]

    with pytest.raises(ValidationError, match="evidence references must be unique"):
        ExecutionAttempt.model_validate(data)


def test_attempt_ids_and_numbers_must_form_an_ordered_unique_sequence() -> None:
    data = _result_data()
    data["attempts"] = [
        _failed_attempt(attempt_id="duplicate", attempt_no=1),
        _successful_attempt(attempt_id="duplicate", attempt_no=2),
    ]
    data["selected_attempt_id"] = "duplicate"

    with pytest.raises(ValidationError, match="attempt IDs must be unique"):
        ExecutionResult.model_validate(data)

    data = _result_data()
    data["attempts"] = [
        _failed_attempt(attempt_no=1),
        _successful_attempt(attempt_no=3),
    ]

    with pytest.raises(ValidationError, match="ordered and contiguous"):
        ExecutionResult.model_validate(data)


def test_attempts_cannot_overlap() -> None:
    data = _result_data()
    data["attempts"] = [
        _failed_attempt(duration_ms=2_000),
        _successful_attempt(started_at=NOW + timedelta(seconds=1)),
    ]

    with pytest.raises(ValidationError, match="cannot overlap"):
        ExecutionResult.model_validate(data)


def test_selection_must_point_to_the_only_final_success() -> None:
    data = _result_data()
    data["selected_attempt_id"] = "missing"
    with pytest.raises(ValidationError, match="existing attempt"):
        ExecutionResult.model_validate(data)

    data = _result_data()
    data["selected_attempt_id"] = "attempt-001"
    with pytest.raises(ValidationError, match="successful attempt"):
        ExecutionResult.model_validate(data)

    data = _result_data()
    data["selected_attempt_id"] = None
    with pytest.raises(ValidationError, match="successful attempt must be selected"):
        ExecutionResult.model_validate(data)


def test_retry_cannot_continue_after_a_success() -> None:
    data = _result_data()
    data["attempts"] = [
        _successful_attempt(
            attempt_id="attempt-001",
            attempt_no=1,
            started_at=NOW,
            duration_ms=500,
        ),
        {
            **_successful_attempt(
                attempt_id="attempt-002",
                attempt_no=2,
                started_at=NOW + timedelta(seconds=1),
            ),
        },
    ]
    data["selected_attempt_id"] = "attempt-002"

    with pytest.raises(ValidationError, match="at most one success"):
        ExecutionResult.model_validate(data)


def test_models_reject_fields_outside_the_v1_contract() -> None:
    data = _result_data()
    data["target_session_ref"] = "not-supported-in-v1"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExecutionResult.model_validate(data)


def test_archive_round_trip():
    result = ExecutionResult.model_validate(_result_data())
    assert ExecutionResult.model_validate_json(result.to_archive_json()) == result
