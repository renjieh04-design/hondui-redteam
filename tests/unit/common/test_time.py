"""Clock and timestamp conversion contracts."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from redteam.common.time import to_utc_isoformat, utc_now


def test_utc_now_tracks_the_system_clock_with_an_explicit_zone():
    before = datetime.now(UTC)
    first = utc_now()
    second = utc_now()
    after = datetime.now(UTC)
    assert first.tzinfo is UTC and second.tzinfo is UTC
    assert before <= first <= second <= after


def test_isoformat_normalizes_an_offset_and_preserves_microseconds():
    value = datetime(2026, 11, 27, 1, 2, 3, 456, timezone(timedelta(hours=8)))
    text = to_utc_isoformat(value)
    assert text == "2026-11-26T17:02:03.000456+00:00"
    assert datetime.fromisoformat(text) == value


def test_naive_timestamps_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        to_utc_isoformat(datetime(2026, 11, 27))
