"""Tests for local strategy catalog resolution."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import yaml

from redteam.attacker.strategy_provider import LocalAttackStrategyProvider
from redteam.core.interfaces import AttackStrategyProvider, ResourceResolutionError
from redteam.core.models import AvailableStrategy


class TestLocalAttackStrategyProvider(TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "strategies.yaml"
        self.provider = LocalAttackStrategyProvider(self.path)
        self.entry = {
            "strategy_id": "format-check",
            "name": "Format check",
            "description": "A local fixture.",
            "guidance": "Use the fixed example text.",
        }

    def write_catalog(self, entries: object) -> None:
        self.path.write_text(yaml.safe_dump(entries), encoding="utf-8")

    def test_returns_exact_typed_entry(self) -> None:
        self.write_catalog([dict(self.entry, strategy_id="other"), self.entry])

        self.assertIsInstance(self.provider, AttackStrategyProvider)
        self.assertEqual(
            self.provider.resolve("format-check"), AvailableStrategy(**self.entry)
        )

    def test_rejects_unknown_id(self) -> None:
        self.write_catalog([self.entry])

        with self.assertRaisesRegex(ResourceResolutionError, "not found"):
            self.provider.resolve("missing")

    def test_rejects_duplicate_ids_after_model_validation(self) -> None:
        self.write_catalog([self.entry, dict(self.entry, strategy_id=" format-check ")])

        with self.assertRaisesRegex(ResourceResolutionError, "duplicates"):
            self.provider.resolve("format-check")

    def test_rejects_invalid_fields_even_after_a_valid_match(self) -> None:
        for field in self.entry:
            for invalid in ("", "  ", None, 123):
                with self.subTest(field=field, invalid=invalid):
                    self.write_catalog([self.entry, dict(self.entry, **{field: invalid})])

                    with self.assertRaisesRegex(ResourceResolutionError, "entry 2"):
                        self.provider.resolve("format-check")

    def test_rejects_missing_or_extra_fields(self) -> None:
        incomplete = self.entry.copy()
        del incomplete["guidance"]
        for entry in (incomplete, dict(self.entry, extra_field="fixture")):
            with self.subTest(entry=entry):
                self.write_catalog([entry])

                with self.assertRaisesRegex(ResourceResolutionError, "entry 1"):
                    self.provider.resolve("format-check")

    def test_rejects_non_list_catalog(self) -> None:
        self.write_catalog(self.entry)

        with self.assertRaisesRegex(ResourceResolutionError, "list"):
            self.provider.resolve("format-check")

    def test_rejects_malformed_or_unsafe_yaml(self) -> None:
        for content in ("[unfinished", "!!python/object:example.Fixture {}"):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")

                with self.assertRaisesRegex(ResourceResolutionError, "YAML"):
                    self.provider.resolve("format-check")

    def test_rejects_invalid_utf8(self) -> None:
        self.path.write_bytes(b"\xff")

        with self.assertRaisesRegex(ResourceResolutionError, "UTF-8"):
            self.provider.resolve("format-check")

    def test_rejects_missing_catalog(self) -> None:
        with self.assertRaisesRegex(ResourceResolutionError, "read"):
            self.provider.resolve("format-check")
