"""A complete typed read model for one persisted task run."""

from collections import Counter
from typing import Self

from pydantic import model_validator

from redteam.core.models.case import TestCase
from redteam.core.models.context import TaskContext
from redteam.core.models.decision import AttackDecision
from redteam.core.models.evaluation import EvaluationResult, EvaluationStatus
from redteam.core.models.evidence import EvidenceKind, EvidenceReference
from redteam.core.models.execution import ExecutionResult, ExecutionStatus
from redteam.core.models.step import StepContext
from redteam.core.models.task import (
    BaselineTestSpec,
    RiskTestSpec,
    TaskDefinition,
)
from redteam.core.models.common import DomainModel


class TaskRunRecords(DomainModel):
    """All typed records required to inspect or export one task run."""

    task_definition: TaskDefinition
    task_context: TaskContext
    test_cases: tuple[TestCase, ...] = ()
    step_contexts: tuple[StepContext, ...] = ()
    attack_decisions: tuple[AttackDecision, ...] = ()
    execution_results: tuple[ExecutionResult, ...] = ()
    evaluation_results: tuple[EvaluationResult, ...] = ()
    evidence_references: tuple[EvidenceReference, ...] = ()

    @model_validator(mode="after")
    def validate_task_lineage_and_record_ids(self) -> Self:
        task_id = self.task_definition.task_id
        if self.task_context.task_id != task_id:
            raise ValueError("task_context must belong to task_definition")

        collections = (
            self.test_cases,
            self.step_contexts,
            self.attack_decisions,
            self.execution_results,
            self.evaluation_results,
            self.evidence_references,
        )
        if any(record.task_id != task_id for records in collections for record in records):
            raise ValueError("all task run records must belong to task_definition")

        test_items = {
            test_item.item_id: test_item
            for test_item in self.task_definition.test_items
        }
        progress_ids = {
            progress.test_item_id
            for progress in self.task_context.test_item_progress
        }
        if progress_ids != set(test_items):
            raise ValueError(
                "task context progress must cover exactly the task test items"
            )
        if (
            self.task_context.current_test_item_id is not None
            and self.task_context.current_test_item_id not in test_items
        ):
            raise ValueError(
                "task context current_test_item_id must refer to a task test item"
            )

        test_cases = {
            case.case_id: case
            for case in self.test_cases
        }
        if (
            self.task_context.current_case_id is not None
            and self.task_context.current_case_id not in test_cases
        ):
            raise ValueError(
                "task context current_case_id must refer to an existing test case"
            )
        if self.task_context.current_case_id is not None:
            current_case = test_cases[self.task_context.current_case_id]
            if (
                self.task_context.current_test_item_id is not None
                and current_case.test_item_id
                != self.task_context.current_test_item_id
            ):
                raise ValueError(
                    "task context current_case_id must belong to current_test_item_id"
                )
        for case in self.test_cases:
            test_item = test_items.get(case.test_item_id)
            if test_item is None:
                raise ValueError("test case must belong to a task test item")

            if isinstance(test_item, BaselineTestSpec):
                if case.source.kind != "dataset":
                    raise ValueError("baseline test cases must come from datasets")
                if (
                    case.source.dataset.dataset_id
                    != test_item.dataset.dataset_id
                    or case.source.dataset.version != test_item.dataset.version
                ):
                    raise ValueError(
                        "baseline test case must come from the test item dataset"
                    )
                if (
                    test_item.case_ids is not None
                    and case.source.source_case_id not in test_item.case_ids
                ):
                    raise ValueError(
                        "baseline test case must be selected by case_ids"
                    )
            elif isinstance(test_item, RiskTestSpec):
                if case.source.kind == "dataset":
                    source_keys = {
                        (
                            sample.dataset.dataset_id,
                            sample.dataset.version,
                        )
                        for sample in test_item.sources.datasets
                    }
                    if (
                        case.source.dataset.dataset_id,
                        case.source.dataset.version,
                    ) not in source_keys:
                        raise ValueError(
                            "risk test case must come from an allowed dataset"
                        )
                elif case.source.kind == "generated":
                    if test_item.sources.generated is None:
                        raise ValueError(
                            "risk test case cannot be generated by this test item"
                        )

        for test_item_id, test_item in test_items.items():
            if isinstance(test_item, BaselineTestSpec):
                baseline_cases = [
                    case
                    for case in self.test_cases
                    if case.test_item_id == test_item_id
                ]
                baseline_source_keys = [
                    (
                        case.source.dataset.dataset_id,
                        case.source.dataset.version,
                        case.source.source_case_id,
                    )
                    for case in baseline_cases
                ]
                if len(baseline_source_keys) != len(set(baseline_source_keys)):
                    raise ValueError("baseline dataset source case IDs must be unique")
                if test_item.case_ids is not None:
                    prepared_source_ids = Counter(
                        case.source.source_case_id
                        for case in baseline_cases
                    )
                    if prepared_source_ids != Counter(test_item.case_ids):
                        raise ValueError(
                            "task run baseline cases must exactly match selected case_ids"
                        )
            elif isinstance(test_item, RiskTestSpec):
                actual_dataset_counts: Counter[tuple[str, str]] = Counter()
                actual_generated_count = 0
                risk_source_keys: list[tuple[str, str, str]] = []
                for case in self.test_cases:
                    if case.test_item_id != test_item_id:
                        continue
                    if case.source.kind == "dataset":
                        actual_dataset_counts[
                            (
                                case.source.dataset.dataset_id,
                                case.source.dataset.version,
                            )
                        ] += 1
                        risk_source_keys.append(
                            (
                                case.source.dataset.dataset_id,
                                case.source.dataset.version,
                                case.source.source_case_id,
                            )
                        )
                    elif case.source.kind == "generated":
                        actual_generated_count += 1

                if len(risk_source_keys) != len(set(risk_source_keys)):
                    raise ValueError("risk dataset source case IDs must be unique")

                expected_dataset_counts: Counter[tuple[str, str]] = Counter()
                for sample in test_item.sources.datasets:
                    expected_dataset_counts[
                        (sample.dataset.dataset_id, sample.dataset.version)
                    ] += sample.count
                if actual_dataset_counts != expected_dataset_counts:
                    raise ValueError(
                        "task run risk dataset case counts must match the test item sources"
                    )
                expected_generated_count = (
                    test_item.sources.generated.count
                    if test_item.sources.generated is not None
                    else 0
                )
                if actual_generated_count != expected_generated_count:
                    raise ValueError(
                        "task run generated case count must match the test item source"
                    )

        step_contexts = {
            (
                context.task_id,
                context.test_item_id,
                context.case_id,
                context.step_id,
                context.round_index,
            ): context
            for context in self.step_contexts
        }
        if (
            self.task_context.current_step_id is not None
            and self.task_context.current_step_id not in {
                context.step_id
                for context in self.step_contexts
            }
        ):
            raise ValueError(
                "task context current_step_id must refer to an existing step context"
            )
        if self.task_context.current_step_id is not None:
            matching_current_steps = [
                context
                for context in self.step_contexts
                if context.step_id == self.task_context.current_step_id
            ]
            if not any(
                context.test_item_id
                == self.task_context.current_test_item_id
                and context.case_id == self.task_context.current_case_id
                for context in matching_current_steps
            ):
                raise ValueError(
                    "task context current_step_id must belong to current test item and case"
                )
        for context in self.step_contexts:
            case = test_cases.get(context.case_id)
            test_item = test_items.get(context.test_item_id)
            if case is None or case.test_item_id != context.test_item_id:
                raise ValueError("step context must belong to an existing test case")
            if not isinstance(test_item, RiskTestSpec):
                raise ValueError("step contexts are only valid for risk test items")
            if context.max_rounds != test_item.max_rounds:
                raise ValueError(
                    "step context max_rounds must match the risk test item"
                )
            if context.risk_objective.risk_id != test_item.risk_id:
                raise ValueError(
                    "step context risk objective must match the risk test item"
                )
            if (
                test_item.objective is not None
                and context.risk_objective.objective != test_item.objective
            ):
                raise ValueError(
                    "step context objective must match the risk test item override"
                )
            context_strategy_ids = {
                strategy.strategy_id
                for strategy in context.available_strategies
            }
            if context_strategy_ids != set(test_item.strategy_refs):
                raise ValueError(
                    "step context strategies must exactly match the risk test item"
                )
            if context.round_index > test_item.max_rounds:
                raise ValueError("step context round exceeds test item max_rounds")

        for decision in self.attack_decisions:
            context = step_contexts.get(
                (
                    decision.task_id,
                    decision.test_item_id,
                    decision.case_id,
                    decision.step_id,
                    decision.round_index,
                )
            )
            if context is None:
                raise ValueError(
                    "attack decision must correspond to an existing step context"
                )
            if decision.strategy_id not in {
                strategy.strategy_id
                for strategy in context.available_strategies
            }:
                raise ValueError(
                    "attack decision strategy must refer to available_strategies"
                )

        execution_lineage_keys = [
            (
                result.task_id,
                result.test_item_id,
                result.case_id,
                result.step_id,
                result.round_index,
            )
            for result in self.execution_results
        ]
        if len(execution_lineage_keys) != len(set(execution_lineage_keys)):
            raise ValueError(
                "execution results must be unique per task, case, step, and round"
            )
        execution_results = dict(
            zip(execution_lineage_keys, self.execution_results)
        )
        for result in self.execution_results:
            case = test_cases.get(result.case_id)
            if (
                case is None
                or case.test_item_id != result.test_item_id
            ):
                raise ValueError(
                    "execution result must belong to an existing test case"
                )
            matching_context = step_contexts.get(
                (
                    result.task_id,
                    result.test_item_id,
                    result.case_id,
                    result.step_id,
                    result.round_index,
                )
            )
            test_item = test_items[result.test_item_id]
            if isinstance(test_item, BaselineTestSpec):
                if matching_context is not None:
                    raise ValueError(
                        "baseline execution cannot have a risk step context"
                    )
            elif matching_context is None:
                raise ValueError(
                    "risk execution must correspond to an existing step context"
                )

        evaluation_results = {
            (
                evaluation.task_id,
                evaluation.test_item_id,
                evaluation.case_id,
                evaluation.step_id,
                evaluation.round_index,
            ): evaluation
            for evaluation in self.evaluation_results
        }
        for evaluation in self.evaluation_results:
            execution = execution_results.get(
                (
                    evaluation.task_id,
                    evaluation.test_item_id,
                    evaluation.case_id,
                    evaluation.step_id,
                    evaluation.round_index,
                )
            )
            if execution is None:
                raise ValueError(
                    "evaluation must correspond to an existing execution result"
                )
            if execution.status is not ExecutionStatus.SUCCESS:
                raise ValueError(
                    "evaluation must correspond to a successful execution"
                )
            attempt_ids = {
                attempt.attempt_id
                for attempt in execution.attempts
            }
            if not set(evaluation.execution_attempt_ids).issubset(attempt_ids):
                raise ValueError(
                    "evaluation execution attempts must belong to its execution"
                )
            if (
                execution.selected_attempt_id is None
                or execution.selected_attempt_id
                not in evaluation.execution_attempt_ids
            ):
                raise ValueError(
                    "evaluation must include the selected execution attempt"
                )
            selected_attempt = next(
                attempt
                for attempt in execution.attempts
                if attempt.attempt_id == execution.selected_attempt_id
            )
            if not set(evaluation.input_evidence_refs).issubset(
                set(selected_attempt.evidence_refs)
            ):
                raise ValueError(
                    "evaluation input evidence must come from the selected execution attempt"
                )

            test_item = test_items.get(evaluation.test_item_id)
            if test_item is None:
                raise ValueError("evaluation must belong to a task test item")
            expected_rule_keys = {
                (rule.rule_id, rule.version)
                for rule in test_item.evaluation_rule_refs
            }
            actual_rule_keys = {
                (rule.rule_id, rule.version)
                for rule in evaluation.evaluation_rule_refs
            }
            if actual_rule_keys != expected_rule_keys:
                raise ValueError(
                    "evaluation rules must exactly match the test item"
                )

        evaluation_by_id = {
            evaluation.evaluation_id: evaluation
            for evaluation in self.evaluation_results
        }
        for evaluation in self.evaluation_results:
            if evaluation.supersedes_evaluation_id is None:
                continue
            previous = evaluation_by_id.get(
                evaluation.supersedes_evaluation_id
            )
            if previous is None:
                raise ValueError(
                    "superseded evaluation must exist in the task run"
                )
            evaluation_lineage = (
                evaluation.task_id,
                evaluation.test_item_id,
                evaluation.case_id,
                evaluation.step_id,
                evaluation.round_index,
            )
            previous_lineage = (
                previous.task_id,
                previous.test_item_id,
                previous.case_id,
                previous.step_id,
                previous.round_index,
            )
            if evaluation_lineage != previous_lineage:
                raise ValueError(
                    "superseded evaluation must have matching lineage"
                )
            if evaluation.evaluated_at <= previous.evaluated_at:
                raise ValueError(
                    "a superseding evaluation must be evaluated later"
                )

        for evaluation in self.evaluation_results:
            seen_evaluation_ids = {evaluation.evaluation_id}
            current_evaluation = evaluation
            while current_evaluation.supersedes_evaluation_id is not None:
                predecessor_id = current_evaluation.supersedes_evaluation_id
                if predecessor_id in seen_evaluation_ids:
                    raise ValueError(
                        "evaluation supersession chain cannot contain a cycle"
                    )
                seen_evaluation_ids.add(predecessor_id)
                predecessor = evaluation_by_id.get(predecessor_id)
                if predecessor is None:
                    break
                current_evaluation = predecessor

        evidence_ids = {
            evidence.evidence_id
            for evidence in self.evidence_references
        }
        if len(evidence_ids) != len(self.evidence_references):
            raise ValueError("evidence IDs must be unique within a task run")
        evidence_by_id = {
            evidence.evidence_id: evidence
            for evidence in self.evidence_references
        }

        for result in self.execution_results:
            for attempt in result.attempts:
                if not set(attempt.evidence_refs).issubset(evidence_ids):
                    raise ValueError(
                        "execution attempt evidence references must exist in task run records"
                    )
                for evidence_id in attempt.evidence_refs:
                    evidence = evidence_by_id[evidence_id]
                    if (
                        evidence.producer_type.value != "execution_attempt"
                        or evidence.producer_id != attempt.attempt_id
                        or evidence.task_id != result.task_id
                        or evidence.test_item_id != result.test_item_id
                        or evidence.case_id != result.case_id
                        or evidence.step_id != result.step_id
                        or evidence.round_index != result.round_index
                    ):
                        raise ValueError(
                            "execution evidence must be owned by the exact execution attempt"
                        )
                if attempt.status is ExecutionStatus.SUCCESS:
                    attempt_evidence_kinds = {
                        evidence_by_id[evidence_id].kind
                        for evidence_id in attempt.evidence_refs
                    }
                    if (
                        EvidenceKind.TARGET_REQUEST not in attempt_evidence_kinds
                        or EvidenceKind.TARGET_RESPONSE not in attempt_evidence_kinds
                    ):
                        raise ValueError(
                            "a successful execution attempt requires target request and response evidence"
                        )
        for evaluation in self.evaluation_results:
            evaluation_evidence_ids = set(evaluation.input_evidence_refs)
            evaluation_evidence_ids.update(evaluation.evidence_refs)
            for result in evaluation.scorer_results:
                evaluation_evidence_ids.update(result.evidence_refs)
            for error in evaluation.errors:
                evaluation_evidence_ids.update(error.evidence_refs)
            if not evaluation_evidence_ids.issubset(evidence_ids):
                raise ValueError(
                    "evaluation evidence references must exist in task run records"
                )
            if evaluation.status is EvaluationStatus.COMPLETED:
                judgment_evidence_ids = set(evaluation.evidence_refs)
                for result in evaluation.scorer_results:
                    judgment_evidence_ids.update(result.evidence_refs)
                judgment_evidence_kinds = {
                    evidence_by_id[evidence_id].kind
                    for evidence_id in judgment_evidence_ids
                }
                if EvidenceKind.EVALUATION_JUDGMENT not in judgment_evidence_kinds:
                    raise ValueError(
                        "a completed evaluation requires evaluation judgment evidence"
                    )

        for evidence in self.evidence_references:
            case = test_cases.get(evidence.case_id)
            if (
                case is None
                or case.test_item_id != evidence.test_item_id
            ):
                raise ValueError(
                    "evidence must belong to an existing test case"
                )

            if evidence.producer_type.value == "execution_attempt":
                matching_attempt = any(
                    attempt.attempt_id == evidence.producer_id
                    and evidence.evidence_id in attempt.evidence_refs
                    for result in self.execution_results
                    if (
                        result.test_item_id,
                        result.case_id,
                        result.step_id,
                        result.round_index,
                    ) == (
                        evidence.test_item_id,
                        evidence.case_id,
                        evidence.step_id,
                        evidence.round_index,
                    )
                    for attempt in result.attempts
                )
                if not matching_attempt:
                    raise ValueError(
                        "execution evidence producer must own the exact evidence reference"
                    )
            else:
                matching_evaluation = any(
                    evaluation.evaluation_id == evidence.producer_id
                    and (
                        evidence.evidence_id in evaluation.evidence_refs
                        or any(
                            evidence.evidence_id in result.evidence_refs
                            for result in evaluation.scorer_results
                        )
                        or any(
                            evidence.evidence_id in error.evidence_refs
                            for error in evaluation.errors
                        )
                    )
                    for evaluation in self.evaluation_results
                    if (
                        evaluation.test_item_id,
                        evaluation.case_id,
                        evaluation.step_id,
                        evaluation.round_index,
                    ) == (
                        evidence.test_item_id,
                        evidence.case_id,
                        evidence.step_id,
                        evidence.round_index,
                    )
                )
                if not matching_evaluation:
                    raise ValueError(
                        "evaluation evidence producer must own the exact evidence reference"
                    )

        attempt_ids = [
            attempt.attempt_id
            for execution in self.execution_results
            for attempt in execution.attempts
        ]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("execution attempt IDs must be unique within a task run")

        unique_id_groups = (
            ("case IDs", [record.case_id for record in self.test_cases]),
            ("step context IDs", [record.step_id for record in self.step_contexts]),
            ("attack decision step IDs", [record.step_id for record in self.attack_decisions]),
            ("execution call IDs", [record.call_id for record in self.execution_results]),
            ("evaluation IDs", [record.evaluation_id for record in self.evaluation_results]),
            ("evidence IDs", [record.evidence_id for record in self.evidence_references]),
        )
        for label, values in unique_id_groups:
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique within a task run")
        return self
