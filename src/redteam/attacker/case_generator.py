"""Generate normalized initial case drafts with an attacker model."""

import json

from pydantic import ValidationError

from redteam.attacker.prompts import build_case_generation_request
from redteam.core.interfaces import AttackerError, ModelClient, ModelClientError
from redteam.core.models import (
    CaseGenerationRequest,
    GeneratedCaseDraft,
    ModelResponse,
)


class ModelCaseGenerator:
    """Generate exactly the requested number of validated initial drafts."""

    def __init__(self, model_client: ModelClient) -> None:
        self._model_client = model_client

    async def generate(
        self,
        request: CaseGenerationRequest,
    ) -> tuple[GeneratedCaseDraft, ...]:
        """Call the attacker model once and validate its complete JSON output."""

        model_request = build_case_generation_request(request)
        try:
            response = await self._model_client.complete(model_request)
        except ModelClientError as error:
            raise AttackerError(
                str(error),
                retryable_error_type=error.retryable_error_type,
            ) from None

        try:
            return _parse_generated_cases(response, expected_count=request.count)
        except (json.JSONDecodeError, ValidationError, _InvalidGeneratedCases):
            raise AttackerError(
                "The attacker model returned invalid generated cases."
            ) from None


class _InvalidGeneratedCases(Exception):
    """The generated response did not match the V1 output contract."""


def _parse_generated_cases(
    response: ModelResponse,
    *,
    expected_count: int,
) -> tuple[GeneratedCaseDraft, ...]:
    payload = json.loads(response.text)
    if not isinstance(payload, dict) or set(payload) != {"cases"}:
        raise _InvalidGeneratedCases
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list) or len(raw_cases) != expected_count:
        raise _InvalidGeneratedCases
    return tuple(GeneratedCaseDraft.model_validate(item) for item in raw_cases)
