from datetime import UTC, datetime, timedelta

from redteam.core.models import TaskRunRecords
from redteam.reporting.projection import project_run


NOW = datetime(2026, 11, 25, tzinfo=UTC)
DATASET = {"dataset_id": "sample", "version": "1"}
RULE = {"rule_id": "output-format", "version": "1"}


def _case(case_id, item_id="baseline"):
    return {
        "task_id": "task",
        "test_item_id": item_id,
        "case_id": case_id,
        "initial_prompt": "Return the word apple.",
        "source": {"kind": "dataset", "dataset": DATASET, "source_case_id": case_id},
    }


def _lineage(case):
    return {
        "task_id": case["task_id"],
        "test_item_id": case["test_item_id"],
        "case_id": case["case_id"],
        "step_id": f'{case["case_id"]}-step',
        "round_index": 1,
    }


def _evidence(lineage, producer_id, kind, producer_type="execution_attempt"):
    evidence_id = f"{producer_id}-{kind}"
    return {
        **lineage,
        "evidence_id": evidence_id,
        "kind": kind,
        "producer_type": producer_type,
        "producer_id": producer_id,
        "storage_ref": f"evidence/{evidence_id}",
        "media_type": "text/plain",
        "sha256": "0" * 64,
        "size_bytes": 10,
        "redaction_status": "not_required",
        "recorded_at": NOW,
    }


def _execution(case, *, retry=False, success=True):
    lineage = _lineage(case)
    case_id = case["case_id"]
    attempts = []
    if retry or not success:
        attempts.append({
            "attempt_id": f"{case_id}-error",
            "attempt_no": 1,
            "status": "error",
            "started_at": NOW,
            "duration_ms": 15,
            "error": {"error_type": "timeout", "message": "Request timed out."},
        })
    selected = None
    evidence = []
    if success:
        selected = f"{case_id}-selected"
        evidence = [_evidence(lineage, selected, kind)
                    for kind in ("target_request", "target_response")]
        attempts.append({
            "attempt_id": selected,
            "attempt_no": len(attempts) + 1,
            "status": "success",
            "started_at": NOW + timedelta(seconds=1),
            "duration_ms": 10,
            "response_text": "Recorded response kept in the evidence store.",
            "evidence_refs": [ref["evidence_id"] for ref in evidence],
        })
    return {
        **lineage,
        "call_id": f"{case_id}-call",
        "attempts": attempts,
        "selected_attempt_id": selected,
    }, evidence


def _evaluation(case, evaluation_id, verdict, *, supersedes=None):
    lineage = _lineage(case)
    judgment = _evidence(lineage, evaluation_id, "evaluation_judgment", "evaluation")
    score = {"passed": 0.0, "failed": 1.0}[verdict]
    return {
        **lineage,
        "evaluation_id": evaluation_id,
        "execution_attempt_ids": [f'{case["case_id"]}-selected'],
        "input_evidence_refs": [f'{case["case_id"]}-selected-target_response'],
        "evaluation_rule_refs": [RULE],
        "status": "completed",
        "verdict": verdict,
        "risk_score": score,
        "reason": "Checked the expected output format.",
        "scorer_results": [{
            "rule_ref": RULE,
            "scorer_id": "format-check",
            "scorer_version": "1",
            "method_origin": "primary",
            "verdict": verdict,
            "risk_score": score,
            "reason": "Compared the result with the expected word.",
        }],
        "evidence_refs": [judgment["evidence_id"]],
        "evaluated_at": NOW + timedelta(seconds=3 if supersedes else 2),
        "supersedes_evaluation_id": supersedes,
    }, judgment


def _run(cases, *, status="completed", completed=1, errors=0):
    progress_status = {
        "completed": "completed",
        "completed_with_errors": "completed_with_errors",
        "failed": "failed",
        "running": "running",
    }[status]
    reason = {
        "completed": "all_test_items_completed",
        "completed_with_errors": "all_test_items_completed",
        "failed": "user_cancelled",
        "running": None,
    }[status]
    return {
        "task_definition": {
            "task_id": "task",
            "name": "Reporting test",
            "target": {
                "name": "Example app",
                "description": "Produces sample output.",
                "endpoint": "https://private.example/v1",
                "adapter_type": "mock",
                "api_key_ref": "env:TEST_REPORT_KEY",
            },
            "test_items": [{
                "item_id": "baseline",
                "kind": "baseline",
                "dataset": DATASET,
                "evaluation_rule_refs": [RULE],
            }],
        },
        "task_context": {
            "task_id": "task",
            "status": status,
            "test_item_progress": [{
                "test_item_id": "baseline",
                "status": progress_status,
                "total_cases": len(cases),
                "completed_cases": completed,
                "error_cases": errors,
            }],
            "created_at": NOW,
            "started_at": NOW,
            "updated_at": NOW + timedelta(minutes=1),
            "finished_at": NOW + timedelta(minutes=1) if reason else None,
            "termination_reason": reason,
        },
        "test_cases": cases,
    }


