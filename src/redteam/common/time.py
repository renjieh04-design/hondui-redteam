"""Timezone-aware UTC timestamps for persisted records."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current wall-clock time with the UTC timezone attached."""
    return datetime.now(UTC)


def to_utc_isoformat(value: datetime) -> str:
    """Convert an aware datetime to ISO 8601 with an explicit UTC offset."""
    if value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()
