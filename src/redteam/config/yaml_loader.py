"""Load a complete V1 task definition from a YAML file."""

import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from redteam.core.interfaces.errors import ConfigurationLoadError
from redteam.core.models.task import TaskDefinition


class YamlTaskDefinitionLoader:
    """Validate one configuration without resolving resources or credentials."""

    def load(self, config_path: Path) -> TaskDefinition:
        try:
            with config_path.open("rb") as stream:
                document = yaml.safe_load(stream)
        except OSError:
            message = "Cannot read the task configuration file."
        except yaml.MarkedYAMLError as exc:
            mark = exc.problem_mark
            message = "Invalid YAML in the task configuration."
            if mark is not None:
                message += f" See line {mark.line + 1}, column {mark.column + 1}."
        except (
            yaml.YAMLError, ValueError, OverflowError, RecursionError, LookupError, AttributeError
        ):
            # SafeLoader can also raise Python exceptions when converting explicit scalar tags.
            message = "Invalid YAML in the task configuration."
        else:
            return self._validate(document)

        # Raise outside the handler: parser exceptions can contain the raw input.
        raise ConfigurationLoadError(message)

    @staticmethod
    def _validate(document: object) -> TaskDefinition:
        try:
            task = TaskDefinition.model_validate(document)
        except ValidationError as exc:
            error = exc.errors(
                include_input=False, include_context=False, include_url=False
            )[0]
            location = error["loc"]
            # Unknown mapping keys can themselves be secrets.
            if error["type"] in {"extra_forbidden", "invalid_key"}:
                location = location[:-1]
            field = ".".join(str(part) for part in location) or "task"
            message = f"Invalid task configuration at {field} ({error['type']})."
        else:
            for section in ("target", "attacker_model", "judge_model"):
                connection = getattr(task, section)
                if connection is None or connection.api_key_ref is None:
                    continue
                if not re.fullmatch(r"env:[A-Za-z_][A-Za-z0-9_]*", connection.api_key_ref):
                    raise ConfigurationLoadError(
                        f"{section}.api_key_ref must use env:VARIABLE_NAME."
                    )
            return task

        raise ConfigurationLoadError(message)
