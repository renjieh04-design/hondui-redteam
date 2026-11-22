"""The public Interface surface that module implementations must satisfy."""

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from redteam.core.interfaces import (
    AttackStrategyProvider,
    Attacker,
    AttackerError,
    CaseGenerator,
    DatasetProvider,
    Evaluator,
    EvaluationRuleResolver,
    EvidenceStore,
    ModelClient,
    ReportExporter,
    RunRepository,
    Scorer,
    TargetAdapter,
    TargetAdapterError,
    TargetExecutor,
    TaskDefinitionLoader,
    TaskResourceResolver,
    TaskRunner,
)
from redteam.core.models import (
    ExecutionErrorType,
    RetryableErrorType,
    TaskRunRecords,
)


class _LoaderAdapter:
    def load(self, config_path: Path) -> object:
        return config_path


class _DatasetAdapter:
    def load(self, reference: object) -> tuple[object, ...]:
        return (reference,)


class _CaseGeneratorAdapter:
    async def generate(self, request: object) -> tuple[object, ...]:
        return (request,)


class _StrategyAdapter:
    def resolve(self, strategy_id: str) -> object:
        return strategy_id


class _RuleAdapter:
    def resolve(self, reference: object) -> object:
        return reference


class _ResourceAdapter:
    async def prepare(self, task: object, test_item: object) -> object:
        return (task, test_item)


class _AttackerAdapter:
    async def decide(self, context: object) -> object:
        return context


class _ModelAdapter:
    async def complete(self, request: object) -> object:
        return request


class _TargetAdapter:
    async def invoke(self, request: object) -> object:
        return request


class _TargetExecutorAdapter:
    async def execute_once(
        self,
        request: object,
        *,
        attempt_no: int,
    ) -> object:
        return (request, attempt_no)


class _ScorerAdapter:
    async def score(self, request: object) -> object:
        return request


class _EvaluatorAdapter:
    async def evaluate(self, request: object) -> object:
        return request


class _RepositoryAdapter:
    def save_task_definition(self, value: object) -> None: ...

    def save_task_context(self, value: object) -> None: ...

    def save_test_case(self, value: object) -> None: ...

    def save_step_context(self, value: object) -> None: ...

    def save_attack_decision(self, value: object) -> None: ...

    def save_execution_result(self, value: object) -> None: ...

    def save_evaluation_result(self, value: object) -> None: ...

    def save_evidence_reference(self, value: object) -> None: ...

    def load_task_run(self, task_id: str) -> object:
        return task_id


class _EvidenceAdapter:
    def write(self, request: object) -> object:
        return request

    def read(self, reference: object) -> bytes:
        return b"evidence"


class _ReportAdapter:
    def export(self, request: object) -> tuple[object, ...]:
        return (request,)


class _RunnerAdapter:
    async def run(self, task: object) -> object:
        return task


def test_structural_adapters_satisfy_every_public_protocol() -> None:
    adapters_and_interfaces = (
        (_LoaderAdapter(), TaskDefinitionLoader),
        (_DatasetAdapter(), DatasetProvider),
        (_CaseGeneratorAdapter(), CaseGenerator),
        (_StrategyAdapter(), AttackStrategyProvider),
        (_RuleAdapter(), EvaluationRuleResolver),
        (_ResourceAdapter(), TaskResourceResolver),
        (_AttackerAdapter(), Attacker),
        (_ModelAdapter(), ModelClient),
        (_TargetAdapter(), TargetAdapter),
        (_TargetExecutorAdapter(), TargetExecutor),
        (_ScorerAdapter(), Scorer),
        (_EvaluatorAdapter(), Evaluator),
        (_RepositoryAdapter(), RunRepository),
        (_EvidenceAdapter(), EvidenceStore),
        (_ReportAdapter(), ReportExporter),
        (_RunnerAdapter(), TaskRunner),
    )

    for adapter, interface in adapters_and_interfaces:
        assert isinstance(adapter, interface)


def test_external_calls_and_orchestration_are_async() -> None:
    async_methods = (
        CaseGenerator.generate,
        TaskResourceResolver.prepare,
        Attacker.decide,
        ModelClient.complete,
        TargetAdapter.invoke,
        TargetExecutor.execute_once,
        Scorer.score,
        Evaluator.evaluate,
        TaskRunner.run,
    )

    assert all(inspect.iscoroutinefunction(method) for method in async_methods)


