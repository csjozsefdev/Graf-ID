"""Filesystem scan CLI command."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, TypeVar

import typer

from grafid.cli.common import exit_with_error

from grafid.services.runtime import prepare_runtime
from grafid.config.manager import ConfigManager
from grafid.observability.journal import record_event
from grafid.observability.timing import new_timing_collector, timed_block
from grafid.core.exceptions import (
    ConfigError,
    DatabaseError,
    GrafIdError,
    GrafPermissionError,
    ProjectError,
    ScanError,
    SnapshotError,
    StartupError,
    ValidationError,
)
from grafid.cli.git_display import print_scan_git_summary
from grafid.git import GitReadService
from grafid.scanner import ProjectScannerService, ScanResult
from grafid.services.snapshot_persistence import SnapshotPersistenceService
from grafid.scanner.models import TaskFinding
from grafid.scanner.task_parser import count_findings_by_marker

T = TypeVar("T")


def _run(action: Callable[[], T]) -> T:
    try:
        return action()
    except (
        ValidationError,
        ProjectError,
        ScanError,
        SnapshotError,
        ConfigError,
        DatabaseError,
        GrafPermissionError,
        StartupError,
    ) as exc:
        exit_with_error(str(exc))
    except GrafIdError as exc:
        exit_with_error(str(exc))


def format_finding_detail(finding: TaskFinding) -> str:
    """Format one finding for --details output."""
    text = finding.text or "(no description)"
    return (
        f"{finding.marker} {finding.file_path}:{finding.line_number} "
        f"[{finding.severity}] {text}"
    )


def _print_scan_summary(
    result: ScanResult, *, details: bool = False, snapshot_id: int | None = None
) -> None:
    typer.echo(f"project: {result.project_name}")
    typer.echo(f"path: {result.project_path}")
    typer.echo(f"scanned: {result.scanned_count}")
    typer.echo(f"ignored_dirs: {result.ignored_dirs_count}")
    typer.echo(
        f"skipped: {result.skipped_count} "
        f"(includes {result.ignored_dirs_count} ignored directories)"
    )
    typer.echo(f"findings: {result.findings_count}")
    typer.echo(f"warnings: {len(result.warnings)}")
    typer.echo(f"duration: {result.duration_seconds:.3f}s")
    if snapshot_id is not None:
        typer.echo(f"snapshot_id: {snapshot_id}")

    by_marker = count_findings_by_marker(result.findings)
    if by_marker:
        typer.echo("findings_by_marker:")
        for marker, count in by_marker.items():
            typer.echo(f"  {marker}: {count}")
    else:
        typer.echo("findings_by_marker: none")

    for warning in result.warnings:
        typer.echo(f"warning: {warning}")

    if details and result.findings:
        typer.echo("details:")
        for finding in sorted(
            result.findings,
            key=lambda item: (item.file_path, item.line_number, item.marker),
        ):
            typer.echo(f"  {format_finding_detail(finding)}")


def scan_cmd(
    identifier: Annotated[str, typer.Argument(help="Registered project id or name.")],
    details: Annotated[
        bool,
        typer.Option("--details", help="Show each finding with file and line."),
    ] = False,
) -> None:
    """Scan text files and detect TODO/FIXME-style task markers."""

    def _action() -> None:
        runtime = prepare_runtime()
        project = runtime.registry.get_info(identifier)
        mgr = ConfigManager()
        config = mgr.load()
        timing = new_timing_collector(config)
        with timed_block("scan", timing, project_id=project.id):
            result = ProjectScannerService().scan_project(
                project.path,
                project_name=project.name,
            )
        with timed_block("git_collect", timing):
            git_state = GitReadService().collect(project.path)
        persistence = SnapshotPersistenceService(runtime.database_path)
        with timed_block("snapshot_persist", timing):
            snapshot = persistence.save_snapshot(
                project.id, result, git_state=git_state
            )
        record_event(
            "cli.scan",
            config_dir=mgr.config_dir,
            config=config,
            project_id=project.id,
            findings=result.findings_count,
            duration_seconds=round(result.duration_seconds, 3),
            git_dirty=git_state.is_dirty if git_state.is_git_repo else None,
        )
        _print_scan_summary(result, details=details, snapshot_id=snapshot.id)
        print_scan_git_summary(git_state)
        if timing.enabled:
            for row in timing.as_list():
                typer.echo(
                    f"timing {row['operation']}: {row['duration_ms']}ms",
                    err=True,
                )

    _run(_action)
