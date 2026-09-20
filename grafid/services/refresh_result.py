"""Structured refresh outcome for IPC and UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RefreshResult:
    """Result of a project context refresh (scan + optional git)."""

    scan_ok: bool
    snapshot_id: int | None = None
    scan_error: str | None = None
    git_ok: bool = True
    git_error: str | None = None
    warnings_count: int = 0
    skipped_files_count: int = 0
    scanned_files_count: int = 0
    findings_count: int = 0
    duration_seconds: float = 0.0
    snapshots_pruned: int = 0
    mode: str = "full"  # full | git_only
    scan_started_at: str | None = None
    scan_finished_at: str | None = None
    files_considered: int = 0
    files_scanned: int = 0
    files_skipped: int = 0
    cache_used: bool = False
    top_summary_sources: tuple[str, ...] = ()
    changed_files_seen: tuple[str, ...] = ()
    last_refreshed_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
