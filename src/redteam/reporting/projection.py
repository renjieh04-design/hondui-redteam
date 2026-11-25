"""Read-only report data and counts derived from persisted V1 runs."""

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from redteam.core.models import (
    CaseSource,
    EvaluationResult,
    EvaluationStatus,
    EvaluationVerdict,
    EvidenceReference,
    ExecutionAttempt,
    ExecutionError,
    ExecutionResult,
    ExecutionStatus,
    RiskTestSpec,
    TaskRunRecords,
    TaskStatus,
    TerminationReason,
    TestItemProgress,
    TestItemStatus,
)


class ProjectionModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class TargetProjection(ProjectionModel):
    name: str
    description: str
    adapter_type: str
    model: str | None


class AttemptProjection(ProjectionModel):
    attempt_id: str
    attempt_no: int
    status: ExecutionStatus
    started_at: datetime
    duration_ms: int
    http_status_code: int | None
    error: ExecutionError | None
    evidence_refs: tuple[str, ...]


class ExecutionProjection(ProjectionModel):
    call_id: str
    status: ExecutionStatus
    selected_attempt_id: str | None
    attempts: tuple[AttemptProjection, ...]


class StepProjection(ProjectionModel):
    step_id: str
    round_index: int
    strategy_id: str | None
    execution: ExecutionProjection | None
    evaluations: tuple[EvaluationResult, ...]
    evidence: tuple[EvidenceReference, ...]

    @property
    def effective_evaluation(self) -> EvaluationResult | None:
        """The latest stored evaluation, including an error if that is latest."""
        return self.evaluations[-1] if self.evaluations else None


class CaseProjection(ProjectionModel):
    case_id: str
    source: CaseSource
    skipped: bool | None
    attack_succeeded: bool | None
    steps: tuple[StepProjection, ...]


class ReportCounts(ProjectionModel):
    planned_cases: int | None
    recorded_cases: int
    completed_cases: int
    error_cases: int
    skipped_cases: int
    target_calls: int
    target_attempts: int
    failed_target_calls: int
    failed_target_attempts: int
    passed_steps: int
    failed_steps: int
    inconclusive_steps: int
    evaluation_error_steps: int
    unevaluated_successful_calls: int
    successful_risk_cases: int


class ItemProjection(ProjectionModel):
    item_id: str
    kind: Literal["baseline", "risk_attack"]
    risk_id: str | None
    max_rounds: int | None
    progress: TestItemProgress
    counts: ReportCounts
    cases: tuple[CaseProjection, ...]


class ReportProjection(ProjectionModel):
    task_id: str
    name: str
    target: TargetProjection
    status: TaskStatus
    started_at: datetime | None
    finished_at: datetime | None
    termination_reason: TerminationReason | None
    termination_detail: str | None
    test_item_count: int
    counts: ReportCounts
    items: tuple[ItemProjection, ...]


def _project_attempt(attempt: ExecutionAttempt) -> AttemptProjection:
    return AttemptProjection(
        attempt_id=attempt.attempt_id,
        attempt_no=attempt.attempt_no,
        status=attempt.status,
        started_at=attempt.started_at,
        duration_ms=attempt.duration_ms,
        http_status_code=attempt.http_status_code,
        error=attempt.error,
        evidence_refs=attempt.evidence_refs,
    )


def _project_execution(execution: ExecutionResult | None) -> ExecutionProjection | None:
    if execution is None:
        return None
    return ExecutionProjection(
        call_id=execution.call_id,
        status=execution.status,
        selected_attempt_id=execution.selected_attempt_id,
        attempts=tuple(_project_attempt(attempt) for attempt in execution.attempts),
    )


def _counts(
    cases: Iterable[CaseProjection], progress: tuple[TestItemProgress, ...]
) -> ReportCounts:
    cases = tuple(cases)
    steps = [step for case in cases for step in case.steps]
    executions = [step.execution for step in steps if step.execution is not None]
    attempts = [attempt for execution in executions for attempt in execution.attempts]
    evaluations = [step.effective_evaluation for step in steps]
    verdicts = Counter(result.verdict for result in evaluations if result is not None)
    known_totals = [item.total_cases for item in progress if item.total_cases is not None]
    return ReportCounts(
        planned_cases=sum(known_totals) if len(known_totals) == len(progress) else None,
        recorded_cases=len(cases),
        completed_cases=sum(item.completed_cases for item in progress),
        error_cases=sum(item.error_cases for item in progress),
        skipped_cases=sum(case.skipped is True for case in cases),
        target_calls=len(executions),
        target_attempts=len(attempts),
        failed_target_calls=sum(call.status is ExecutionStatus.ERROR for call in executions),
        failed_target_attempts=sum(attempt.status is ExecutionStatus.ERROR for attempt in attempts),
        passed_steps=verdicts[EvaluationVerdict.PASSED],
        failed_steps=verdicts[EvaluationVerdict.FAILED],
        inconclusive_steps=verdicts[EvaluationVerdict.INCONCLUSIVE],
        evaluation_error_steps=sum(
            result is not None and result.status is EvaluationStatus.ERROR
            for result in evaluations
        ),
        unevaluated_successful_calls=sum(
            step.execution is not None
            and step.execution.status is ExecutionStatus.SUCCESS
            and step.effective_evaluation is None
            for step in steps
        ),
        successful_risk_cases=sum(case.attack_succeeded is True for case in cases),
    )


