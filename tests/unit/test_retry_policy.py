"""RetryPolicy configuration and safety constraints."""

import pytest
from pydantic import ValidationError

from redteam.core.models import RetryPolicy, RetryableErrorType, TaskDefinition


def _target() -> dict[str, str]:
    return {
        "name": "customer-service-assistant",
        "description": "Answers questions about the authenticated customer's orders.",
        "adapter_type": "openai_compatible",
        "endpoint": "https://target.example.test/v1/chat/completions",
    }


def _task_data() -> dict[str, object]:
    return {
        "task_id": "task-001",
        "name": "Retry policy test",
        "target": _target(),
        "test_items": [
            {
                "item_id": "baseline-1",
                "kind": "baseline",
                "dataset": {"dataset_id": "benchmark", "version": "1.0"},
                "evaluation_rule_refs": [
                    {"rule_id": "exact-answer", "version": "1.0"}
                ],
            }
        ],
    }


def _backoff() -> dict[str, object]:
    return {
        "base_delay_seconds": 1.0,
        "max_delay_seconds": 20.0,
        "multiplier": 2.0,
        "jitter_ratio": 0.25,
    }


def test_existing_tasks_receive_a_resolved_retry_disabled_policy() -> None:
    task = TaskDefinition.model_validate(_task_data())

    assert task.retry_policy.attacker_model.max_retries == 0
    assert task.retry_policy.target.max_retries == 0
    assert task.retry_policy.judge_model.max_retries == 0
    assert task.retry_policy.internal_execution.max_retries == 0


def test_four_retry_categories_are_configured_independently() -> None:
    data = _task_data()
    data["retry_policy"] = {
        "attacker_model": {
            "timeout_seconds": 45,
            "max_retries": 1,
            "retryable_errors": ["timeout"],
            "backoff": _backoff(),
        },
        "target": {
            "timeout_seconds": 60,
            "max_retries": 3,
            "retryable_errors": [
                "connection_error",
                "rate_limit_error",
                "temporary_server_error",
            ],
            "backoff": _backoff(),
        },
        "judge_model": {
            "timeout_seconds": 30,
            "max_retries": 2,
            "retryable_errors": ["timeout", "rate_limit_error"],
            "backoff": _backoff(),
        },
        "internal_execution": {
            "max_retries": 1,
            "retryable_errors": ["evidence_persistence_error"],
            "backoff": _backoff(),
        },
    }

    task = TaskDefinition.model_validate(data)

    assert task.retry_policy.attacker_model.max_retries == 1
    assert task.retry_policy.target.max_retries == 3
    assert task.retry_policy.judge_model.max_retries == 2
    assert task.retry_policy.internal_execution.max_retries == 1
    assert (
        task.retry_policy.target.retryable_errors[-1]
        is RetryableErrorType.TEMPORARY_SERVER_ERROR
    )


def test_enabled_retries_require_a_nonempty_unique_whitelist() -> None:
    with pytest.raises(ValidationError, match="at least one retryable"):
        RetryPolicy.model_validate(
            {"target": {"max_retries": 1, "retryable_errors": []}}
        )

    with pytest.raises(ValidationError, match="must be unique"):
        RetryPolicy.model_validate(
            {
                "target": {
                    "max_retries": 1,
                    "retryable_errors": ["timeout", "timeout"],
                }
            }
        )


def test_external_and_internal_error_whitelists_cannot_be_mixed() -> None:
    with pytest.raises(ValidationError, match="not valid for this operation"):
        RetryPolicy.model_validate(
            {
                "target": {
                    "max_retries": 1,
                    "retryable_errors": ["temporary_io_error"],
                }
            }
        )

    with pytest.raises(ValidationError, match="not valid for this operation"):
        RetryPolicy.model_validate(
            {
                "internal_execution": {
                    "max_retries": 1,
                    "retryable_errors": ["connection_error"],
                }
            }
        )


def test_backoff_bounds_timeout_and_jitter_are_validated() -> None:
    with pytest.raises(ValidationError, match="cannot be less"):
        RetryPolicy.model_validate(
            {
                "target": {
                    "backoff": {
                        **_backoff(),
                        "base_delay_seconds": 10,
                        "max_delay_seconds": 5,
                    }
                }
            }
        )

    with pytest.raises(ValidationError, match="greater than 0"):
        RetryPolicy.model_validate({"target": {"timeout_seconds": 0}})

    with pytest.raises(ValidationError, match="greater than 0"):
        RetryPolicy.model_validate(
            {"target": {"backoff": {**_backoff(), "jitter_ratio": 0}}}
        )

    with pytest.raises(ValidationError):
        RetryPolicy.model_validate({"target": {"timeout_seconds": float("inf")}})


def test_retry_policy_does_not_accept_runtime_state() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RetryPolicy.model_validate({"current_attempt": 2})
