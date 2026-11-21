"""Final attacker output for one risk-attack step."""

from typing import Annotated

from pydantic import PositiveInt, StringConstraints

from redteam.core.models.task import DomainModel, NonEmptyStr


ShortDecisionSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class AttackDecision(DomainModel):
    """One final strategy and prompt produced from one StepContext."""

    task_id: NonEmptyStr
    test_item_id: NonEmptyStr
    case_id: NonEmptyStr
    step_id: NonEmptyStr
    round_index: PositiveInt

    strategy_id: NonEmptyStr
    attack_prompt: NonEmptyStr
    decision_summary: ShortDecisionSummary
