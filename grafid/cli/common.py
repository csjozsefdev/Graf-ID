"""Helpers shared by the Typer command modules."""

from __future__ import annotations

from typing import NoReturn

import typer


def exit_with_error(message: str, code: int = 1) -> NoReturn:
    """Print ``Error: <message>`` to stderr and exit the command with ``code``."""
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code)
