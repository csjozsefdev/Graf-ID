"""
CRUD access for persisted resume summaries.

Insert does not commit — the service layer must commit via commit_write().
"""

from __future__ import annotations

import sqlite3

from grafid.resume.models import ResumeMode, ResumeSummaryRecord
from grafid.utils.datetime_utils import utc_now_iso


class ResumeRepository:
    """SQLite repository for resume summary history."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def insert(
        self,
        project_id: int,
        *,
        session_id: int | None,
        snapshot_id: int | None,
        mode: ResumeMode,
        summary_body: str,
    ) -> ResumeSummaryRecord:
        generated_at = utc_now_iso()
        cursor = self._conn.execute(
            """
            INSERT INTO resume_summaries (
                project_id, session_id, snapshot_id, mode,
                summary_body, generated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, session_id, snapshot_id, mode, summary_body, generated_at),
        )
        record = self.get_by_id(int(cursor.lastrowid))
        if record is None:
            raise RuntimeError("Failed to load resume summary after insert")
        return record

    def get_by_id(self, summary_id: int) -> ResumeSummaryRecord | None:
        row = self._conn.execute(
            "SELECT * FROM resume_summaries WHERE id = ?", (summary_id,)
        ).fetchone()
        return _row_to_record(row) if row else None

    def get_latest_for_project(
        self, project_id: int, *, mode: ResumeMode | None = None
    ) -> ResumeSummaryRecord | None:
        if mode is None:
            row = self._conn.execute(
                """
                SELECT * FROM resume_summaries
                WHERE project_id = ?
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT * FROM resume_summaries
                WHERE project_id = ? AND mode = ?
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
                """,
                (project_id, mode),
            ).fetchone()
        return _row_to_record(row) if row else None

    def get_previous_for_project(
        self, project_id: int, *, mode: ResumeMode | None = None
    ) -> ResumeSummaryRecord | None:
        """Return the second-most-recent summary (for history comparison)."""
        if mode is None:
            rows = self._conn.execute(
                """
                SELECT * FROM resume_summaries
                WHERE project_id = ?
                ORDER BY generated_at DESC, id DESC
                LIMIT 2
                """,
                (project_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM resume_summaries
                WHERE project_id = ? AND mode = ?
                ORDER BY generated_at DESC, id DESC
                LIMIT 2
                """,
                (project_id, mode),
            ).fetchall()
        if len(rows) < 2:
            return None
        return _row_to_record(rows[1])


def _row_to_record(row: sqlite3.Row) -> ResumeSummaryRecord:
    return ResumeSummaryRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        session_id=row["session_id"],
        snapshot_id=row["snapshot_id"],
        mode=str(row["mode"]),
        summary_body=str(row["summary_body"]),
        generated_at=str(row["generated_at"]),
    )
