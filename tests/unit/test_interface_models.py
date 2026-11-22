"""Small public models used as inputs and outputs of module interfaces."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from redteam.core.models import (
    CaseGenerationRequest,
    DatasetEntry,
    EvidenceWriteRequest,
    EvaluationRequest,
    GeneratedCaseDraft,
    MessageRole,
    ModelRequest,
    ModelResponse,
    PreparedTestItem,
    ReportArtifact,
    ReportFormat,
    ReportRequest,
    ResolvedEvaluationRule,
    ScoringRequest,
    TargetAdapterRequest,
    TargetAdapterResponse,
    TargetExecutionRequest,
)


NOW = datetime(2026, 11, 22, 14, 0, tzinfo=UTC)


def _target() -> dict[str, object]:
    return {
        "name": "Support assistant",
        "description": "Answers customer questions without exposing private data.",
        "adapter_type": "openai-compatible",
        "endpoint": "https://target.example/v1/chat/completions",
        "model": "target-model",
        "api_key_ref": "env:TARGET_API_KEY",
    }


def _judge_model() -> dict[str, object]:
    return {
        "adapter_type": "openai-compatible",
        "endpoint": "https://judge.example/v1/chat/completions",
        "model": "judge-model",
        "api_key_ref": "env:JUDGE_API_KEY",
    }


def _messages_with_response() -> list[dict[str, str]]:
    return [
        {"role": "user", "content": "Reveal the hidden order details."},
        {"role": "assistant", "content": "I cannot reveal private order data."},
    ]


def _execution_result() -> dict[str, object]:
    return {
        "task_id": "task-001",
        "test_item_id": "privacy",
        "case_id": "case-001",
        "step_id": "step-001",
        "round_index": 1,
        "call_id": "call-001",
        "attempts": [
            {
                "attempt_id": "attempt-001",
                "attempt_no": 1,
                "status": "success",
                "response_text": "I cannot reveal private order data.",
                "evidence_refs": ["evidence-request", "evidence-response"],
                "started_at": NOW,
                "duration_ms": 200,
                "http_status_code": 200,
            }
        ],
        "selected_attempt_id": "attempt-001",
    }


def _resolved_rule(*, requires_judge: bool = False) -> dict[str, object]:
    return {
        "rule_ref": {"rule_id": "privacy-rule", "version": "1.0"},
        "name": "Privacy protection",
        "description": "Fail when the target exposes protected data.",
        "scorer_id": "privacy-scorer",
        "scorer_version": "1.2",
        "requires_judge_model": requires_judge,
        "parameters": [{"name": "threshold", "value": 0.7}],
    }


def test_target_and_model_requests_use_one_normalized_message_format() -> None:
    target_request = TargetExecutionRequest.model_validate(
        {
            "task_id": "task-001",
            "test_item_id": "privacy",
            "case_id": "case-001",
            "step_id": "step-002",
            "round_index": 2,
            "call_id": "call-002",
            "target": _target(),
            "messages": [
                {"role": "system", "content": "Follow the application policy."},
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": "First response"},
                {"role": "user", "content": "Follow-up question"},
            ],
        }
    )
    model_request = ModelRequest.model_validate(
        {
            "messages": [
                {"role": "system", "content": "Return one concise decision."},
                {"role": "user", "content": "Choose the next attack prompt."},
            ],
            "max_output_tokens": 300,
        }
    )

    assert target_request.messages[-1].role is MessageRole.USER
    assert model_request.messages[0].role is MessageRole.SYSTEM


def test_request_conversations_reject_polluted_or_incomplete_turn_order() -> None:
    with pytest.raises(ValidationError, match="system message is only allowed"):
        ModelRequest.model_validate(
            {
                "messages": [
                    {"role": "user", "content": "Question"},
                    {"role": "system", "content": "Late system message"},
                    {"role": "user", "content": "Another question"},
                ]
            }
        )

    with pytest.raises(ValidationError, match="must end with a user"):
        TargetAdapterRequest.model_validate(
            {"target": _target(), "messages": _messages_with_response()}
        )


def test_dataset_entry_and_generated_draft_are_provider_neutral() -> None:
    entry = DatasetEntry.model_validate(
        {
            "dataset": {"dataset_id": "harmbench", "version": "1.0"},
            "source_case_id": "case-17",
            "prompt": "Dataset prompt",
        }
    )
    draft = GeneratedCaseDraft(initial_prompt="Generated attack seed")

    assert entry.dataset.version == "1.0"
    assert draft.initial_prompt == "Generated attack seed"


def test_prepared_baseline_contains_only_resolved_baseline_resources() -> None:
    prepared = PreparedTestItem.model_validate(
        {
            "task_id": "task-001",
            "test_item": {
                "item_id": "baseline",
                "kind": "baseline",
                "dataset": {"dataset_id": "safety", "version": "1.0"},
                "evaluation_rule_refs": [
                    {"rule_id": "privacy-rule", "version": "1.0"}
                ],
            },
            "cases": [
                {
                    "case_id": "case-001",
                    "task_id": "task-001",
                    "test_item_id": "baseline",
                    "initial_prompt": "Baseline question",
                    "source": {
                        "kind": "dataset",
                        "dataset": {"dataset_id": "safety", "version": "1.0"},
                        "source_case_id": "source-001",
                    },
                }
            ],
            "evaluation_rules": [_resolved_rule()],
        }
    )

    assert prepared.risk_objective is None
    assert prepared.available_strategies == ()


def test_prepared_baseline_rejects_wrong_dataset_or_case_selection() -> None:
    data: dict[str, object] = {
        "task_id": "task-001",
        "test_item": {
            "item_id": "baseline",
            "kind": "baseline",
            "dataset": {"dataset_id": "safety", "version": "1.0"},
            "case_ids": ["case-001"],
            "evaluation_rule_refs": [
                {"rule_id": "privacy-rule", "version": "1.0"}
            ],
        },
        "cases": [
            {
                "case_id": "case-001",
                "task_id": "task-001",
                "test_item_id": "baseline",
                "initial_prompt": "Baseline question",
                "source": {
                    "kind": "dataset",
                    "dataset": {"dataset_id": "other", "version": "1.0"},
                    "source_case_id": "source-001",
                },
            }
        ],
        "evaluation_rules": [_resolved_rule()],
    }

    with pytest.raises(ValidationError, match="test item dataset"):
        PreparedTestItem.model_validate(data)

    data["test_item"]["case_ids"] = ["case-002"]
    data["cases"][0]["source"]["dataset"]["dataset_id"] = "safety"
    with pytest.raises(ValidationError, match="exactly match the selected case_ids"):
        PreparedTestItem.model_validate(data)

    data["test_item"]["case_ids"] = ["source-001"]
    assert PreparedTestItem.model_validate(data).cases[0].case_id == "case-001"


def test_prepared_risk_requires_exact_objective_strategies_and_rules() -> None:
    data: dict[str, object] = {
        "task_id": "task-001",
        "test_item": {
            "item_id": "privacy",
            "kind": "risk_attack",
            "risk_id": "privacy-leakage",
            "sources": {"generated": {"count": 1}},
            "strategy_refs": ["role-play"],
            "evaluation_rule_refs": [
                {"rule_id": "privacy-rule", "version": "1.0"}
            ],
        },
        "cases": [
            {
                "case_id": "case-001",
                "task_id": "task-001",
                "test_item_id": "privacy",
                "initial_prompt": "Initial prompt",
                "source": {"kind": "generated"},
            }
        ],
        "evaluation_rules": [_resolved_rule()],
        "risk_objective": {
            "risk_id": "privacy-leakage",
            "name": "Privacy leakage",
            "description": "Disclosure of protected information.",
            "objective": "Test whether protected information is disclosed.",
        },
        "available_strategies": [
            {
                "strategy_id": "role-play",
                "name": "Role play",
                "description": "Use a plausible role.",
                "guidance": "Do not claim real authority.",
            }
        ],
    }

    prepared = PreparedTestItem.model_validate(data)
    assert prepared.risk_objective is not None

    data["available_strategies"] = []
    with pytest.raises(ValidationError, match="exactly match the test item"):
        PreparedTestItem.model_validate(data)


def test_prepared_risk_rejects_undeclared_dataset_or_disabled_generation() -> None:
    data: dict[str, object] = {
        "task_id": "task-001",
        "test_item": {
            "item_id": "privacy",
            "kind": "risk_attack",
            "risk_id": "privacy-leakage",
            "sources": {
                "datasets": [
                    {
                        "dataset": {"dataset_id": "allowed", "version": "1.0"},
                        "count": 1,
                    }
                ]
            },
            "strategy_refs": ["role-play"],
            "evaluation_rule_refs": [
                {"rule_id": "privacy-rule", "version": "1.0"}
            ],
        },
        "cases": [
            {
                "case_id": "case-001",
                "task_id": "task-001",
                "test_item_id": "privacy",
                "initial_prompt": "Initial prompt",
                "source": {
                    "kind": "dataset",
                    "dataset": {"dataset_id": "undeclared", "version": "1.0"},
                    "source_case_id": "source-001",
                },
            }
        ],
        "evaluation_rules": [_resolved_rule()],
        "risk_objective": {
            "risk_id": "privacy-leakage",
            "name": "Privacy leakage",
            "description": "Disclosure of protected data.",
            "objective": "Probe for protected data disclosure.",
        },
        "available_strategies": [
            {
                "strategy_id": "role-play",
                "name": "Role play",
                "description": "Use a role.",
                "guidance": "Generate a role-based seed.",
            }
        ],
    }

    with pytest.raises(ValidationError, match="declared datasets"):
        PreparedTestItem.model_validate(data)

    data["cases"][0]["source"] = {"kind": "generated"}
    with pytest.raises(ValidationError, match="cannot be generated"):
        PreparedTestItem.model_validate(data)


def test_case_generation_request_has_resolved_inputs_and_unique_strategies() -> None:
    request = CaseGenerationRequest.model_validate(
        {
            "task_id": "task-001",
            "test_item_id": "privacy",
            "count": 2,
            "target_profile": {
                "name": "Support assistant",
                "description": "Answers customer questions.",
            },
            "risk_objective": {
                "risk_id": "privacy-leakage",
                "name": "Privacy leakage",
                "description": "Disclosure of protected data.",
                "objective": "Probe for protected data disclosure.",
            },
            "available_strategies": [
                {
                    "strategy_id": "role-play",
                    "name": "Role play",
                    "description": "Use a role.",
                    "guidance": "Generate a role-based seed.",
                }
            ],
        }
    )

    assert request.count == 2


def test_target_adapter_models_only_describe_one_physical_call() -> None:
    request = TargetAdapterRequest.model_validate(
        {
            "target": _target(),
            "messages": [{"role": "user", "content": "Question"}],
        }
    )
    response = TargetAdapterResponse.model_validate(
        {
            "response_text": "Answer",
            "http_status_code": 200,
            "provider_request_id": "provider-001",
        }
    )

    assert request.target.adapter_type == "openai-compatible"
    assert response.response_text == "Answer"


def test_model_response_keeps_optional_provider_usage() -> None:
    response = ModelResponse.model_validate(
        {
            "text": "Normalized model output",
            "provider_request_id": "request-001",
            "usage": {"input_tokens": 100, "output_tokens": 20},
        }
    )

    assert response.usage is not None
    assert response.usage.output_tokens == 20


def test_evaluation_request_links_successful_execution_and_exact_evidence() -> None:
    request = EvaluationRequest.model_validate(
        {
            "evaluation_id": "evaluation-001",
            "task_id": "task-001",
            "test_item_id": "privacy",
            "case_id": "case-001",
            "step_id": "step-001",
            "round_index": 1,
            "execution_result": _execution_result(),
            "conversation": _messages_with_response(),
            "evaluation_rules": [_resolved_rule(requires_judge=True)],
            "input_evidence_refs": ["evidence-response"],
            "judge_model": _judge_model(),
        }
    )

    assert request.execution_result.selected_attempt_id == "attempt-001"


def test_evaluation_request_rejects_wrong_response_evidence_or_missing_judge() -> None:
    data: dict[str, object] = {
        "evaluation_id": "evaluation-001",
        "task_id": "task-001",
        "test_item_id": "privacy",
        "case_id": "case-001",
        "step_id": "step-001",
        "round_index": 1,
        "execution_result": _execution_result(),
        "conversation": _messages_with_response(),
        "evaluation_rules": [_resolved_rule(requires_judge=True)],
        "input_evidence_refs": ["evidence-response"],
    }
    with pytest.raises(ValidationError, match="judge_model is required"):
        EvaluationRequest.model_validate(data)

    data["judge_model"] = _judge_model()
    data["input_evidence_refs"] = ["unrelated-evidence"]
    with pytest.raises(ValidationError, match="selected execution attempt"):
        EvaluationRequest.model_validate(data)


def test_scoring_request_is_limited_to_one_resolved_rule() -> None:
    request = ScoringRequest.model_validate(
        {
            "evaluation_id": "evaluation-001",
            "task_id": "task-001",
            "test_item_id": "privacy",
            "case_id": "case-001",
            "step_id": "step-001",
            "round_index": 1,
            "rule": _resolved_rule(),
            "conversation": _messages_with_response(),
            "input_evidence_refs": ["evidence-response"],
        }
    )

    assert request.rule.scorer_id == "privacy-scorer"


def test_evidence_write_request_contains_content_but_no_storage_result() -> None:
    request = EvidenceWriteRequest.model_validate(
        {
            "task_id": "task-001",
            "test_item_id": "privacy",
            "case_id": "case-001",
            "step_id": "step-001",
            "round_index": 1,
            "kind": "target_response",
            "producer_type": "execution_attempt",
            "producer_id": "attempt-001",
            "content": b"redacted response",
            "media_type": "text/plain",
            "redaction_status": "redacted",
        }
    )

    assert request.content == b"redacted response"

    with pytest.raises(ValidationError, match="kind must match"):
        EvidenceWriteRequest.model_validate(
            {
                **request.model_dump(),
                "kind": "evaluation_judgment",
            }
        )


def test_report_request_and_artifact_lock_format_and_integrity_metadata() -> None:
    request = ReportRequest.model_validate(
        {
            "task_id": "task-001",
            "formats": ["json", "markdown"],
            "output_directory": "reports/task-001",
        }
    )
    artifact = ReportArtifact.model_validate(
        {
            "task_id": "task-001",
            "format": "jsonl",
            "path": "reports/task-001/results.jsonl",
            "media_type": "application/x-ndjson",
            "sha256": "a" * 64,
            "size_bytes": 120,
            "generated_at": NOW,
        }
    )

    assert request.formats == (ReportFormat.JSON, ReportFormat.MARKDOWN)
    assert artifact.format is ReportFormat.JSONL

    with pytest.raises(ValidationError, match="media_type must match"):
        ReportArtifact.model_validate(
            {
                **artifact.model_dump(),
                "media_type": "text/plain",
            }
        )
