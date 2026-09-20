"""Persisted scan snapshot models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScanSnapshotRecord:
    """One stored scan run for a project."""

    id: int
    project_id: int
    scanned_at: str
    scanned_files_count: int
    skipped_files_count: int
    findings_count: int
    duration_seconds: float
    warnings_count: int
    created_at: str


@dataclass(frozen=True)
class PersistedFindingRecord:
    """One task finding stored under a scan snapshot."""

    id: int
    snapshot_id: int
    file_path: str
    line_number: int
    marker: str
    text: str
    severity: str
    created_at: str


@dataclass(frozen=True)
class GitSnapshotRecord:
    """Git metadata stored for one scan snapshot."""

    id: int
    snapshot_id: int
    is_git_repo: bool
    current_branch: str | None
    is_detached_head: bool
    is_dirty: bool
    modified_files: list[str]
    staged_files: list[str]
    latest_commits: list[dict[str, str]]
    collected_at: str
    warning_message: str | None = None


@dataclass(frozen=True)
class SnapshotHistoryEntry:
    """Compact row for CLI history output."""

    snapshot_id: int
    scanned_at: str
    findings_count: int
    scanned_files_count: int
    duration_seconds: float
    is_git_repo: bool = False
    git_branch: str | None = None
    git_dirty: bool | None = None