def test_retry_and_rescore_keep_history_without_double_counting():
    case = _case("a")
    run = _run([case])
    execution, evidence = _execution(case, retry=True)
    initial, initial_ref = _evaluation(case, "initial", "failed")
    latest, latest_ref = _evaluation(case, "latest", "passed", supersedes="initial")
    run.update(execution_results=[execution], evaluation_results=[latest, initial],
               evidence_references=[*evidence, initial_ref, latest_ref])
    records = TaskRunRecords.model_validate(run)
    before = records.model_dump()

    report = project_run(records)
    counts = report.counts
    step = report.items[0].cases[0].steps[0]
    assert (counts.target_calls, counts.target_attempts, counts.failed_target_attempts) == (1, 2, 1)
    assert (counts.passed_steps, counts.failed_steps, counts.error_cases) == (1, 0, 0)
    assert step.execution.selected_attempt_id == "a-selected"
    assert [evaluation.evaluation_id for evaluation in step.evaluations] == ["initial", "latest"]
    assert step.effective_evaluation.evaluation_id == "latest"
    assert {ref.evidence_id for ref in step.evidence} == {
        "a-selected-target_request", "a-selected-target_response",
        "initial-evaluation_judgment", "latest-evaluation_judgment",
    }
    assert report.items[0].cases[0].attack_succeeded is None
    assert report == project_run(records)
    assert records.model_dump() == before
    assert "TEST_REPORT_KEY" not in report.model_dump_json()
    assert "private.example" not in report.model_dump_json()


def test_interrupted_run_preserves_unscored_calls_and_skipped_cases():
    first, second, last = (_case(case_id) for case_id in ("a", "b", "c"))
    run = _run([last, second, first], status="failed")
    first_call, first_evidence = _execution(first)
    evaluation, judgment = _evaluation(first, "first-evaluation", "passed")
    second_call, second_evidence = _execution(second)
    run.update(execution_results=[second_call, first_call],
               evaluation_results=[evaluation],
               evidence_references=[*second_evidence, judgment, *first_evidence])
    run["task_context"].update(current_test_item_id="baseline", current_case_id="b")

    report = project_run(TaskRunRecords.model_validate(run))
    assert report.termination_reason == "user_cancelled"
    assert [case.case_id for case in report.items[0].cases] == ["a", "b", "c"]
    assert [case.skipped for case in report.items[0].cases] == [False, False, True]
    assert report.counts.completed_cases == 1
    assert report.counts.skipped_cases == 1
    assert report.counts.unevaluated_successful_calls == 1
    assert report.counts.evaluation_error_steps == 0


def test_technical_errors_remain_separate_from_model_verdicts():
    first, second = (_case(case_id) for case_id in ("a", "b"))
    run = _run([first, second], status="completed_with_errors", completed=2, errors=2)
    first_call, _ = _execution(first, success=False)
    second_call, evidence = _execution(second)
    run.update(
        execution_results=[first_call, second_call],
        evaluation_results=[{
            **_lineage(second),
            "evaluation_id": "judge-error",
            "execution_attempt_ids": ["b-selected"],
            "evaluation_rule_refs": [RULE],
            "status": "error",
            "reason": "Judge unavailable.",
            "errors": [{"error_type": "judge_model_error", "message": "Judge timed out."}],
            "evaluated_at": NOW + timedelta(seconds=2),
        }],
        evidence_references=evidence,
    )
    counts = project_run(TaskRunRecords.model_validate(run)).counts
    assert (counts.failed_target_calls, counts.evaluation_error_steps, counts.error_cases) == (1, 1, 2)
    assert (counts.failed_steps, counts.skipped_cases, counts.successful_risk_cases) == (0, 0, 0)


def test_risk_item_counts_a_stored_failed_verdict_per_case():
    case = _case("risk-a", "risk")
    run = _run([case])
    run["task_definition"]["test_items"] = [{
        "item_id": "risk",
        "kind": "risk_attack",
        "risk_id": "format",
        "strategy_refs": ["fixture"],
        "sources": {"datasets": [{"dataset": DATASET, "count": 1}]},
        "max_rounds": 2,
        "evaluation_rule_refs": [RULE],
    }]
    run["task_context"]["test_item_progress"][0]["test_item_id"] = "risk"
    call, evidence = _execution(case)
    evaluation, judgment = _evaluation(case, "failed-evaluation", "failed")
    run.update(
        step_contexts=[{
            **_lineage(case),
            "max_rounds": 2,
            "target_profile": {"name": "Example app", "description": "Fixture."},
            "risk_objective": {"risk_id": "format", "name": "Format",
                               "description": "Fixture.", "objective": "Observe the output."},
            "available_strategies": [{"strategy_id": "fixture", "name": "Fixture",
                                      "description": "Stored test data.", "guidance": "Fixture."}],
        }],
        execution_results=[call],
        evaluation_results=[evaluation],
        evidence_references=[*evidence, judgment],
    )

    report = project_run(TaskRunRecords.model_validate(run))
    assert report.items[0].kind == "risk_attack"
    assert report.items[0].cases[0].attack_succeeded is True
    assert (report.counts.successful_risk_cases, report.counts.failed_steps) == (1, 1)
