"""Public interface for turning one YAML file into a task definition."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from redteam.core.models.task import TaskDefinition


@runtime_checkable
class TaskDefinitionLoader(Protocol):
    """Load and fully validate one task configuration.

    Implementations raise ConfigurationLoadError for expected read, parse, or
    validation failures and must never return a partially valid definition.
    """

    def load(self, config_path: Path) -> TaskDefinition:
        """Return the complete immutable task definition in the YAML file."""

        ...
