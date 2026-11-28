"""Tests for plain and prefixed identifiers."""

from uuid import UUID

from redteam.common.ids import generate_id


def test_plain_and_prefixed_ids():
    for prefix in (None, "", "test-call", "evidence"):
        identifier = generate_id(prefix)
        label = f"{prefix}-" if prefix else ""
        assert identifier.startswith(label)
        suffix = identifier.removeprefix(label)
        parsed = UUID(suffix)
        assert parsed.hex == suffix
        assert parsed.version == 4


def test_prefixed_ids_are_unique_across_a_batch():
    identifiers = {generate_id("attempt") for _ in range(1_000)}
    assert len(identifiers) == 1_000
