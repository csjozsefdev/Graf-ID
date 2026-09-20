"""Display-ready scan history rows for the desktop History UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from grafid.utils.datetime_utils import parse_iso
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.git_snapshot_repository import GitSnapshotRepository
from grafid.db.repositories.session_repository import SessionRepository
from grafid.models.session import WorkSessionRecord
from grafid.models.snapshot import SnapshotHistoryEntry
from grafid.resume.display_format import (
    build_scan_summary_preview,
    format_display_timestamp,
    format_duration_label,
    session_duration_seconds,
)
from grafid.resume.quality import normalize_note
from grafid.services.snapshot_persistence import SnapshotPersistenceService

SUMMARY_PREVIEW_MAX_CHARS = 160


@dataclass(frozen=True)
class HistoryDisplayRow:
    """One scan snapshot row with human-facing display fields."""

    snapshot_id: int
    scanned_at: str
    project_name: str
    scanned_at_label: str
    summary_preview: str
    changed_files_count: int | None
    session_duration_label: str | None
    findings_count: int
    scanned_files_count: int
    duration_seconds: float
    git_branch: str | None
    git_dirty: bool | None
    is_git_repo: bool
    summary_source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "scanned_at": self.scanned_at,
            "project_name": self.project_name,
            "scanned_at_label": self.scanned_at_label,
            "summary_preview": self.summary_preview,
            "changed_files_count": self.changed_files_count,
            "session_duration_label": self.session_duration_label,
            "findings_count": self.findings_count,
            "scanned_files_count": self.scanned_files_count,
            "duration_seconds": self.duration_seconds,
            "git_branch": self.git_branch,
            "git_dirty": self.git_dirty,
            "is_git_repo": self.is_git_repo,
            "summary_source": self.summary_source,
        }


def _first_line(text: str | None, *, limit: int = SUMMARY_PREVIEW_MAX_CHARS) -> str | None:
    cleaned = normalize_note(text)
    if not cleaned:
        return None
    first = cleaned.split("\n", 1)[0].strip()
    if not first:
        return None
    if len(first) <= limit:
        return first
    return first[: limit - 3].rstrip() + "..."


def correlate_session_for_scan(
    sessions: list[WorkSessionRecord],
    scanned_at: str,
) -> WorkSessionRecord | None:
    """
    Best-effort: pick the latest ended session at or before ``scanned_at``.

    This is not a guaranteed session-to-snapshot link.
    """
    scan_dt = parse_iso(scanned_at)
    if scan_dt is None:
        return None

    best: WorkSessionRecord | None = None
    best_ended: datetime | None = None
    for session in sessions:
        if session.ended_at is None:
            continue
        ended_dt = parse_iso(session.ended_at)
        if ended_dt is None or ended_dt > scan_dt:
            continue
        if best_ended is None or ended_dt > best_ended:
            best = session
            best_ended = ended_dt
    return best


def _session_preview(session: WorkSessionRecord) -> str | None:
    for candidate in (session.exit_note, session.summary):
        line = _first_line(candidate)
        if line:
            return line
    return None


def _session_duration_label(session: WorkSessionRecord) -> str | None:
    return format_duration_label(
        session_duration_seconds(session.started_at, session.ended_at)
    )


def build_history_display_rows(
    *,
    project_id: int,
    project_name: str,
    db_path: Path,
    limit: int = 15,
    entries: list[SnapshotHistoryEntry] | None = None,
) -> list[dict[str, Any]]:
    """Build display-ready history rows for IPC and bootstrap cache."""
    if entries is None:
        entries = SnapshotPersistenceService(db_path).list_history(
            project_id, limit=limit
        )
    else:
        entries = entries[:limit]

    with DatabaseConnection(db_path) as conn:
        sessions = SessionRepository(conn).list_for_project(project_id, limit=50)
        git_repo = GitSnapshotRepository(conn)

        rows: list[HistoryDisplayRow] = []
        for entry in entries:
            changed_files_count: int | None = None
            try:
                git = git_repo.get_by_snapshot_id(entry.snapshot_id)
                if git is not None:
                    changed_files_count = len(git.modified_files)
            except Exception:  # noqa: BLE001 — per-row degrade
                changed_files_count = None

            session = correlate_session_for_scan(sessions, entry.scanned_at)
            summary_preview: str
            summary_source: str
            session_duration_label: str | None = None

            session_line = _session_preview(session) if session is not None else None
            if session_line:
                summary_preview = session_line
                summary_source = "session_best_effort"
                if session is not None:
                    session_duration_label = _session_duration_label(session)
            else:
                summary_preview = build_scan_summary_preview(
                    scanned_files_count=entry.scanned_files_count,
                    findings_count=entry.findings_count,
                    git_branch=entry.git_branch,
                    git_dirty=entry.git_dirty,
                )
                summary_source = "scan"

            scanned_label = format_display_timestamp(entry.scanned_at)
            rows.append(
                HistoryDisplayRow(
                    snapshot_id=entry.snapshot_id,
                    scanned_at=entry.scanned_at,
                    project_name=project_name,
                    scanned_at_label=scanned_label or entry.scanned_at,
                    summary_preview=summary_preview,
                    changed_files_count=changed_files_count,
                    session_duration_label=session_duration_label,
                    findings_count=entry.findings_count,
                    scanned_files_count=entry.scanned_files_count,
                    duration_seconds=entry.duration_seconds,
                    git_branch=entry.git_branch,
                    git_dirty=entry.git_dirty,
                    is_git_repo=entry.is_git_repo,
                    summary_source=summary_source,
                )
            )
    return [row.to_dict() for row in rows]
