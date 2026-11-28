"""File-to-model contract for Plan's YAML entry point."""

import traceback
from pathlib import Path

import pytest
import yaml

from redteam.config.yaml_loader import YamlTaskDefinitionLoader
from redteam.core.interfaces.configuration import TaskDefinitionLoader
from redteam.core.interfaces.errors import ConfigurationLoadError
from redteam.core.models.task import BaselineTestSpec, RiskTestSpec, TaskDefinition


@pytest.fixture
def config():
    return {
        "task_id": "plan-001",
        "name": "固定样本回归",
        "target": {
            "name": "fixture",
            "description": "Offline fixture",
            "adapter_type": "mock",
            "endpoint": "https://fixture.invalid",
            "api_key_ref": "env:FIXTURE_KEY",
        },
        "test_items": [{
            "item_id": "format",
            "kind": "baseline",
            "dataset": {"dataset_id": "format-check", "version": "1"},
            "evaluation_rule_refs": [{"rule_id": "exact", "version": "1"}],
        }],
    }


@pytest.fixture
def path(tmp_path):
    return tmp_path / "任务.yaml"


def write_config(path, config):
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")


def test_loads_complete_baseline_with_defaults(path, config, monkeypatch):
    monkeypatch.delenv("FIXTURE_KEY", raising=False)
    write_config(path, config)
    loader = YamlTaskDefinitionLoader()
    assert isinstance(loader, TaskDefinitionLoader)
    task = loader.load(path)
    assert isinstance(task, TaskDefinition)
    assert task == TaskDefinition.model_validate(config)
    assert isinstance(task.test_items[0], BaselineTestSpec)
    assert task.test_items[0].case_ids is None
    assert task.retry_policy.target.max_retries == 0
    assert task.target.api_key_ref == "env:FIXTURE_KEY"


def test_loads_risk_configuration_with_fixed_dataset(path, config):
    config["test_items"] = [{
        "item_id": "format-regression",
        "kind": "risk_attack",
        "risk_id": "fixture-format",
        "sources": {"datasets": [{
            "dataset": {"dataset_id": "format-check", "version": "1"}, "count": 1,
        }]},
        "strategy_refs": ["fixed-fixture"],
        "evaluation_rule_refs": [{"rule_id": "exact", "version": "1"}],
    }]
    write_config(path, config)
    task = YamlTaskDefinitionLoader().load(path)
    assert isinstance(task.test_items[0], RiskTestSpec)
    assert task.test_items[0].max_rounds == 1
    assert task.test_items[0].sources.datasets[0].count == 1


def assert_sanitized_failure(path: Path, expected: str):
    with pytest.raises(ConfigurationLoadError, match=expected) as caught:
        YamlTaskDefinitionLoader().load(path)
    assert "private-marker" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None


def test_missing_file(path):
    assert_sanitized_failure(path.with_name("private-marker.yaml"), "Cannot read")


@pytest.mark.parametrize(("content", "message"), [
    (b"private-marker: [\n", "line"),
    (b"---\n{}\n---\n{}", "Invalid YAML"),
    (b"!!python/name:private-marker", "Invalid YAML"),
    (b"\xff\x00\xfd", "Invalid YAML"),
    (b"!!timestamp 2026-02-31", "Invalid YAML"),
    (b"!!bool private-marker", "Invalid YAML"),
    (b"", "Invalid task configuration"),
    (b"- private-marker", "Invalid task configuration"),
])
def test_invalid_document(path, content, message):
    path.write_bytes(content)
    assert_sanitized_failure(path, message)


def test_missing_required_field(path, config):
    del config["target"]["endpoint"]
    write_config(path, config)
    assert_sanitized_failure(path, r"target\.endpoint \(missing\)")


def test_invalid_second_item_rejects_whole_task(path, config):
    invalid_item = dict(config["test_items"][0], item_id="other", case_ids="private-marker")
    config["test_items"].append(invalid_item)
    write_config(path, config)
    assert_sanitized_failure(path, r"test_items\.1\.baseline\.case_ids")


def test_unknown_key_does_not_expose_untrusted_field_name(path, config):
    config["target"]["private-marker"] = "private-marker"
    write_config(path, config)
    assert_sanitized_failure(path, r"target \(extra_forbidden\)")


def test_duplicate_item_id_fails_cross_item_validation(path, config):
    config["test_items"].append(config["test_items"][0].copy())
    write_config(path, config)
    assert_sanitized_failure(path, r"task \(value_error\)")


def test_invalid_item_kind_is_not_echoed(path, config):
    config["test_items"][0]["kind"] = "private-marker"
    write_config(path, config)
    assert_sanitized_failure(path, r"test_items\.0 \(union_tag_invalid\)")


@pytest.mark.parametrize("section", ["target", "attacker_model", "judge_model"])
def test_rejects_literal_credentials(path, config, section):
    if section != "target":
        config[section] = {"model": "fixture", "adapter_type": "mock", "endpoint": "local"}
    config[section]["api_key_ref"] = "private-marker"
    write_config(path, config)
    assert_sanitized_failure(path, rf"{section}\.api_key_ref")
