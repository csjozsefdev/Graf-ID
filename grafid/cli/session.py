"""Work session CLI commands."""

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
    SessionError,
    SnapshotError,
    StartupError,
    ValidationError,
)
from grafid.models.session import ExitNoteInput
from grafid.services.session_service import SessionService

T = TypeVar("T")


def _run(action: Callable[[], T]) -> T:
    try:
        return action()
    except (
        ValidationError,
        ProjectError,
        SessionError,
        SnapshotError,
        ConfigError,
        DatabaseError,
        GrafPermissionError,
        StartupError,
    ) as exc:
        exit_with_error(str(exc))
    except GrafIdError as exc:
        exit_with_error(str(exc))


def _print_duration(service: SessionService, session) -> None:
    seconds = service.session_duration_seconds(session)
    typer.echo(f"duration_seconds: {seconds:.1f}")


def session_start_cmd(
    identifier: Annotated[str, typer.Argument(help="Registered project id or name.")],
) -> None:
    """Start a new work session for a project."""

    def _action() -> None:
        runtime = prepare_runtime()
        project = runtime.registry.get_info(identifier)
        service = SessionService(runtime.database_path)
        session = service.start_session(project.id)
        typer.echo(f"Session started for '{project.name}' (session_id={session.id})")
        typer.echo(f"started_at: {session.started_at}")
        if session.snapshot_id_at_start:
            typer.echo(f"snapshot_at_start: {session.snapshot_id_at_start}")
        else:
            typer.echo("snapshot_at_start: none (run graf-id scan to capture baseline)")

    _run(_action)


def session_end_cmd(
    identifier: Annotated[str, typer.Argument(help="Registered project id or name.")],
    done: Annotated[str | None, typer.Option("--done", help="What was completed.")] = None,
    blocker: Annotated[
        str | None, typer.Option("--blocker", help="Current blocker.")
    ] = None,
    next_step: Annotated[
        str | None, typer.Option("--next", help="Suggested next step.")
    ] = None,
) -> None:
    """End the active session and optionally save exit notes."""

    def _action() -> None:
        runtime = prepare_runtime()
        project = runtime.registry.get_info(identifier)
        service = SessionService(runtime.database_path)
        notes = ExitNoteInput(exit_note=done, blocker=blocker, next_step=next_step)
        session = service.end_active_session_for_project(project.id, notes=notes)
        typer.echo(f"Session ended for '{project.name}' (session_id={session.id})")
        typer.echo(f"ended_at: {session.ended_at}")
        _print_duration(service, session)
        if session.exit_note:
            typer.echo(f"done: {session.exit_note}")
        if session.blocker:
            typer.echo(f"blocker: {session.blocker}")
        if session.next_step:
            typer.echo(f"next: {session.next_step}")

    _run(_action)


def _collect_exit_notes(
    *,
    skip_notes: bool,
    prompt: bool,
    done: str | None,
    blocker: str | None,
    next_step: str | None,
) -> ExitNoteInput:
    if skip_notes:
        return ExitNoteInput()
    if done or blocker or next_step:
        return ExitNoteInput(exit_note=done, blocker=blocker, next_step=next_step)
    if prompt:
        typer.echo("Exit notes (press Enter to skip any field):")
        done_val = typer.prompt("What was done today?", default="", show_default=False)
        blocker_val = typer.prompt("Current blocker", default="", show_default=False)
        next_val = typer.prompt("Next step", default="", show_default=False)
        return ExitNoteInput(
            exit_note=done_val or None,
            blocker=blocker_val or None,
            next_step=next_val or None,
        )
    return ExitNoteInput()


def session_close_cmd(
    identifier: Annotated[str, typer.Argument(help="Registered project id or name.")],
    skip_notes: Annotated[
        bool,
        typer.Option("--skip-notes", help="Close without saving exit notes."),
    ] = False,
    prompt: Annotated[
        bool,
        typer.Option("--prompt", help="Ask for exit notes interactively."),
    ] = False,
    done: Annotated[str | None, typer.Option("--done", help="What was completed.")] = None,
    blocker: Annotated[
        str | None, typer.Option("--blocker", help="Current blocker.")
    ] = None,
    next_step: Annotated[
        str | None, typer.Option("--next", help="Suggested next step.")
    ] = None,
) -> None:
    """Close the active session with optional exit notes (safe to skip)."""

    def _action() -> None:
        runtime = prepare_runtime()
        project = runtime.registry.get_info(identifier)
        service = SessionService(runtime.database_path)
        notes = _collect_exit_notes(
            skip_notes=skip_notes,
            prompt=prompt,
            done=done,
            blocker=blocker,
            next_step=next_step,
        )
        session = service.close_active_session_for_project(
            project.id,
            notes=notes,
            skip_notes=skip_notes,
        )
        typer.echo(f"Session closed for '{project.name}' (session_id={session.id})")
        typer.echo(f"ended_at: {session.ended_at}")
        _print_duration(service, session)
        if skip_notes:
            typer.echo("exit_notes: skipped")
        else:
            if session.exit_note:
                typer.echo(f"done: {session.exit_note}")
            if session.blocker:
                typer.echo(f"blocker: {session.blocker}")
            if session.next_step:
                typer.echo(f"next: {session.next_step}")
            if not session.exit_note and not session.blocker and not session.next_step:
                typer.echo("exit_notes: none provided")

    _run(_action)


def session_status_cmd(
    identifier: Annotated[str, typer.Argument(help="Registered project id or name.")],
) -> None:
    """Show active or unfinished session state for a project."""

    def _action() -> None:
        runtime = prepare_runtime()
        project = runtime.registry.get_info(identifier)
        service = SessionService(runtime.database_path)
        status = service.get_status(project.id, project_name=project.name)

        typer.echo(f"project: {status.project_name}")
        typer.echo(f"active_session: {int(status.has_active_session)}")
        typer.echo(f"unfinished_session: {int(status.has_unfinished_session)}")

        if status.active_session:
            session = status.active_session
            typer.echo(f"session_id: {session.id}")
            typer.echo(f"started_at: {session.started_at}")
            _print_duration(service, session)
            typer.echo("recovery: unfinished session detected - run 'graf-id session end'")
            if session.snapshot_id_at_start:
                typer.echo(f"snapshot_at_start: {session.snapshot_id_at_start}")

            resume = service.build_resume_context(session.id)
            typer.echo(f"linked_findings_at_start: {resume.findings_at_start}")
            typer.echo(f"linked_git_branch_at_start: {resume.git_branch_at_start or '-'}")
        elif status.last_ended_session:
            last = status.last_ended_session
            typer.echo(f"last_session_id: {last.id}")
            typer.echo(f"last_ended_at: {last.ended_at}")
            _print_duration(service, last)
            if last.exit_note:
                typer.echo(f"last_done: {last.exit_note}")
            if last.blocker:
                typer.echo(f"last_blocker: {last.blocker}")
            if last.next_step:
                typer.echo(f"last_next: {last.next_step}")
        else:
            typer.echo("No sessions recorded yet. Use 'graf-id session start'.")

    _run(_action)
