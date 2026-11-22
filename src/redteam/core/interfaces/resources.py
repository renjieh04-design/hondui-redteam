"""Public resource-resolution and case-generation interfaces."""

from typing import Protocol, runtime_checkable

from redteam.core.models.resources import (
    CaseGenerationRequest,
    DatasetEntry,
    GeneratedCaseDraft,
    PreparedTestItem,
    ResolvedEvaluationRule,
)
from redteam.core.models.step import AvailableStrategy
from redteam.core.models.task import (
    DatasetReference,
    EvaluationRuleReference,
    TaskDefinition,
    TestItem,
)


@runtime_checkable
class DatasetProvider(Protocol):
    """Load normalized entries from one exact dataset version."""

    def load(self, reference: DatasetReference) -> tuple[DatasetEntry, ...]:
        """Return all entries in deterministic source order."""

        ...


@runtime_checkable
class CaseGenerator(Protocol):
    """Generate initial risk-attack case drafts with the attacker model."""

    async def generate(
        self,
        request: CaseGenerationRequest,
    ) -> tuple[GeneratedCaseDraft, ...]:
        """Return exactly request.count generated drafts or raise AttackerError."""

        ...


@runtime_checkable
class AttackStrategyProvider(Protocol):
    """Resolve one strategy identifier into attacker-visible guidance."""

    def resolve(self, strategy_id: str) -> AvailableStrategy:
        """Return one exact strategy or raise ResourceResolutionError."""

        ...


@runtime_checkable
class EvaluationRuleResolver(Protocol):
    """Resolve a versioned rule reference to one concrete scorer version."""

    def resolve(
        self,
        reference: EvaluationRuleReference,
    ) -> ResolvedEvaluationRule:
        """Return the executable rule or raise ResourceResolutionError."""

        ...


@runtime_checkable
class TaskResourceResolver(Protocol):
    """Hide all raw resource formats from TaskRunner."""

    async def prepare(
        self,
        task: TaskDefinition,
        test_item: TestItem,
    ) -> PreparedTestItem:
        """Return one fully resolved test item or raise ResourceResolutionError."""

        ...
