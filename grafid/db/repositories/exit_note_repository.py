"""
CRUD access for exit_note_history.

Insert does not commit — the service layer must call commit_write().
"""

from __future__ import annotations

import sqlite3

from grafid.models.exit_note import ExitNoteHistoryRecord
from grafid.utils.datetime_utils import utc_now_iso


class ExitNoteRepository:
    """SQLite repository for session close / exit note history."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def insert(
        self,
        project_id: int,
        session_id: int,
        *,
        exit_note: str | None,
        blocker: str | None,
        next_step: str | None,
        skipped: bool,
    ) -> ExitNoteHistoryRecord:
        recorded_at = utc_now_iso()
        cursor = self._conn.execute(
            """
            INSERT INTO exit_note_history (
                project_id, session_id,
                exit_note, blocker, next_step,
                recorded_at, skipped
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                session_id,
                exit_note,
                blocker,
                next_step,
                recorded_at,
                int(skipped),
            ),
        )
        record = self.get_by_id(int(cursor.lastrowid))
        if record is None:
            raise RuntimeError("Failed to load exit note history after insert")
        return record

    def get_by_id(self, record_id: int) -> ExitNoteHistoryRecord | None:
        row = self._conn.execute(
            "SELECT * FROM exit_note_history WHERE id = ?", (record_id,)
        ).fetchone()
        return _row_to_record(row) if row else None

    def list_for_project(
        self, project_id: int, *, limit: int = 20
    ) -> list[ExitNoteHistoryRecord]:
        rows = self._conn.execute(
            """
            SELECT * FROM exit_note_history
            WHERE project_id = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
        return [_row_to_record(row) for row in rows]


def _row_to_record(row: sqlite3.Row) -> ExitNoteHistoryRecord:
    return ExitNoteHistoryRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        session_id=int(row["session_id"]),
        exit_note=row["exit_note"],
        blocker=row["blocker"],
        next_step=row["next_step"],
        recorded_at=str(row["recorded_at"]),
        skipped=bool(row["skipped"]),
    )
