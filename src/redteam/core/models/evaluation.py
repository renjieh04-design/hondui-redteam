"""Results of evaluating one completed target-model execution step."""

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    Field,
    PositiveInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from redteam.core.models.common import (
    DomainModel,
    ErrorMessage,
    NonEmptyStr,
    NormalizedRiskScore,
)
from redteam.core.models.task import (
    EvaluationRuleReference,
)


EvaluationReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]
# Keep the domain-specific public name while sharing one validation primitive.
EvaluationErrorMessage = ErrorMessage


class EvaluationStatus(StrEnum):
    """Whether the evaluation process itself completed normally."""

    COMPLETED = "completed"
    ERROR = "error"


class EvaluationVerdict(StrEnum):
    """Target-centric outcome of applying an evaluation rule."""

    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class EvaluationAggregationMethod(StrEnum):
    """The deterministic V1 rule used to aggregate scorer results."""

    ANY_FAILURE_V1 = "any_failure_v1"


class ScorerMethodOrigin(StrEnum):
    """Whether a scorer result came from the primary or fallback method."""

    PRIMARY = "primary"
    FALLBACK = "fallback"


class EvaluationErrorType(StrEnum):
    """Provider-independent categories for evaluation-side failures."""

    INPUT_UNAVAILABLE = "input_unavailable"
    RULE_RESOLUTION_ERROR = "rule_resolution_error"
    SCORER_ERROR = "scorer_error"
    JUDGE_MODEL_ERROR = "judge_model_error"
    INVALID_SCORER_OUTPUT = "invalid_scorer_output"
    EVIDENCE_PERSISTENCE_ERROR = "evidence_persistence_error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class ScorerResult(DomainModel):
    """One completed rule result produced by one concrete scorer version."""

    rule_ref: EvaluationRuleReference
    scorer_id: NonEmptyStr
    scorer_version: NonEmptyStr
    method_origin: ScorerMethodOrigin
    verdict: EvaluationVerdict
    risk_score: NormalizedRiskScore | None = Field(
        default=None,
        description="Normalized risk from 0 (no detected risk) to 1 (highest risk).",
    )
    reason: EvaluationReason
    evidence_refs: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_scorer_result(self) -> Self:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("scorer evidence references must be unique")
        if (
            self.verdict is EvaluationVerdict.INCONCLUSIVE
            and self.risk_score is not None
        ):
            raise ValueError("an inconclusive scorer result cannot have risk_score")
        return self


class EvaluationError(DomainModel):
    """A normalized, redacted evaluation-side failure."""

    error_type: EvaluationErrorType
    message: EvaluationErrorMessage
    rule_ref: EvaluationRuleReference | None = None
    scorer_id: NonEmptyStr | None = None
    scorer_version: NonEmptyStr | None = None
    evidence_refs: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_error_context(self) -> Self:
        if (self.scorer_id is None) != (self.scorer_version is None):
            raise ValueError("scorer_id and scorer_version must be provided together")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evaluation error evidence references must be unique")
        return self


