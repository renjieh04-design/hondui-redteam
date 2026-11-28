"""Generate identifiers shared by V1 modules."""

from uuid import uuid4


def generate_id(prefix: str | None = None) -> str:
    """Return a UUID4 hex string, optionally preceded by ``prefix-``.

    The prefix is a caller-defined label. An empty or omitted prefix produces
    the plain UUID.
    """
    identifier = uuid4().hex
    return f"{prefix}-{identifier}" if prefix else identifier
