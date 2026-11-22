"""Public evaluation orchestration and scorer interfaces."""

from typing import Protocol, runtime_checkable

from redteam.core.models.evaluation import EvaluationResult, ScorerResult
from redteam.core.models.evaluation_request import EvaluationRequest, ScoringRequest


@runtime_checkable
class Scorer(Protocol):
    """Apply one resolved rule to one exact scoring input."""

    async def score(self, request: ScoringRequest) -> ScorerResult:
        """Return one rule result or raise ScorerError without hidden retries."""

        ...


@runtime_checkable
class Evaluator(Protocol):
    """Evaluate one successful target execution using all resolved rules."""

    async def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        """Return a completed or error result; do not advance task state."""

        ...
