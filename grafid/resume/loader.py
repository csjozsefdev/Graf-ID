"""Load persisted state for resume generation (database only)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from grafid.core.exceptions import ResumeError
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.git_snapshot_repository import GitSnapshotRepository
from grafid.db.repositories.project_repository import ProjectRepository
from grafid.db.repositories.scan_finding_repository import ScanFindingRepository
from grafid.db.repositories.session_repository import SessionRepository
from grafid.db.repositories.snapshot_repository import SnapshotRepository
from grafid.models.snapshot import PersistedFindingRecord
from grafid.resume.models import ResumeBundle


class ResumeDataLoader:
    """Aggregate project, session, snapshot, findings, and git data."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def load(self, project_id: int) -> ResumeBundle:
        """Load resume inputs for one project from SQLite."""
        try:
            with DatabaseConnection(self._db_path) as conn:
                project = ProjectRepository(conn).get_by_id(project_id)
                if project is None:
                    raise ResumeError(f"Project not found: {project_id}")

                active = SessionRepository(conn).get_active_for_project(project_id)
                ended = SessionRepository(conn).get_last_ended_for_project(project_id)
                session = active if active is not None else ended
                using_active = active is not None

                snapshot_id = _resolve_snapshot_id(session, project_id, conn)
                snapshot = (
                    SnapshotRepository(conn).get_by_id(snapshot_id)
                    if snapshot_id is not None
                    else None
                )

                findings: tuple[PersistedFindingRecord, ...] = ()
                git = None
                if snapshot_id is not None:
                    findings = tuple(
                        ScanFindingRepository(conn).list_for_snapshot(snapshot_id)
                    )
                    git = GitSnapshotRepository(conn).get_by_snapshot_id(snapshot_id)

        except ResumeError:
            raise
        except sqlite3.Error as exc:
            raise ResumeError(f"Failed to load resume data: {exc}") from exc

        return ResumeBundle(
            project_id=project_id,
            project_name=project.name,
            project_path=project.path,
            session=session,
            snapshot=snapshot,
            findings=findings,
            git=git,
            using_active_session=using_active,
        )


def _resolve_snapshot_id(
    session,
    project_id: int,
    connection: sqlite3.Connection,
) -> int | None:
    if session is not None:
        if session.snapshot_id_at_end is not None:
            return session.snapshot_id_at_end
        if session.snapshot_id_at_start is not None:
            return session.snapshot_id_at_start

    row = connection.execute(
        """
        SELECT id FROM scan_snapshots
        WHERE project_id = ?
        ORDER BY scanned_at DESC, id DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    return int(row["id"]) if row else None
