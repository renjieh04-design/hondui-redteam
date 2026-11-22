"""任务定义模型：被配置模块与编排模块共用的公共领域模型。"""

from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

from redteam.core.models.common import DomainModel, NonEmptyStr
from redteam.core.models.retry import RetryPolicy


class ModelConfig(DomainModel):
    """攻击者模型或裁判模型的连接配置。"""

    adapter_type: NonEmptyStr = Field(description="Model adapter identifier.")
    endpoint: NonEmptyStr = Field(description="Model API endpoint.")
    model: NonEmptyStr = Field(description="Provider-specific model identifier.")
    # 只保存凭据引用（如 env:ATTACKER_API_KEY），不保存密钥明文
    api_key_ref: NonEmptyStr | None = Field(
        default=None,
        description="Reference to a credential; never the secret value itself.",
    )


class TargetConfig(DomainModel):
    """被测应用的连接信息与业务上下文。"""

    name: NonEmptyStr = Field(description="Application name.")
    # 描述应用用途、正常能力与权限边界，攻击者据此理解目标
    description: NonEmptyStr = Field(
        description="Application purpose, normal capabilities, and permission boundaries."
    )
    adapter_type: NonEmptyStr = Field(description="Target adapter identifier.")
    endpoint: NonEmptyStr = Field(description="Target application endpoint.")
    model: NonEmptyStr | None = Field(
        default=None,
        description="Target model identifier when required by the target API.",
    )
    # 只保存凭据引用，不保存密钥明文
    api_key_ref: NonEmptyStr | None = Field(
        default=None,
        description="Reference to a target credential; never the secret value itself.",
    )


class DatasetReference(DomainModel):
    """指向某个已导入数据集的确定版本（dataset_id + version）。"""

    dataset_id: NonEmptyStr
    version: NonEmptyStr


class EvaluationRuleReference(DomainModel):
    """An exact, reproducible version of an evaluation rule."""

    rule_id: NonEmptyStr
    version: NonEmptyStr

    @field_validator("version")
    @classmethod
    def require_resolved_version(cls, value: str) -> str:
        if value.casefold() == "latest" or value == "*":
            raise ValueError("evaluation rule version must be resolved")
        return value


def _require_unique_evaluation_rule_refs(
    refs: tuple[EvaluationRuleReference, ...],
) -> None:
    keys = [(ref.rule_id, ref.version) for ref in refs]
    if len(keys) != len(set(keys)):
        raise ValueError("evaluation rule references must be unique")


class DatasetSampleConfig(DomainModel):
    """从某个已导入数据集中随机抽取 count 条用例。"""

    dataset: DatasetReference
    count: PositiveInt


class GenerationConfig(DomainModel):
    """用任务级攻击者模型生成 count 条初始用例。"""

    count: PositiveInt


class CaseSources(DomainModel):
    """风险攻击测试的初始用例来源：数据集抽样与模型生成可同时使用。"""

    datasets: tuple[DatasetSampleConfig, ...] = ()
    generated: GenerationConfig | None = None

    @model_validator(mode="after")
    def require_at_least_one_source(self) -> Self:
        # 两种来源都为空时无从开始攻击，直接拒绝
        if not self.datasets and self.generated is None:
            raise ValueError("at least one dataset or generated source is required")
        return self


class BaselineTestSpec(DomainModel):
    """基线测试项：按数据集与评估规则执行标准题目，不发起攻击。"""

    item_id: NonEmptyStr
    kind: Literal["baseline"] = "baseline"
    dataset: DatasetReference
    # 为 None 表示使用数据集内的全部用例
    case_ids: tuple[NonEmptyStr, ...] | None = Field(
        default=None,
        min_length=1,
        description="Selected case IDs; null means all cases in the dataset.",
    )
    evaluation_rule_refs: tuple[EvaluationRuleReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_baseline_relationships(self) -> Self:
        if self.case_ids is not None and len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("baseline case IDs must be unique")
        _require_unique_evaluation_rule_refs(self.evaluation_rule_refs)
        return self


class RiskTestSpec(DomainModel):
    """风险攻击测试项：针对某一风险类别，由攻击者模型多轮尝试突破目标。"""

    item_id: NonEmptyStr
    kind: Literal["risk_attack"] = "risk_attack"
    risk_id: NonEmptyStr
    objective: NonEmptyStr | None = None
    sources: CaseSources
    # 策略池是可选集合，不要求逐一执行每种策略或策略组合
    strategy_refs: tuple[NonEmptyStr, ...] = Field(
        min_length=1,
        description="Strategies available to the attacker as a choice pool.",
    )
    max_rounds: PositiveInt = 1
    evaluation_rule_refs: tuple[EvaluationRuleReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_risk_relationships(self) -> Self:
        strategy_ids = [strategy_id for strategy_id in self.strategy_refs]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ValueError("risk attack strategy references must be unique")
        _require_unique_evaluation_rule_refs(self.evaluation_rule_refs)
        return self


# 判别式联合：按 kind 字段自动路由到 BaselineTestSpec 或 RiskTestSpec
TestItem = Annotated[
    BaselineTestSpec | RiskTestSpec,
    Field(discriminator="kind"),
]


class TaskDefinition(DomainModel):
    """一次完整测试运行的不可变定义，只含输入，不含运行状态与结果。"""

    task_id: NonEmptyStr
    name: NonEmptyStr
    target: TargetConfig
    attacker_model: ModelConfig | None = None
    judge_model: ModelConfig | None = None
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    test_items: tuple[TestItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_task_relationships(self) -> Self:
        # 测试项 ID 必须唯一，否则报告与结果无法对应
        item_ids = [item.item_id for item in self.test_items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("test item IDs must be unique within a task")

        # 用例需要由模型生成时，必须提供攻击者模型
        uses_generation = any(
            isinstance(item, RiskTestSpec) and item.sources.generated is not None
            for item in self.test_items
        )
        if uses_generation and self.attacker_model is None:
            raise ValueError("attacker_model is required when cases are model-generated")

        return self