def test_local_loading_persistence_and_reporting_are_synchronous() -> None:
    sync_methods = (
        TaskDefinitionLoader.load,
        DatasetProvider.load,
        AttackStrategyProvider.resolve,
        EvaluationRuleResolver.resolve,
        RunRepository.save_task_context,
        RunRepository.load_task_run,
        EvidenceStore.write,
        EvidenceStore.read,
        ReportExporter.export,
    )

    assert not any(inspect.iscoroutinefunction(method) for method in sync_methods)


def test_retryable_failures_expose_only_normalized_retry_categories() -> None:
    attacker_error = AttackerError(
        "The attacker model timed out.",
        retryable_error_type=RetryableErrorType.TIMEOUT,
    )
    target_error = TargetAdapterError(
        "The target rate limited the request.",
        error_type=ExecutionErrorType.RATE_LIMIT_ERROR,
        retryable_error_type=RetryableErrorType.RATE_LIMIT_ERROR,
        http_status_code=429,
        provider_request_id="provider-001",
    )

    assert attacker_error.retryable_error_type is RetryableErrorType.TIMEOUT
    assert target_error.retryable_error_type is RetryableErrorType.RATE_LIMIT_ERROR
    assert target_error.http_status_code == 429


def test_task_run_records_reconstruct_one_typed_task() -> None:
    records = TaskRunRecords.model_validate(
        {
            "task_definition": {
                "task_id": "task-001",
                "name": "Baseline run",
                "target": {
                    "name": "Target",
                    "description": "A test target.",
                    "adapter_type": "openai-compatible",
                    "endpoint": "https://example.test/v1/chat/completions",
                },
                "test_items": [
                    {
                        "item_id": "baseline",
                        "kind": "baseline",
                        "dataset": {"dataset_id": "dataset", "version": "1.0"},
                        "evaluation_rule_refs": [
                            {"rule_id": "rule", "version": "1.0"}
                        ],
                    }
                ],
            },
            "task_context": {
                "task_id": "task-001",
                "test_item_progress": [{"test_item_id": "baseline"}],
                "created_at": "2026-11-22T00:00:00Z",
                "updated_at": "2026-11-22T00:00:00Z",
            },
        }
    )

    assert records.task_definition.task_id == records.task_context.task_id

    data = records.model_dump()
    data["task_context"]["task_id"] = "another-task"
    with pytest.raises(ValidationError, match="must belong to task_definition"):
        TaskRunRecords.model_validate(data)


def test_task_run_records_reject_cross_record_baseline_mismatch() -> None:
    data: dict[str, object] = {
        "task_definition": {
            "task_id": "task-001",
            "name": "Baseline run",
            "target": {
                "name": "Target",
                "description": "A test target.",
                "adapter_type": "openai-compatible",
                "endpoint": "https://example.test/v1/chat/completions",
            },
            "test_items": [
                {
                    "item_id": "baseline",
                    "kind": "baseline",
                    "dataset": {"dataset_id": "dataset", "version": "1.0"},
                    "evaluation_rule_refs": [
                        {"rule_id": "rule", "version": "1.0"}
                    ],
                }
            ],
        },
        "task_context": {
            "task_id": "task-001",
            "test_item_progress": [{"test_item_id": "baseline"}],
            "created_at": "2026-11-22T00:00:00Z",
            "updated_at": "2026-11-22T00:00:00Z",
        },
        "test_cases": [
            {
                "case_id": "case-001",
                "task_id": "task-001",
                "test_item_id": "baseline",
                "initial_prompt": "Question",
                "source": {
                    "kind": "dataset",
                    "dataset": {"dataset_id": "other", "version": "1.0"},
                    "source_case_id": "source-001",
                },
            }
        ],
    }

    with pytest.raises(ValidationError, match="test item dataset"):
        TaskRunRecords.model_validate(data)


