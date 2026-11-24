"""Produce one validated attack decision with an attacker model."""

import json

from pydantic import ValidationError

from redteam.attacker.prompts import build_attack_decision_request
from redteam.core.interfaces import AttackerError, ModelClient, ModelClientError
from redteam.core.models import AttackDecision, ModelResponse, StepContext


_MODEL_OUTPUT_FIELDS = {
    "strategy_id",
    "attack_prompt",
    "decision_summary",
}


class ModelAttacker:
    """Generate one final decision for one immutable step context."""

    def __init__(self, model_client: ModelClient) -> None:
        self._model_client = model_client

    async def decide(self, context: StepContext) -> AttackDecision:
        """Call the attacker model once and validate its complete JSON output."""

        model_request = build_attack_decision_request(context)
        try:
            response = await self._model_client.complete(model_request)
        except ModelClientError as error:
            raise AttackerError(
                str(error),
                retryable_error_type=error.retryable_error_type,
            ) from None

        try:
            return _parse_attack_decision(response, context=context)
        except (json.JSONDecodeError, ValidationError, _InvalidAttackDecision):
            raise AttackerError(
                "The attacker model returned an invalid attack decision."
            ) from None


class _InvalidAttackDecision(Exception):
    """The model response did not match the single-decision contract."""


def _parse_attack_decision(
    response: ModelResponse,
    *,
    context: StepContext,
) -> AttackDecision:
    payload = json.loads(response.text)
    if not isinstance(payload, dict) or set(payload) != _MODEL_OUTPUT_FIELDS:
        raise _InvalidAttackDecision

    decision = AttackDecision(
        task_id=context.task_id,
        test_item_id=context.test_item_id,
        case_id=context.case_id,
        step_id=context.step_id,
        round_index=context.round_index,
        strategy_id=payload["strategy_id"],
        attack_prompt=payload["attack_prompt"],
        decision_summary=payload["decision_summary"],
    )
    allowed_strategy_ids = {
        strategy.strategy_id for strategy in context.available_strategies
    }
    if decision.strategy_id not in allowed_strategy_ids:
        raise _InvalidAttackDecision
    return decision
