"""File integrity checks and atomic replacement for local files."""

import hashlib
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def sha256_bytes(content: bytes) -> str:
    """Return the hexadecimal SHA-256 digest of the supplied bytes."""
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hash a file without loading its entire contents into memory."""
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_write_bytes(path: str | Path, content: bytes) -> None:
    """Publish a complete file with one replacement on the same filesystem."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=".redteam-", suffix=".tmp", delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
    except BaseException:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                # Keep the original exception if cleanup also fails.
                pass
        raise


def atomic_write_text(path: str | Path, content: str) -> None:
    """Write UTF-8 text with its line endings preserved."""
    atomic_write_bytes(path, content.encode("utf-8"))
