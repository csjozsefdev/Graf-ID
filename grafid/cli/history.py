"""Scan snapshot history CLI command."""

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
    SnapshotError,
    StartupError,
    ValidationError,
)
from grafid.services.snapshot_persistence import SnapshotPersistenceService

T = TypeVar("T")


def _run(action: Callable[[], T]) -> T:
    try:
        return action()
    except (
        ValidationError,
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


def _print_history(project_name: str, entries: list) -> None:
    typer.echo(f"project: {project_name}")
    if not entries:
        typer.echo("No scan history for this project.")
        return

    typer.echo("id\tscanned_at\tfindings\tfiles\tduration_s\tgit\tbranch\tdirty")
    for entry in entries:
        git_flag = "yes" if entry.is_git_repo else "no"
        branch = entry.git_branch or "-"
        if not entry.is_git_repo:
            dirty = "-"
        elif entry.git_dirty is None:
            dirty = "-"
        else:
            dirty = str(int(entry.git_dirty))
        typer.echo(
            f"{entry.snapshot_id}\t{entry.scanned_at}\t{entry.findings_count}\t"
            f"{entry.scanned_files_count}\t{entry.duration_seconds:.3f}\t"
            f"{git_flag}\t{branch}\t{dirty}"
        )


def history_cmd(
    identifier: Annotated[str, typer.Argument(help="Registered project id or name.")],
) -> None:
    """List previous scan snapshots for a registered project."""

    def _action() -> None:
        runtime = prepare_runtime()
        project = runtime.registry.get_info(identifier)
        persistence = SnapshotPersistenceService(runtime.database_path)
        entries = persistence.list_history(project.id)
        _print_history(project.name, entries)

    _run(_action)
