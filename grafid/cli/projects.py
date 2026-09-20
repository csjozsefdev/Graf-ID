"""Project registry CLI commands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar

import typer

from grafid.cli.common import exit_with_error

from grafid.cli.git_display import print_live_git_state, print_persisted_git_snapshot
from grafid.services.runtime import prepare_runtime
from grafid.git import GitReadService
from grafid.services.snapshot_persistence import SnapshotPersistenceService
from grafid.core.exceptions import (
    ConfigError,
    DatabaseError,
    DuplicateProjectError,
    GrafIdError,
    GrafPermissionError,
    ProjectError,
    SnapshotError,
    StartupError,
    ValidationError,
)
from grafid.models.project import ProjectRecord

OptionalStr = Annotated[str | None, typer.Option(help="Preferred IDE identifier.")]

T = TypeVar("T")


def _run(action: Callable[[], T]) -> T:
    try:
        return action()
    except (
        ValidationError,
        DuplicateProjectError,
        ProjectError,
        SnapshotError,
        ConfigError,
        DatabaseError,
        GrafPermissionError,
        StartupError,
    ) as exc:
        exit_with_error(str(exc))
    except GrafIdError as exc:
        exit_with_error(str(exc))


def _format_list_line(record: ProjectRecord) -> str:
    opened = record.last_opened_at or "-"
    return f"{record.id}\t{record.name}\t{record.path}\t{opened}"


def add_cmd(
    name: Annotated[str, typer.Argument(help="Unique project name.")],
    path: Annotated[str, typer.Argument(help="Absolute or relative project directory.")],
    ide: OptionalStr = None,
) -> None:
    """Register a local project directory."""

    def _action() -> None:
        record = prepare_runtime().registry.add(name, path, preferred_ide=ide)
        typer.echo(f"Added project '{record.name}' (id={record.id})")

    _run(_action)


def list_cmd() -> None:
    """List registered projects."""

    def _action() -> None:
        projects = prepare_runtime().registry.list_projects()
        if not projects:
            typer.echo("No projects registered.")
            return
        typer.echo("id\tname\tpath\tlast_opened_at")
        for record in projects:
            typer.echo(_format_list_line(record))

    _run(_action)


def remove_cmd(
    identifier: Annotated[str, typer.Argument(help="Project id or name.")],
) -> None:
    """Remove a registered project."""

    def _action() -> None:
        record = prepare_runtime().registry.remove(identifier)
        typer.echo(f"Removed project '{record.name}' (id={record.id})")

    _run(_action)


def info_cmd(
    identifier: Annotated[str, typer.Argument(help="Project id or name.")],
) -> None:
    """Show details for one project."""

    def _action() -> None:
        runtime = prepare_runtime()
        record = runtime.registry.get_info(identifier)
        typer.echo(f"id: {record.id}")
        typer.echo(f"name: {record.name}")
        typer.echo(f"path: {record.path}")
        typer.echo(f"created_at: {record.created_at}")
        typer.echo(f"updated_at: {record.updated_at}")
        typer.echo(f"last_opened_at: {record.last_opened_at or '-'}")
        typer.echo(f"preferred_ide: {record.preferred_ide or '-'}")
        typer.echo(f"is_active: {int(record.is_active)}")

        git_state = GitReadService().collect(Path(record.path))
        print_live_git_state(git_state)

        persistence = SnapshotPersistenceService(runtime.database_path)
        latest_git = persistence.get_latest_git_snapshot(record.id)
        print_persisted_git_snapshot(latest_git)

    _run(_action)


def open_cmd(
    identifier: Annotated[str, typer.Argument(help="Project id or name.")],
) -> None:
    """Resume workflow: session, preferred editor, or Explorer fallback."""

    def _action() -> None:
        from grafid.config.manager import ConfigManager
        from grafid.services.workflow_launch import WorkflowLaunchService

        runtime = prepare_runtime()
        config_dir = runtime.database_path.parent
        config = ConfigManager(config_dir).load()
        project = runtime.registry.get_info(identifier)
        launcher = WorkflowLaunchService(runtime.database_path, runtime.registry)
        updated, outcome = launcher.open_project(project.id, config=config)
        typer.echo(f"Opened project '{updated.name}' (id={updated.id})")
        typer.echo(f"last_opened_at: {updated.last_opened_at}")
        typer.echo(outcome.message)
        if outcome.session_id is not None:
            typer.echo(
                f"session_id: {outcome.session_id} "
                f"({'started' if outcome.session_started else 'active'})"
            )

    _run(_action)
