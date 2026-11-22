"""Public target execution and target adapter interfaces."""

from typing import Protocol, runtime_checkable

from redteam.core.models.execution import ExecutionAttempt
from redteam.core.models.target_request import (
    TargetAdapterRequest,
    TargetAdapterResponse,
    TargetExecutionRequest,
)


@runtime_checkable
class TargetAdapter(Protocol):
    """Perform one physical call using one provider-specific target format."""

    async def invoke(self, request: TargetAdapterRequest) -> TargetAdapterResponse:
        """Return a normalized success or raise TargetAdapterError."""

        ...


@runtime_checkable
class TargetExecutor(Protocol):
    """Execute exactly one physical attempt of a logical target request."""

    async def execute_once(
        self,
        request: TargetExecutionRequest,
        *,
        attempt_no: int,
    ) -> ExecutionAttempt:
        """Return one success or error attempt; never schedule a retry."""

        ...
