"""Build resume context from persisted session links (no scanner/git calls)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from grafid.core.exceptions import SessionError
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.git_snapshot_repository import GitSnapshotRepository
from grafid.db.repositories.scan_finding_repository import ScanFindingRepository
from grafid.db.repositories.project_repository import ProjectRepository
from grafid.db.repositories.snapshot_repository import SnapshotRepository
from grafid.models.session import SessionResumeContext, WorkSessionRecord


class SessionResumeService:
    """Load the scan and git state linked to a session's starting snapshot."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def build_context(self, session: WorkSessionRecord) -> SessionResumeContext:
        """Assemble the linked start-of-session data from database links only."""
        try:
            with DatabaseConnection(self._db_path) as conn:
                project = ProjectRepository(conn).get_by_id(session.project_id)
                if project is None:
                    raise SessionError(f"Project not found: {session.project_id}")

                start_meta = _snapshot_summary(conn, session.snapshot_id_at_start)
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to build resume context: {exc}") from exc

        return SessionResumeContext(
            session=session,
            project_name=project.name,
            snapshot_at_start=session.snapshot_id_at_start,
            findings_at_start=start_meta["findings"],
            git_branch_at_start=start_meta["branch"],
        )


def _snapshot_summary(connection: sqlite3.Connection, snapshot_id: int | None) -> dict:
    if snapshot_id is None:
        return {"findings": 0, "branch": None}

    snapshot = SnapshotRepository(connection).get_by_id(snapshot_id)
    if snapshot is None:
        return {"findings": 0, "branch": None}

    findings = ScanFindingRepository(connection).count_for_snapshot(snapshot_id)
    git_row = GitSnapshotRepository(connection).get_by_snapshot_id(snapshot_id)
    branch = git_row.current_branch if git_row and git_row.is_git_repo else None

    return {"findings": findings, "branch": branch}
