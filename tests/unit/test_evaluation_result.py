"""EvaluationResult, scorer result, and evaluation error constraints."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from redteam.core.models import (
    EvaluationAggregationMethod,
    EvaluationError,
    EvaluationResult,
    EvaluationStatus,
    EvaluationVerdict,
    ScorerMethodOrigin,
)


NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def _rule(rule_id: str = "privacy-leakage", version: str = "1.0") -> dict[str, str]:
    return {"rule_id": rule_id, "version": version}


def _scorer_result(
    *,
    rule_id: str = "privacy-leakage",
    version: str = "1.0",
    scorer_id: str = "llm-judge",
    verdict: str = "failed",
    risk_score: float | None = 0.9,
    method_origin: str = "primary",
) -> dict[str, object]:
    return {
        "rule_ref": _rule(rule_id, version),
        "scorer_id": scorer_id,
        "scorer_version": "2.1",
        "method_origin": method_origin,
        "verdict": verdict,
        "risk_score": risk_score,
        "reason": "The response disclosed protected order information.",
        "evidence_refs": [f"evidence-{scorer_id}"],
    }


def _completed_result() -> dict[str, object]:
    return {
        "evaluation_id": "evaluation-001",
        "task_id": "task-001",
        "test_item_id": "privacy-test",
        "case_id": "case-007",
        "step_id": "step-003",
        "round_index": 3,
        "execution_attempt_ids": [
            "round-001-selected-attempt",
            "round-003-selected-attempt",
        ],
        "input_evidence_refs": [
            "evidence-round-001-response",
            "evidence-round-003-response",
        ],
        "evaluation_rule_refs": [_rule()],
        "status": "completed",
        "verdict": "failed",
        "risk_score": 0.9,
        "reason": "The target failed the privacy test.",
        "scorer_results": [_scorer_result()],
        "evidence_refs": ["evidence-overall-judgment"],
        "evaluated_at": NOW,
    }


def _error_result() -> dict[str, object]:
    return {
        "evaluation_id": "evaluation-error-001",
        "task_id": "task-001",
        "test_item_id": "privacy-test",
        "case_id": "case-007",
        "step_id": "step-003",
        "round_index": 3,
        "execution_attempt_ids": ["round-003-selected-attempt"],
        "evaluation_rule_refs": [_rule()],
        "status": "error",
        "reason": "The judge model call failed before a verdict was formed.",
        "errors": [
            {
                "error_type": "judge_model_error",
                "message": "The judge model request timed out.",
                "rule_ref": _rule(),
                "scorer_id": "llm-judge",
                "scorer_version": "2.1",
            }
        ],
        "evaluated_at": NOW,
    }


def test_completed_evaluation_records_inputs_rules_and_scorers() -> None:
    result = EvaluationResult.model_validate(_completed_result())

    assert result.status is EvaluationStatus.COMPLETED
    assert result.verdict is EvaluationVerdict.FAILED
    assert result.risk_score == 0.9
    assert result.scorer_results[0].method_origin is ScorerMethodOrigin.PRIMARY
    assert result.scorer_results[0].rule_ref.version == "1.0"
    assert result.execution_attempt_ids[-1] == "round-003-selected-attempt"
    assert (
        result.aggregation_method
        is EvaluationAggregationMethod.ANY_FAILURE_V1
    )


def test_completed_inconclusive_evaluation_has_no_risk_score() -> None:
    data = _completed_result()
    data["verdict"] = "inconclusive"
    data["risk_score"] = None
    data["scorer_results"] = [
        _scorer_result(verdict="inconclusive", risk_score=None)
    ]

    result = EvaluationResult.model_validate(data)

    assert result.verdict is EvaluationVerdict.INCONCLUSIVE
    assert result.risk_score is None


def test_any_failure_v1_aggregates_verdict_and_maximum_risk_score() -> None:
    data = _completed_result()
    data["evaluation_rule_refs"] = [_rule(), _rule("policy-compliance")]
    data["scorer_results"] = [
        _scorer_result(verdict="passed", risk_score=0.1),
        _scorer_result(
            rule_id="policy-compliance",
            scorer_id="policy-scorer",
            verdict="failed",
            risk_score=0.8,
        ),
    ]
    data["risk_score"] = 0.8

    result = EvaluationResult.model_validate(data)
    assert result.verdict is EvaluationVerdict.FAILED
    assert result.risk_score == 0.8

    data["verdict"] = "passed"
    with pytest.raises(ValidationError, match="overall verdict"):
        EvaluationResult.model_validate(data)


def test_overall_score_must_match_aggregated_scorer_scores() -> None:
    data = _completed_result()
    data["risk_score"] = 0.2

    with pytest.raises(ValidationError, match="maximum scorer risk_score"):
        EvaluationResult.model_validate(data)


def test_inconclusive_results_reject_numeric_risk_scores() -> None:
    scorer = _scorer_result(verdict="inconclusive", risk_score=0.5)
    data = _completed_result()
    data["verdict"] = "inconclusive"
    data["risk_score"] = 0.5
    data["scorer_results"] = [scorer]

    with pytest.raises(ValidationError, match="inconclusive scorer result"):
        EvaluationResult.model_validate(data)


def test_completed_evaluation_requires_verdict_and_scorer_result() -> None:
    data = _completed_result()
    data["verdict"] = None
    with pytest.raises(ValidationError, match="requires a verdict"):
        EvaluationResult.model_validate(data)

    data = _completed_result()
    data["scorer_results"] = []
    with pytest.raises(ValidationError, match="at least one scorer result"):
        EvaluationResult.model_validate(data)


def test_completed_evaluation_requires_input_and_judgment_evidence() -> None:
    data = _completed_result()
    data["input_evidence_refs"] = []
    with pytest.raises(ValidationError, match="input evidence references"):
        EvaluationResult.model_validate(data)

    data = _completed_result()
    data["evidence_refs"] = []
    scorer = _scorer_result()
    scorer["evidence_refs"] = []
    data["scorer_results"] = [scorer]
    with pytest.raises(ValidationError, match="judgment evidence"):
        EvaluationResult.model_validate(data)


def test_error_evaluation_has_errors_but_no_verdict_or_score() -> None:
    result = EvaluationResult.model_validate(_error_result())

    assert result.status is EvaluationStatus.ERROR
    assert result.verdict is None
    assert result.risk_score is None
    assert result.errors[0].scorer_id == "llm-judge"


def test_error_evaluation_rejects_verdict_score_or_missing_errors() -> None:
    data = _error_result()
    data["verdict"] = "failed"
    with pytest.raises(ValidationError, match="cannot have a verdict"):
        EvaluationResult.model_validate(data)

    data = _error_result()
    data["risk_score"] = 0.8
    with pytest.raises(ValidationError, match="cannot have risk_score"):
        EvaluationResult.model_validate(data)

    data = _error_result()
    data["errors"] = []
    with pytest.raises(ValidationError, match="at least one error"):
        EvaluationResult.model_validate(data)


def test_fallback_can_complete_after_a_primary_method_error() -> None:
    data = _completed_result()
    data["scorer_results"] = [_scorer_result(method_origin="fallback")]
    data["errors"] = [
        {
            "error_type": "judge_model_error",
            "message": "The primary judge model was unavailable.",
            "rule_ref": _rule(),
            "scorer_id": "primary-llm-judge",
            "scorer_version": "1.4",
        }
    ]

    result = EvaluationResult.model_validate(data)

    assert result.status is EvaluationStatus.COMPLETED
    assert result.scorer_results[0].method_origin is ScorerMethodOrigin.FALLBACK
    assert len(result.errors) == 1


def test_scorer_and_error_rules_must_be_declared_by_the_evaluation() -> None:
    data = _completed_result()
    data["scorer_results"] = [_scorer_result(rule_id="undeclared")]
    with pytest.raises(ValidationError, match="scorer result rules"):
        EvaluationResult.model_validate(data)

    data = _error_result()
    data["errors"][0]["rule_ref"] = _rule("undeclared")  # type: ignore[index]
    with pytest.raises(ValidationError, match="evaluation error rules"):
        EvaluationResult.model_validate(data)


def test_execution_attempts_rules_and_scorers_must_be_unique() -> None:
    data = _completed_result()
    data["execution_attempt_ids"] = ["attempt-001", "attempt-001"]
    with pytest.raises(ValidationError, match="execution attempt IDs must be unique"):
        EvaluationResult.model_validate(data)

    data = _completed_result()
    data["evaluation_rule_refs"] = [_rule(), _rule()]
    with pytest.raises(ValidationError, match="evaluation rule references must be unique"):
        EvaluationResult.model_validate(data)

    data = _completed_result()
    data["scorer_results"] = [_scorer_result(), _scorer_result()]
    with pytest.raises(ValidationError, match="scorer results must be unique"):
        EvaluationResult.model_validate(data)


def test_risk_scores_are_normalized() -> None:
    data = _completed_result()
    data["risk_score"] = 1.1
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        EvaluationResult.model_validate(data)

    data = _completed_result()
    data["scorer_results"] = [_scorer_result(risk_score=-0.1)]
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        EvaluationResult.model_validate(data)


def test_evaluation_time_must_be_utc_and_reevaluation_cannot_replace_itself() -> None:
    data = _completed_result()
    data["evaluated_at"] = datetime(2026, 11, 22, 12, 0)
    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        EvaluationResult.model_validate(data)

    data = _completed_result()
    data["supersedes_evaluation_id"] = data["evaluation_id"]
    with pytest.raises(ValidationError, match="cannot supersede itself"):
        EvaluationResult.model_validate(data)


def test_error_scorer_identity_must_include_id_and_version() -> None:
    with pytest.raises(ValidationError, match="must be provided together"):
        EvaluationError.model_validate(
            {
                "error_type": "scorer_error",
                "message": "The scorer failed.",
                "scorer_id": "regex-scorer",
            }
        )


def test_models_reject_fields_outside_the_v1_contract() -> None:
    data = _completed_result()
    data["item_id"] = "old-name"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvaluationResult.model_validate(data)


def test_passed_evaluation_rejects_a_missing_rule_result():
    record = _completed_result()
    record.update(
        evaluation_rule_refs=[_rule(), _rule("second-rule")],
        verdict="passed",
        risk_score=0.0,
        scorer_results=[_scorer_result(verdict="passed", risk_score=0.0)],
    )
    with pytest.raises(ValidationError, match="a result for every rule"):
        EvaluationResult.model_validate(record)
