"""Normalized resources prepared before TaskRunner executes a test item."""

from collections import Counter
from typing import Self

from pydantic import Field, PositiveInt, model_validator

from redteam.core.models.case import DatasetCaseSource, TestCase
from redteam.core.models.common import DomainModel, NonEmptyStr
from redteam.core.models.step import AvailableStrategy, RiskObjective, TargetProfile
from redteam.core.models.task import (
    BaselineTestSpec,
    DatasetReference,
    EvaluationRuleReference,
    RiskTestSpec,
    TestItem,
)


class DatasetEntry(DomainModel):
    """One provider-neutral entry loaded from an exact dataset version."""

    dataset: DatasetReference
    source_case_id: NonEmptyStr
    prompt: NonEmptyStr


class EvaluationRuleParameter(DomainModel):
    """One immutable scalar parameter supplied to a resolved scorer."""

    name: NonEmptyStr
    value: str | int | float | bool | None


class ResolvedEvaluationRule(DomainModel):
    """An exact evaluation rule resolved to one concrete scorer version."""

    rule_ref: EvaluationRuleReference
    name: NonEmptyStr
    description: NonEmptyStr
    scorer_id: NonEmptyStr
    scorer_version: NonEmptyStr
    requires_judge_model: bool = False
    parameters: tuple[EvaluationRuleParameter, ...] = ()

    @model_validator(mode="after")
    def require_unique_parameter_names(self) -> Self:
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("evaluation rule parameter names must be unique")
        return self


class CaseGenerationRequest(DomainModel):
    """The resolved input for generating initial risk-attack cases."""

    task_id: NonEmptyStr
    test_item_id: NonEmptyStr
    count: PositiveInt
    target_profile: TargetProfile
    risk_objective: RiskObjective
    available_strategies: tuple[AvailableStrategy, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_strategies(self) -> Self:
        strategy_ids = [item.strategy_id for item in self.available_strategies]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("available strategy IDs must be unique")
        return self


class GeneratedCaseDraft(DomainModel):
    """One generated prompt before the resource layer assigns case lineage."""

    initial_prompt: NonEmptyStr


class PreparedTestItem(DomainModel):
    """A test item after all raw resources have been resolved and validated."""

    task_id: NonEmptyStr
    test_item: TestItem
    cases: tuple[TestCase, ...] = Field(min_length=1)
    evaluation_rules: tuple[ResolvedEvaluationRule, ...] = Field(min_length=1)
    risk_objective: RiskObjective | None = None
    available_strategies: tuple[AvailableStrategy, ...] = ()

    @model_validator(mode="after")
    def validate_prepared_resources(self) -> Self:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("prepared case IDs must be unique")
        if any(case.task_id != self.task_id for case in self.cases):
            raise ValueError("all prepared cases must belong to task_id")
        if any(
            case.test_item_id != self.test_item.item_id for case in self.cases
        ):
            raise ValueError("all prepared cases must belong to the test item")

        expected_rule_keys = {
            (ref.rule_id, ref.version)
            for ref in self.test_item.evaluation_rule_refs
        }
        actual_rule_keys = {
            (rule.rule_ref.rule_id, rule.rule_ref.version)
            for rule in self.evaluation_rules
        }
        if len(actual_rule_keys) != len(self.evaluation_rules):
            raise ValueError("resolved evaluation rules must be unique")
        if actual_rule_keys != expected_rule_keys:
            raise ValueError(
                "resolved evaluation rules must exactly match the test item"
            )

        if isinstance(self.test_item, BaselineTestSpec):
            if self.risk_objective is not None or self.available_strategies:
                raise ValueError(
                    "a baseline test item cannot contain risk attack resources"
                )
            baseline_source_keys: list[tuple[str, str, str]] = []
            for case in self.cases:
                if not isinstance(case.source, DatasetCaseSource):
                    raise ValueError("baseline cases must come from datasets")
                if (
                    case.source.dataset.dataset_id
                    != self.test_item.dataset.dataset_id
                    or case.source.dataset.version
                    != self.test_item.dataset.version
                ):
                    raise ValueError(
                        "baseline cases must come from the test item dataset"
                    )
                baseline_source_keys.append(
                    (
                        case.source.dataset.dataset_id,
                        case.source.dataset.version,
                        case.source.source_case_id,
                    )
                )
            if len(baseline_source_keys) != len(set(baseline_source_keys)):
                raise ValueError("baseline source case IDs must be unique")
            if self.test_item.case_ids is not None:
                prepared_case_ids = Counter(
                    case.source.source_case_id
                    for case in self.cases
                )
                selected_case_ids = Counter(self.test_item.case_ids)
                if prepared_case_ids != selected_case_ids:
                    raise ValueError(
                        "prepared baseline cases must exactly match the selected case_ids"
                    )
            return self

        if not isinstance(self.test_item, RiskTestSpec):
            raise ValueError("unsupported test item type")
        if self.risk_objective is None:
            raise ValueError("a risk test item requires a resolved risk objective")
        if self.risk_objective.risk_id != self.test_item.risk_id:
            raise ValueError("risk objective must match the risk test item")
        if (
            self.test_item.objective is not None
            and self.risk_objective.objective != self.test_item.objective
        ):
            raise ValueError(
                "resolved risk objective must match the test item objective override"
            )

        actual_dataset_counts: Counter[tuple[str, str]] = Counter()
        actual_generated_count = 0
        risk_source_keys: list[tuple[str, str, str]] = []
        for case in self.cases:
            if isinstance(case.source, DatasetCaseSource):
                source_keys = {
                    (
                        sample.dataset.dataset_id,
                        sample.dataset.version,
                    )
                    for sample in self.test_item.sources.datasets
                }
                if (
                    case.source.dataset.dataset_id,
                    case.source.dataset.version,
                ) not in source_keys:
                    raise ValueError(
                        "prepared risk cases must come from declared datasets"
                    )
                risk_source_keys.append(
                    (
                        case.source.dataset.dataset_id,
                        case.source.dataset.version,
                        case.source.source_case_id,
                    )
                )
                actual_dataset_counts[
                    (
                        case.source.dataset.dataset_id,
                        case.source.dataset.version,
                    )
                ] += 1
            elif getattr(case.source, "kind", None) == "generated":
                if self.test_item.sources.generated is None:
                    raise ValueError(
                        "prepared risk cases cannot be generated when generation is disabled"
                    )
                actual_generated_count += 1

        if len(risk_source_keys) != len(set(risk_source_keys)):
            raise ValueError("risk dataset source case IDs must be unique")

        expected_dataset_counts: Counter[tuple[str, str]] = Counter()
        for sample in self.test_item.sources.datasets:
            expected_dataset_counts[
                (sample.dataset.dataset_id, sample.dataset.version)
            ] += sample.count
        if actual_dataset_counts != expected_dataset_counts:
            raise ValueError(
                "prepared risk dataset case counts must match the test item sources"
            )

        expected_generated_count = (
            self.test_item.sources.generated.count
            if self.test_item.sources.generated is not None
            else 0
        )
        if actual_generated_count != expected_generated_count:
            raise ValueError(
                "prepared generated case count must match the test item source"
            )

        strategy_ids = [item.strategy_id for item in self.available_strategies]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("resolved attack strategies must be unique")
        if set(strategy_ids) != set(self.test_item.strategy_refs):
            raise ValueError(
                "resolved attack strategies must exactly match the test item"
            )
        return self
