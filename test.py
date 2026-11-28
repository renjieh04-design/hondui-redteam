"""Smoke test for the installed Hondui CLI."""

from importlib.metadata import version
from pathlib import Path
import subprocess
import sys


def test_cli_version() -> None:
    cli = Path(sys.executable).with_name("redteam")
    result = subprocess.run(
        [str(cli), "version"], check=True, capture_output=True, text=True, timeout=10
    )
    assert result.stdout.strip() == version("hondui-redteam")


if __name__ == "__main__":
    test_cli_version()
    print("CLI version check passed.")
