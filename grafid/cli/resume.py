"""Resume summary CLI commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, TypeVar

import typer

from grafid.cli.common import exit_with_error

from grafid.services.runtime import prepare_runtime
from grafid.core.exceptions import (
    ConfigError,
    DatabaseError,
    GrafIdError,
    GrafPermissionError,
    ProjectError,
    ResumeError,
    SnapshotError,
    StartupError,
    ValidationError,
)
from grafid.resume.models import ResumeMode
from grafid.services.resume_service import ResumeService

T = TypeVar("T")


def _run(action: Callable[[], T]) -> T:
    try:
        return action()
    except (
        ValidationError,
        ProjectError,
        ResumeError,
        SnapshotError,
        ConfigError,
        DatabaseError,
        GrafPermissionError,
        StartupError,
    ) as exc:
        exit_with_error(str(exc))
    except GrafIdError as exc:
        exit_with_error(str(exc))


def _resolve_mode(*, short: bool, detailed: bool) -> ResumeMode:
    """Default to short output when no mode flag is passed."""
    if detailed:
        return "detailed"
    return "short"


def _generate_resume(
    identifier: str,
    *,
    short: bool,
    detailed: bool,
) -> None:
    runtime = prepare_runtime()
    project = runtime.registry.get_info(identifier)
    mode: ResumeMode = _resolve_mode(short=short, detailed=detailed)

    service = ResumeService(runtime.database_path)
    previous = service.get_previous_stored_summary(project.id, mode=mode)
    summary = service.generate_resume(project.id, mode=mode, persist=True)
    typer.echo(summary.body, nl=False)
    if summary.resume_id is not None:
        typer.echo(f"\nresume_id: {summary.resume_id} (mode={mode})")

    if previous is None:
        typer.echo("history: first stored resume for this project/mode")
    elif previous.summary_body != summary.body:
        typer.echo("history: changed since last stored resume")
    else:
        typer.echo("history: unchanged since last stored resume")


def resume_cmd(
    identifier: Annotated[str, typer.Argument(help="Registered project id or name.")],
    short: Annotated[
        bool,
        typer.Option("--short", help="Compact resume output (default when no mode flag)."),
    ] = False,
    detailed: Annotated[
        bool, typer.Option("--detailed", help="Include more findings and file lists.")
    ] = False,
) -> None:
    """
    Generate and store a fresh resume from session, scan, and git data.

    Examples:
      graf-id resume my-app
      graf-id resume my-app --short
      graf-id resume my-app --detailed
    """

    def _action() -> None:
        _generate_resume(identifier, short=short, detailed=detailed)

    _run(_action)


def resume_latest_cmd(
    identifier: Annotated[str, typer.Argument(help="Registered project id or name.")],
    short: Annotated[
        bool,
        typer.Option("--short", help="Load latest short-mode resume."),
    ] = True,
    detailed: Annotated[
        bool, typer.Option("--detailed", help="Load latest detailed-mode resume.")
    ] = False,
) -> None:
    """Print the most recently stored resume without regenerating."""

    def _action() -> None:
        runtime = prepare_runtime()
        project = runtime.registry.get_info(identifier)
        mode: ResumeMode = _resolve_mode(short=short, detailed=detailed)

        service = ResumeService(runtime.database_path)
        stored = service.get_latest_stored_summary(project.id, mode=mode)
        if stored is None:
            exit_with_error(
                "No stored resume for this project yet. "
                "Run: graf-id resume <project> --short"
            )
        typer.echo(stored.summary_body, nl=False)
        typer.echo(
            f"\nresume_id: {stored.id} (stored_at={stored.generated_at}, mode={stored.mode})"
        )

    _run(_action)
