"""Attacker-facing context for one risk-attack step."""

from typing import Self

from pydantic import Field, PositiveInt, model_validator

from redteam.core.models.common import (
    DomainModel,
    NonEmptyStr,
    NormalizedRiskScore,
)

# Backward-compatible name for callers that imported the original step type.
NormalizedScore = NormalizedRiskScore


class TargetProfile(DomainModel):
    """Public target information that is safe to expose to the attacker."""

    name: NonEmptyStr
    description: NonEmptyStr


class RiskObjective(DomainModel):
    """Resolved risk information and the concrete objective for this attack."""

    risk_id: NonEmptyStr
    name: NonEmptyStr
    description: NonEmptyStr
    objective: NonEmptyStr


class AvailableStrategy(DomainModel):
    """A resolved attack strategy that may be selected for the current step."""

    strategy_id: NonEmptyStr
    name: NonEmptyStr
    description: NonEmptyStr
    guidance: NonEmptyStr


class EvaluationFeedback(DomainModel):
    """The evaluator output that is safe for the attacker to consume."""

    attack_succeeded: bool | None
    score: NormalizedScore | None = Field(
        default=None,
        description="Normalized risk from 0 (no detected risk) to 1 (highest risk).",
    )
    reason: NonEmptyStr


class StepHistoryEntry(DomainModel):
    """One fully executed and evaluated prior round in the current case."""

    step_id: NonEmptyStr
    round_index: PositiveInt
    strategy_id: NonEmptyStr
    attack_prompt: NonEmptyStr
    target_response: NonEmptyStr
    evaluation_feedback: EvaluationFeedback


class StepContext(DomainModel):
    """Immutable input supplied to the attacker for one risk-attack round."""

    step_id: NonEmptyStr
    task_id: NonEmptyStr
    test_item_id: NonEmptyStr
    case_id: NonEmptyStr

    round_index: PositiveInt
    max_rounds: PositiveInt

    target_profile: TargetProfile
    risk_objective: RiskObjective
    available_strategies: tuple[AvailableStrategy, ...] = Field(min_length=1)
    history: tuple[StepHistoryEntry, ...] = ()

    @model_validator(mode="after")
    def validate_step_relationships(self) -> Self:
        if self.round_index > self.max_rounds:
            raise ValueError("round_index cannot exceed max_rounds")

        strategy_ids = [
            strategy.strategy_id for strategy in self.available_strategies
        ]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("available strategy IDs must be unique")

        expected_history_length = self.round_index - 1
        if len(self.history) != expected_history_length:
            raise ValueError(
                "history must contain exactly the completed rounds before round_index"
            )

        history_rounds = [entry.round_index for entry in self.history]
        expected_rounds = list(range(1, self.round_index))
        if history_rounds != expected_rounds:
            raise ValueError("history rounds must be ordered and contiguous from 1")

        history_step_ids = [entry.step_id for entry in self.history]
        if len(history_step_ids) != len(set(history_step_ids)):
            raise ValueError("history step IDs must be unique")
        if self.step_id in history_step_ids:
            raise ValueError("current step_id cannot already appear in history")

        allowed_strategy_ids = set(strategy_ids)
        if any(
            entry.strategy_id not in allowed_strategy_ids for entry in self.history
        ):
            raise ValueError(
                "history strategy IDs must refer to available_strategies"
            )

        if any(
            entry.evaluation_feedback.attack_succeeded is True
            for entry in self.history
        ):
            raise ValueError("a successful attack must terminate the test case")

        return self
