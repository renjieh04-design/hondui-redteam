"""Public application entry interface for TaskRunner."""

from typing import Protocol, runtime_checkable

from redteam.core.models.context import TaskContext
from redteam.core.models.task import TaskDefinition


@runtime_checkable
class TaskRunner(Protocol):
    """Own task state, ordering, retry scheduling, and termination decisions."""

    async def run(self, task: TaskDefinition) -> TaskContext:
        """Run one task to a final context and persist every completed stage."""

        ...