def test_task_run_records_reject_step_context_mismatching_current_case() -> None:
    data: dict[str, object] = {
        "task_definition": {
            "task_id": "task-001",
            "name": "Risk run",
            "target": {
                "name": "Target",
                "description": "A test target.",
                "adapter_type": "openai-compatible",
                "endpoint": "https://example.test/v1/chat/completions",
            },
            "attacker_model": {
                "adapter_type": "openai-compatible",
                "endpoint": "https://attacker.example.test/v1/chat/completions",
                "model": "attacker",
            },
            "test_items": [
                {
                    "item_id": "risk",
                    "kind": "risk_attack",
                    "risk_id": "risk-a",
                    "sources": {"generated": {"count": 2}},
                    "strategy_refs": ["direct"],
                    "evaluation_rule_refs": [
                        {"rule_id": "rule", "version": "1.0"}
                    ],
                }
            ],
        },
        "task_context": {
            "task_id": "task-001",
            "current_test_item_id": "risk",
            "current_case_id": "case-001",
            "current_step_id": "step-002",
            "test_item_progress": [{"test_item_id": "risk"}],
            "created_at": "2026-11-22T00:00:00Z",
            "updated_at": "2026-11-22T00:00:00Z",
        },
        "test_cases": [
            {
                "case_id": "case-001",
                "task_id": "task-001",
                "test_item_id": "risk",
                "initial_prompt": "Question 1",
                "source": {"kind": "generated"},
            },
            {
                "case_id": "case-002",
                "task_id": "task-001",
                "test_item_id": "risk",
                "initial_prompt": "Question 2",
                "source": {"kind": "generated"},
            },
        ],
        "step_contexts": [
            {
                "step_id": "step-001",
                "task_id": "task-001",
                "test_item_id": "risk",
                "case_id": "case-001",
                "round_index": 1,
                "max_rounds": 1,
                "target_profile": {
                    "name": "Target",
                    "description": "A test target.",
                },
                "risk_objective": {
                    "risk_id": "risk-a",
                    "name": "Risk",
                    "description": "Risk description.",
                    "objective": "Test risk.",
                },
                "available_strategies": [
                    {
                        "strategy_id": "direct",
                        "name": "Direct",
                        "description": "Direct prompt.",
                        "guidance": "Use direct wording.",
                    }
                ],
            },
            {
                "step_id": "step-002",
                "task_id": "task-001",
                "test_item_id": "risk",
                "case_id": "case-002",
                "round_index": 1,
                "max_rounds": 1,
                "target_profile": {
                    "name": "Target",
                    "description": "A test target.",
                },
                "risk_objective": {
                    "risk_id": "risk-a",
                    "name": "Risk",
                    "description": "Risk description.",
                    "objective": "Test risk.",
                },
                "available_strategies": [
                    {
                        "strategy_id": "direct",
                        "name": "Direct",
                        "description": "Direct prompt.",
                        "guidance": "Use direct wording.",
                    }
                ],
            },
        ],
    }

    with pytest.raises(
        ValidationError,
        match="current_step_id must belong to current test item and case",
    ):
        TaskRunRecords.model_validate(data)


def test_task_run_records_reject_duplicate_execution_lineage() -> None:
    data: dict[str, object] = {
        "task_definition": {
            "task_id": "task-001",
            "name": "Baseline run",
            "target": {
                "name": "Target",
                "description": "A test target.",
                "adapter_type": "openai-compatible",
                "endpoint": "https://example.test/v1/chat/completions",
            },
            "test_items": [
                {
                    "item_id": "baseline",
                    "kind": "baseline",
                    "dataset": {"dataset_id": "dataset", "version": "1.0"},
                    "evaluation_rule_refs": [
                        {"rule_id": "rule", "version": "1.0"}
                    ],
                }
            ],
        },
        "task_context": {
            "task_id": "task-001",
            "test_item_progress": [{"test_item_id": "baseline"}],
            "created_at": "2026-11-22T00:00:00Z",
            "updated_at": "2026-11-22T00:00:00Z",
        },
        "test_cases": [
            {
                "case_id": "case-001",
                "task_id": "task-001",
                "test_item_id": "baseline",
                "initial_prompt": "Question",
                "source": {
                    "kind": "dataset",
                    "dataset": {"dataset_id": "dataset", "version": "1.0"},
                    "source_case_id": "source-001",
                },
            }
        ],
        "execution_results": [
            {
                "task_id": "task-001",
                "test_item_id": "baseline",
                "case_id": "case-001",
                "step_id": "step-001",
                "round_index": 1,
                "call_id": "call-001",
                "attempts": [
                    {
                        "attempt_id": "attempt-001",
                        "attempt_no": 1,
                        "status": "error",
                        "error": {"error_type": "unknown", "message": "failed"},
                        "started_at": "2026-11-22T00:00:00Z",
                        "duration_ms": 1,
                    }
                ],
            },
            {
                "task_id": "task-001",
                "test_item_id": "baseline",
                "case_id": "case-001",
                "step_id": "step-001",
                "round_index": 1,
                "call_id": "call-002",
                "attempts": [
                    {
                        "attempt_id": "attempt-002",
                        "attempt_no": 1,
                        "status": "error",
                        "error": {"error_type": "unknown", "message": "failed again"},
                        "started_at": "2026-11-22T00:00:01Z",
                        "duration_ms": 1,
                    }
                ],
            },
        ],
    }

    with pytest.raises(ValidationError, match="unique per task, case, step, and round"):
        TaskRunRecords.model_validate(data)
