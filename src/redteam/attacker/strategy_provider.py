"""Resolve strategy data from a local YAML catalog."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from redteam.core.interfaces import ResourceResolutionError
from redteam.core.models import AvailableStrategy


class LocalAttackStrategyProvider:
    """Resolve an exact strategy ID from a validated catalog."""

    def __init__(self, path: str | Path = "resources/strategies.yaml") -> None:
        self._path = Path(path)

    def resolve(self, strategy_id: str) -> AvailableStrategy:
        try:
            entries = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        except OSError:
            raise ResourceResolutionError("Could not read the strategy catalog.") from None
        except (yaml.YAMLError, ValueError, OverflowError):
            raise ResourceResolutionError("The strategy catalog is not valid UTF-8 YAML.") from None

        if not isinstance(entries, list):
            raise ResourceResolutionError("The strategy catalog must be a list of entries.")

        strategies: dict[str, AvailableStrategy] = {}
        for index, entry in enumerate(entries, start=1):
            try:
                strategy = AvailableStrategy.model_validate(entry)
            except ValidationError:
                raise ResourceResolutionError(
                    f"Strategy entry {index} has invalid fields."
                ) from None

            if strategy.strategy_id in strategies:
                raise ResourceResolutionError(
                    f"Strategy entry {index} duplicates an earlier strategy ID."
                )
            strategies[strategy.strategy_id] = strategy

        try:
            return strategies[strategy_id]
        except KeyError:
            raise ResourceResolutionError("The requested strategy ID was not found.") from None
