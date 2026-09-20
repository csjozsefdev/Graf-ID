"""Compact CLI formatting for Git state."""

from __future__ import annotations

import typer

from grafid.git.models import GitState
from grafid.models.snapshot import GitSnapshotRecord


def print_live_git_state(git_state: GitState) -> None:
    """Print current Git metadata for graf-id info."""
    if not git_state.is_git_repo:
        typer.echo("git: not a repository")
        for warning in git_state.warnings:
            typer.echo(f"git_warning: {warning}")
        return

    typer.echo("git: yes")
    typer.echo(f"git_root: {git_state.repo_root or '-'}")
    typer.echo(f"branch: {git_state.current_branch or '-'}")
    typer.echo(f"detached_head: {int(git_state.is_detached_head)}")
    typer.echo(f"dirty: {int(git_state.is_dirty)}")
    typer.echo(f"clean: {int(git_state.is_clean)}")
    typer.echo(f"modified_count: {len(git_state.modified_files)}")
    typer.echo(f"staged_count: {len(git_state.staged_files)}")
    _print_commit_preview(git_state)
    for warning in git_state.warnings:
        typer.echo(f"git_warning: {warning}")


def print_scan_git_summary(git_state: GitState) -> None:
    """Print short Git lines after a scan."""
    if not git_state.is_git_repo:
        typer.echo("git: not a repository")
        return

    typer.echo("git: yes")
    typer.echo(f"branch: {git_state.current_branch or '-'}")
    typer.echo(f"dirty: {int(git_state.is_dirty)}")
    typer.echo(f"modified: {len(git_state.modified_files)}")
    typer.echo(f"staged: {len(git_state.staged_files)}")


def print_persisted_git_snapshot(record: GitSnapshotRecord | None) -> None:
    """Print Git metadata stored on the latest snapshot."""
    if record is None:
        typer.echo("latest_snapshot_git: none")
        return

    if not record.is_git_repo:
        typer.echo("latest_snapshot_git: not a repository")
        return

    typer.echo("latest_snapshot_git: yes")
    typer.echo(f"latest_snapshot_branch: {record.current_branch or '-'}")
    typer.echo(f"latest_snapshot_dirty: {int(record.is_dirty)}")


def _print_commit_preview(git_state: GitState, limit: int = 3) -> None:
    if not git_state.latest_commits:
        typer.echo("recent_commits: none")
        return

    typer.echo("recent_commits:")
    for commit in git_state.latest_commits[:limit]:
        short_hash = commit.commit_hash[:8]
        typer.echo(f"  {short_hash} {commit.subject}")
