"""Public attacker orchestration interface."""

from typing import Protocol, runtime_checkable

from redteam.core.models.decision import AttackDecision
from redteam.core.models.step import StepContext


@runtime_checkable
class Attacker(Protocol):
    """Produce one final attack decision for one immutable step context."""

    async def decide(self, context: StepContext) -> AttackDecision:
        """Return one decision or raise AttackerError without hidden retries."""

        ...
