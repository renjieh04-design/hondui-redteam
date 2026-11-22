"""Public provider-independent model client interface."""

from typing import Protocol, runtime_checkable

from redteam.core.models.model_call import ModelRequest, ModelResponse


@runtime_checkable
class ModelClient(Protocol):
    """Call one configured attacker or judge model without hidden retries."""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Return a normalized response or raise ModelClientError."""

        ...
