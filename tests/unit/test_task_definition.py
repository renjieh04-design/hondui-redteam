"""Validation tests for the public V1 task definition."""

import pytest
from pydantic import ValidationError

from redteam.core.models import TaskDefinition


def _rule(rule_id: str, version: str = "1.0") -> dict[str, str]:
    return {"rule_id": rule_id, "version": version}


def _target() -> dict[str, str]:
    return {
        "name": "customer-service-assistant",
        "description": "Answers order questions for the authenticated customer only.",
        "adapter_type": "openai_compatible",
        "endpoint": "https://target.example.test/v1/chat/completions",
        "api_key_ref": "env:TARGET_API_KEY",
    }


def _attacker_model() -> dict[str, str]:
    return {
        "adapter_type": "openai_compatible",
        "endpoint": "https://attacker.example.test/v1/chat/completions",
        "model": "attacker-model",
        "api_key_ref": "env:ATTACKER_API_KEY",
    }


def test_combines_baseline_and_risk_test_items() -> None:
    task = TaskDefinition.model_validate(
        {
            "task_id": "run-001",
            "name": "V1 combined test",
            "target": _target(),
            "attacker_model": _attacker_model(),
            "test_items": [
                {
                    "item_id": "baseline-1",
                    "kind": "baseline",
                    "dataset": {"dataset_id": "open-benchmark", "version": "1.0"},
                    "evaluation_rule_refs": [_rule("exact-answer")],
                },
                {
                    "item_id": "privacy-orders",
                    "kind": "risk_attack",
                    "risk_id": "privacy_leakage",
                    "objective": "Test access to other customers' orders.",
                    "sources": {
                        "datasets": [
                            {
                                "dataset": {
                                    "dataset_id": "privacy-prompts",
                                    "version": "2026-01",
                                },
                                "count": 20,
                            }
                        ],
                        "generated": {"count": 10},
                    },
                    "strategy_refs": ["direct", "role_play"],
                    "max_rounds": 5,
                    "evaluation_rule_refs": [
                        _rule("secret-match", "2.0"),
                        _rule("semantic-judge", "3.1"),
                    ],
                },
            ],
        }
    )

    assert len(task.test_items) == 2
    assert task.test_items[1].max_rounds == 5
    assert task.test_items[1].sources.generated.count == 10
    assert task.test_items[1].evaluation_rule_refs[1].version == "3.1"


def test_risk_test_requires_at_least_one_case_source() -> None:
    with pytest.raises(ValidationError, match="at least one dataset or generated source"):
        TaskDefinition.model_validate(
            {
                "task_id": "run-002",
                "name": "Missing source",
                "target": _target(),
                "test_items": [
                    {
                        "item_id": "risk-1",
                        "kind": "risk_attack",
                        "risk_id": "privacy_leakage",
                        "sources": {},
                        "strategy_refs": ["direct"],
                        "evaluation_rule_refs": [_rule("semantic-judge")],
                    }
                ],
            }
        )


def test_model_generated_cases_require_attacker_model() -> None:
    with pytest.raises(ValidationError, match="attacker_model is required"):
        TaskDefinition.model_validate(
            {
                "task_id": "run-003",
                "name": "Missing attacker model",
                "target": _target(),
                "test_items": [
                    {
                        "item_id": "risk-1",
                        "kind": "risk_attack",
                        "risk_id": "privacy_leakage",
                        "sources": {"generated": {"count": 5}},
                        "strategy_refs": ["direct"],
                        "evaluation_rule_refs": [_rule("semantic-judge")],
                    }
                ],
            }
        )


def test_test_item_ids_are_unique_within_task() -> None:
    with pytest.raises(ValidationError, match="test item IDs must be unique"):
        TaskDefinition.model_validate(
            {
                "task_id": "run-004",
                "name": "Duplicate item IDs",
                "target": _target(),
                "test_items": [
                    {
                        "item_id": "duplicate",
                        "kind": "baseline",
                        "dataset": {"dataset_id": "set-a", "version": "1"},
                        "evaluation_rule_refs": [_rule("rule-a")],
                    },
                    {
                        "item_id": "duplicate",
                        "kind": "baseline",
                        "dataset": {"dataset_id": "set-b", "version": "1"},
                        "evaluation_rule_refs": [_rule("rule-b")],
                    },
                ],
            }
        )


def test_public_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TaskDefinition.model_validate(
            {
                "task_id": "run-005",
                "name": "Unknown field",
                "target": {**_target(), "unexpected": True},
                "test_items": [
                    {
                        "item_id": "baseline-1",
                        "kind": "baseline",
                        "dataset": {"dataset_id": "set-a", "version": "1"},
                        "evaluation_rule_refs": [_rule("rule-a")],
                    }
                ],
            }
        )


def test_evaluation_rule_versions_must_be_explicit_and_unique() -> None:
    with pytest.raises(ValidationError, match="evaluation rule references must be unique"):
        TaskDefinition.model_validate(
            {
                "task_id": "run-006",
                "name": "Duplicate evaluation rules",
                "target": _target(),
                "test_items": [
                    {
                        "item_id": "baseline-1",
                        "kind": "baseline",
                        "dataset": {"dataset_id": "set-a", "version": "1"},
                        "evaluation_rule_refs": [
                            _rule("rule-a", "1.0"),
                            _rule("rule-a", "1.0"),
                        ],
                    }
                ],
            }
        )


def test_baseline_case_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="baseline case IDs must be unique"):
        TaskDefinition.model_validate(
            {
                "task_id": "run-006",
                "name": "Duplicate baseline case IDs",
                "target": _target(),
                "test_items": [
                    {
                        "item_id": "baseline-1",
                        "kind": "baseline",
                        "dataset": {"dataset_id": "set-a", "version": "1"},
                        "case_ids": ["case-a", "case-a"],
                        "evaluation_rule_refs": [_rule("rule-a")],
                    }
                ],
            }
        )


def test_risk_strategy_refs_must_be_unique() -> None:
    with pytest.raises(
        ValidationError,
        match="risk attack strategy references must be unique",
    ):
        TaskDefinition.model_validate(
            {
                "task_id": "run-007",
                "name": "Duplicate strategy references",
                "target": _target(),
                "test_items": [
                    {
                        "item_id": "risk-1",
                        "kind": "risk_attack",
                        "risk_id": "risk-a",
                        "sources": {
                            "datasets": [
                                {
                                    "dataset": {"dataset_id": "set-a", "version": "1"},
                                    "count": 1,
                                }
                            ]
                        },
                        "strategy_refs": ["direct", "direct"],
                        "evaluation_rule_refs": [_rule("rule-a")],
                    }
                ],
            }
        )


def test_legacy_string_evaluation_rule_reference_requires_migration() -> None:
    with pytest.raises(ValidationError):
        TaskDefinition.model_validate(
            {
                "task_id": "run-legacy",
                "name": "Legacy rule reference",
                "target": _target(),
                "test_items": [
                    {
                        "item_id": "baseline-1",
                        "kind": "baseline",
                        "dataset": {"dataset_id": "set-a", "version": "1"},
                        "evaluation_rule_refs": ["rule-a"],
                    }
                ],
            }
        )

    with pytest.raises(ValidationError, match="version must be resolved"):
        TaskDefinition.model_validate(
            {
                "task_id": "run-007",
                "name": "Unresolved evaluation rule",
                "target": _target(),
                "test_items": [
                    {
                        "item_id": "baseline-1",
                        "kind": "baseline",
                        "dataset": {"dataset_id": "set-a", "version": "1"},
                        "evaluation_rule_refs": [_rule("rule-a", "latest")],
                    }
                ],
            }
        )
