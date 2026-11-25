"""File integrity and atomic publication behavior."""

from pathlib import Path

import pytest

from redteam.common import files


def test_binary_write_creates_parents_and_matches_known_digest(tmp_path):
    path = tmp_path / "evidence" / "responses" / "sample.bin"

    files.atomic_write_bytes(path, b"abc")

    assert path.read_bytes() == b"abc"
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert files.sha256_bytes(b"abc") == files.sha256_file(path) == expected
    files.atomic_write_bytes(path, b"\x00\xff\r\n")
    assert path.read_bytes() == b"\x00\xff\r\n"
    assert files.sha256_file(path) != expected
    assert list(path.parent.iterdir()) == [path]


def test_text_replaces_existing_file_as_utf8(tmp_path):
    path = tmp_path / "report.md"
    path.write_bytes(b"old content")

    files.atomic_write_text(path, "# 测试报告\n")

    assert path.read_bytes() == "# 测试报告\n".encode("utf-8")


@pytest.mark.parametrize("destination_exists", [False, True])
def test_replace_failure_leaves_destination_intact_and_cleans_temp(
    tmp_path, monkeypatch, destination_exists
):
    path = tmp_path / "evidence.bin"
    if destination_exists:
        path.write_bytes(b"old")

    def fail_replace(source, destination):
        temporary = Path(source)
        assert temporary.parent == path.parent
        assert temporary.read_bytes() == b"complete new data"
        assert destination == path
        if destination_exists:
            assert path.read_bytes() == b"old"
        else:
            assert not path.exists()
        raise PermissionError("replacement blocked")

    monkeypatch.setattr(files.os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="replacement blocked"):
        files.atomic_write_bytes(path, b"complete new data")

    assert list(tmp_path.iterdir()) == ([path] if destination_exists else [])
    if destination_exists:
        assert path.read_bytes() == b"old"


def test_sync_failure_preserves_old_content(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_bytes(b"old")

    def fail_sync(fd):
        raise OSError("sync failed")

    monkeypatch.setattr(files.os, "fsync", fail_sync)
    with pytest.raises(OSError, match="sync failed"):
        files.atomic_write_bytes(path, b"new")

    assert path.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [path]