class EvaluationResult(DomainModel):
    """One immutable evaluation record for a completed target execution step."""

    evaluation_id: NonEmptyStr
    task_id: NonEmptyStr
    test_item_id: NonEmptyStr
    case_id: NonEmptyStr
    step_id: NonEmptyStr
    round_index: PositiveInt

    execution_attempt_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    input_evidence_refs: tuple[NonEmptyStr, ...] = ()
    evaluation_rule_refs: tuple[EvaluationRuleReference, ...] = Field(min_length=1)

    aggregation_method: EvaluationAggregationMethod = (
        EvaluationAggregationMethod.ANY_FAILURE_V1
    )
    status: EvaluationStatus
    verdict: EvaluationVerdict | None = None
    risk_score: NormalizedRiskScore | None = Field(
        default=None,
        description="Normalized risk from 0 (no detected risk) to 1 (highest risk).",
    )
    reason: EvaluationReason

    scorer_results: tuple[ScorerResult, ...] = ()
    evidence_refs: tuple[NonEmptyStr, ...] = ()
    errors: tuple[EvaluationError, ...] = ()

    evaluated_at: datetime
    supersedes_evaluation_id: NonEmptyStr | None = None

    @field_validator("evaluated_at")
    @classmethod
    def require_utc_evaluated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("evaluated_at must be a timezone-aware UTC datetime")
        return value

    @model_validator(mode="after")
    def validate_evaluation_result(self) -> Self:
        if self.supersedes_evaluation_id == self.evaluation_id:
            raise ValueError("an evaluation cannot supersede itself")

        if len(self.execution_attempt_ids) != len(set(self.execution_attempt_ids)):
            raise ValueError("execution attempt IDs must be unique")
        if len(self.input_evidence_refs) != len(set(self.input_evidence_refs)):
            raise ValueError("input evidence references must be unique")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evaluation evidence references must be unique")

        rule_keys = [
            (rule.rule_id, rule.version) for rule in self.evaluation_rule_refs
        ]
        if len(rule_keys) != len(set(rule_keys)):
            raise ValueError("evaluation rule references must be unique")
        allowed_rule_keys = set(rule_keys)

        scorer_keys: list[tuple[str, str, str, str]] = []
        for result in self.scorer_results:
            rule_key = (result.rule_ref.rule_id, result.rule_ref.version)
            if rule_key not in allowed_rule_keys:
                raise ValueError(
                    "scorer result rules must appear in evaluation_rule_refs"
                )
            scorer_keys.append(
                (*rule_key, result.scorer_id, result.scorer_version)
            )
        if len(scorer_keys) != len(set(scorer_keys)):
            raise ValueError("scorer results must be unique within an evaluation")

        for error in self.errors:
            if error.rule_ref is None:
                continue
            error_rule_key = (error.rule_ref.rule_id, error.rule_ref.version)
            if error_rule_key not in allowed_rule_keys:
                raise ValueError(
                    "evaluation error rules must appear in evaluation_rule_refs"
                )

        if self.status is EvaluationStatus.COMPLETED:
            if self.verdict is None:
                raise ValueError("a completed evaluation requires a verdict")
            if not self.scorer_results:
                raise ValueError(
                    "a completed evaluation requires at least one scorer result"
                )
            if self.verdict is EvaluationVerdict.PASSED and {
                (result.rule_ref.rule_id, result.rule_ref.version)
                for result in self.scorer_results
            } != allowed_rule_keys:
                raise ValueError("a passed evaluation requires a result for every rule")
            if not self.input_evidence_refs:
                raise ValueError(
                    "a completed evaluation requires input evidence references"
                )
            has_judgment_evidence = bool(self.evidence_refs) or any(
                result.evidence_refs for result in self.scorer_results
            )
            if not has_judgment_evidence:
                raise ValueError(
                    "a completed evaluation requires judgment evidence"
                )

            scorer_verdicts = {
                result.verdict for result in self.scorer_results
            }
            if EvaluationVerdict.FAILED in scorer_verdicts:
                expected_verdict = EvaluationVerdict.FAILED
            elif EvaluationVerdict.INCONCLUSIVE in scorer_verdicts:
                expected_verdict = EvaluationVerdict.INCONCLUSIVE
            else:
                expected_verdict = EvaluationVerdict.PASSED
            if self.verdict is not expected_verdict:
                raise ValueError(
                    "overall verdict must match the any_failure_v1 aggregation"
                )

            if (
                self.verdict is EvaluationVerdict.INCONCLUSIVE
                and self.risk_score is not None
            ):
                raise ValueError(
                    "an inconclusive evaluation cannot have risk_score"
                )
            if self.verdict is not EvaluationVerdict.INCONCLUSIVE:
                scorer_scores = [
                    result.risk_score
                    for result in self.scorer_results
                    if result.risk_score is not None
                ]
                expected_score = max(scorer_scores, default=None)
                if self.risk_score != expected_score:
                    raise ValueError(
                        "overall risk_score must equal the maximum scorer risk_score"
                    )
        else:
            if self.verdict is not None:
                raise ValueError("an evaluation error cannot have a verdict")
            if self.risk_score is not None:
                raise ValueError("an evaluation error cannot have risk_score")
            if not self.errors:
                raise ValueError("an evaluation error requires at least one error")

        return self
