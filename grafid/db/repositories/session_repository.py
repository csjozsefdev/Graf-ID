"""
CRUD access for work_sessions.

Write methods do not commit — SessionService owns commits via commit_write().
"""

from __future__ import annotations

import sqlite3

from grafid.core.session_status import DEFAULT_SESSION_STATUS
from grafid.models.session import ExitNoteInput, WorkSessionRecord
from grafid.utils.datetime_utils import utc_now_iso


def _row_to_session(row: sqlite3.Row) -> WorkSessionRecord:
    keys = row.keys()
    status = (
        str(row["status"])
        if "status" in keys and row["status"] is not None
        else DEFAULT_SESSION_STATUS
    )
    summary = row["summary"] if "summary" in keys else None
    return WorkSessionRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        started_at=str(row["started_at"]),
        ended_at=row["ended_at"],
        exit_note=row["exit_note"],
        blocker=row["blocker"],
        next_step=row["next_step"],
        snapshot_id_at_start=row["snapshot_id_at_start"],
        snapshot_id_at_end=row["snapshot_id_at_end"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        status=status,
        summary=summary,
    )


class SessionRepository:
    """SQLite repository for workflow sessions."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def insert_start(
        self,
        project_id: int,
        *,
        snapshot_id_at_start: int | None,
        summary: str | None = None,
    ) -> WorkSessionRecord:
        now = utc_now_iso()
        cursor = self._conn.execute(
            """
            INSERT INTO work_sessions (
                project_id, started_at, ended_at,
                exit_note, blocker, next_step,
                snapshot_id_at_start, snapshot_id_at_end,
                created_at, updated_at, status, summary
            )
            VALUES (?, ?, NULL, NULL, NULL, NULL, ?, NULL, ?, ?, 'active', ?)
            """,
            (project_id, now, snapshot_id_at_start, now, now, summary),
        )
        record = self.get_by_id(int(cursor.lastrowid))
        if record is None:
            raise RuntimeError("Failed to load session after insert")
        return record

    def end_session(
        self,
        session_id: int,
        *,
        ended_at: str,
        notes: ExitNoteInput,
        snapshot_id_at_end: int | None,
        status: str = "completed",
        summary: str | None = None,
    ) -> WorkSessionRecord | None:
        self._conn.execute(
            """
            UPDATE work_sessions
            SET ended_at = ?,
                exit_note = ?,
                blocker = ?,
                next_step = ?,
                snapshot_id_at_end = ?,
                updated_at = ?,
                status = ?,
                summary = COALESCE(?, summary)
            WHERE id = ? AND ended_at IS NULL
            """,
            (
                ended_at,
                notes.exit_note,
                notes.blocker,
                notes.next_step,
                snapshot_id_at_end,
                ended_at,
                status,
                summary,
                session_id,
            ),
        )
        return self.get_by_id(session_id)

    def get_by_id(self, session_id: int) -> WorkSessionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM work_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return _row_to_session(row) if row else None

    def get_active_for_project(self, project_id: int) -> WorkSessionRecord | None:
        row = self._conn.execute(
            """
            SELECT * FROM work_sessions
            WHERE project_id = ? AND ended_at IS NULL
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return _row_to_session(row) if row else None

    def get_last_ended_for_project(self, project_id: int) -> WorkSessionRecord | None:
        row = self._conn.execute(
            """
            SELECT * FROM work_sessions
            WHERE project_id = ? AND ended_at IS NOT NULL
            ORDER BY ended_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return _row_to_session(row) if row else None

    def list_for_project(self, project_id: int, *, limit: int = 20) -> list[WorkSessionRecord]:
        rows = self._conn.execute(
            """
            SELECT * FROM work_sessions
            WHERE project_id = ?
            ORDER BY started_at DESC, id DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
        return [_row_to_session(row) for row in rows]
