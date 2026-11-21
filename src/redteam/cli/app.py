"""Minimal command-line entry point for the framework."""

from __future__ import annotations

import typer

from redteam import __version__

app = typer.Typer(
    name="redteam",
    help="Run and inspect LLM red-team tests.",
    no_args_is_help=True,
)


@app.callback()
def cli() -> None:
    """Run and inspect LLM red-team tests."""


@app.command()
def version() -> None:
    """Print the installed framework version."""

    typer.echo(__version__)


def main() -> None:
    """Run the command-line application."""

    app()


if __name__ == "__main__":
    main()