def _risk_outcome(steps: tuple[StepProjection, ...], max_rounds: int | None) -> bool | None:
    if max_rounds is None:
        return None
    evaluations = tuple(step.effective_evaluation for step in steps)
    if any(result and result.verdict is EvaluationVerdict.FAILED for result in evaluations):
        return True
    if len(steps) == max_rounds and all(
        step.round_index == index
        and result is not None
        and result.verdict is EvaluationVerdict.PASSED
        for index, (step, result) in enumerate(zip(steps, evaluations), 1)
    ):
        return False
    return None


def project_run(records: TaskRunRecords) -> ReportProjection:
    """Build the shared input for the JSON, JSONL and Markdown renderers."""
    task = records.task_definition
    context = records.task_context
    progress = {item.test_item_id: item for item in context.test_item_progress}

    case_steps: dict[str, set[tuple[int, str]]] = defaultdict(set)
    for record in (*records.step_contexts, *records.execution_results):
        case_steps[record.case_id].add((record.round_index, record.step_id))
    executions = {(r.case_id, r.round_index, r.step_id): r for r in records.execution_results}
    strategies = {(r.case_id, r.round_index, r.step_id): r.strategy_id for r in records.attack_decisions}
    evaluations: dict[tuple[str, int, str], list[EvaluationResult]] = defaultdict(list)
    for evaluation in records.evaluation_results:
        evaluations[evaluation.case_id, evaluation.round_index, evaluation.step_id].append(evaluation)
    evidence: dict[tuple[str, int, str], list[EvidenceReference]] = defaultdict(list)
    for reference in records.evidence_references:
        evidence[reference.case_id, reference.round_index, reference.step_id].append(reference)

    cases_with_steps = Counter(
        case.test_item_id for case in records.test_cases if case_steps.get(case.case_id)
    )
    cases_by_item: dict[str, list[CaseProjection]] = defaultdict(list)
    round_limits = {
        item.item_id: item.max_rounds for item in task.test_items if isinstance(item, RiskTestSpec)
    }
    for case in sorted(records.test_cases, key=lambda case: case.case_id):
        steps = []
        for round_index, step_id in sorted(case_steps[case.case_id]):
            key = (case.case_id, round_index, step_id)
            steps.append(StepProjection(
                step_id=step_id,
                round_index=round_index,
                strategy_id=strategies.get(key),
                execution=_project_execution(executions.get(key)),
                evaluations=tuple(sorted(
                    evaluations[key], key=lambda result: (result.evaluated_at, result.evaluation_id)
                )),
                evidence=tuple(sorted(evidence[key], key=lambda ref: ref.evidence_id)),
            ))

        item_progress = progress[case.test_item_id]
        skipped = False
        if not steps and case.case_id != context.current_case_id:
            if context.finished_at is not None or item_progress.status is TestItemStatus.FAILED:
                # Cases can fail before a step is persisted. Aggregate progress
                # alone cannot identify which unobserved case failed.
                ambiguous = (
                    item_progress.error_cases > 0
                    or item_progress.completed_cases > cases_with_steps[case.test_item_id]
                    or item_progress.status in (
                        TestItemStatus.COMPLETED, TestItemStatus.COMPLETED_WITH_ERRORS
                    )
                )
                skipped = None if ambiguous else True
        case_projection = CaseProjection(
            case_id=case.case_id,
            source=case.source,
            skipped=skipped,
            attack_succeeded=_risk_outcome(tuple(steps), round_limits.get(case.test_item_id)),
            steps=tuple(steps),
        )
        cases_by_item[case.test_item_id].append(case_projection)

    items = tuple(
        ItemProjection(
            item_id=item.item_id,
            kind=item.kind,
            risk_id=item.risk_id if isinstance(item, RiskTestSpec) else None,
            max_rounds=round_limits.get(item.item_id),
            progress=progress[item.item_id],
            counts=_counts(cases_by_item[item.item_id], (progress[item.item_id],)),
            cases=tuple(cases_by_item[item.item_id]),
        )
        for item in task.test_items
    )
    return ReportProjection(
        task_id=task.task_id,
        name=task.name,
        target=TargetProjection(
            name=task.target.name,
            description=task.target.description,
            model=task.target.model,
            adapter_type=task.target.adapter_type,
        ),
        status=context.status,
        started_at=context.started_at,
        finished_at=context.finished_at,
        termination_reason=context.termination_reason,
        termination_detail=context.termination_detail,
        test_item_count=len(items),
        counts=_counts((case for item in items for case in item.cases), context.test_item_progress),
        items=items,
    )
