"""Normalized inputs for evaluation orchestration and individual scorers."""

from typing import Self

from pydantic import Field, PositiveInt, model_validator

from redteam.core.models.common import DomainModel, NonEmptyStr
from redteam.core.models.execution import ExecutionResult, ExecutionStatus
from redteam.core.models.interaction import (
    ConversationMessage,
    MessageRole,
    validate_conversation,
)
from redteam.core.models.resources import ResolvedEvaluationRule
from redteam.core.models.task import ModelConfig


class EvaluationRequest(DomainModel):
    """All normalized material required to evaluate one successful execution."""

    evaluation_id: NonEmptyStr
    task_id: NonEmptyStr
    test_item_id: NonEmptyStr
    case_id: NonEmptyStr
    step_id: NonEmptyStr
    round_index: PositiveInt

    execution_result: ExecutionResult
    conversation: tuple[ConversationMessage, ...] = Field(min_length=2)
    evaluation_rules: tuple[ResolvedEvaluationRule, ...] = Field(min_length=1)
    input_evidence_refs: tuple[NonEmptyStr, ...] = Field(min_length=1)
    judge_model: ModelConfig | None = None
    supersedes_evaluation_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_evaluation_input(self) -> Self:
        execution = self.execution_result
        request_lineage = (
            self.task_id,
            self.test_item_id,
            self.case_id,
            self.step_id,
            self.round_index,
        )
        execution_lineage = (
            execution.task_id,
            execution.test_item_id,
            execution.case_id,
            execution.step_id,
            execution.round_index,
        )
        if request_lineage != execution_lineage:
            raise ValueError("evaluation lineage must match execution_result")
        if execution.status is not ExecutionStatus.SUCCESS:
            raise ValueError("only a successful execution can be evaluated")

        validate_conversation(self.conversation, final_role=MessageRole.ASSISTANT)
        if self.conversation[-1].content != execution.final_response_text:
            raise ValueError(
                "the final assistant message must match the selected target response"
            )

        if len(self.input_evidence_refs) != len(set(self.input_evidence_refs)):
            raise ValueError("input evidence references must be unique")
        selected_attempt = next(
            attempt
            for attempt in execution.attempts
            if attempt.attempt_id == execution.selected_attempt_id
        )
        if not set(self.input_evidence_refs).issubset(
            set(selected_attempt.evidence_refs)
        ):
            raise ValueError(
                "input evidence must come from the selected execution attempt"
            )

        rule_keys = [
            (rule.rule_ref.rule_id, rule.rule_ref.version)
            for rule in self.evaluation_rules
        ]
        if len(rule_keys) != len(set(rule_keys)):
            raise ValueError("evaluation rules must be unique")
        if (
            any(rule.requires_judge_model for rule in self.evaluation_rules)
            and self.judge_model is None
        ):
            raise ValueError("judge_model is required by an evaluation rule")
        if self.supersedes_evaluation_id == self.evaluation_id:
            raise ValueError("an evaluation cannot supersede itself")
        return self


class ScoringRequest(DomainModel):
    """The input supplied to one scorer for one resolved evaluation rule."""

    evaluation_id: NonEmptyStr
    task_id: NonEmptyStr
    test_item_id: NonEmptyStr
    case_id: NonEmptyStr
    step_id: NonEmptyStr
    round_index: PositiveInt

    rule: ResolvedEvaluationRule
    conversation: tuple[ConversationMessage, ...] = Field(min_length=2)
    input_evidence_refs: tuple[NonEmptyStr, ...] = Field(min_length=1)
    judge_model: ModelConfig | None = None

    @model_validator(mode="after")
    def validate_scorer_input(self) -> Self:
        validate_conversation(self.conversation, final_role=MessageRole.ASSISTANT)
        if len(self.input_evidence_refs) != len(set(self.input_evidence_refs)):
            raise ValueError("input evidence references must be unique")
        if self.rule.requires_judge_model and self.judge_model is None:
            raise ValueError("judge_model is required by the evaluation rule")
        return self
