"""CRUD access for scan_snapshots."""

from __future__ import annotations

import sqlite3

from grafid.models.snapshot import ScanSnapshotRecord, SnapshotHistoryEntry
from grafid.utils.datetime_utils import utc_now_iso


def _row_to_snapshot(row: sqlite3.Row) -> ScanSnapshotRecord:
    return ScanSnapshotRecord(
        id=int(row["id"]),
        project_id=int(row["project_id"]),
        scanned_at=str(row["scanned_at"]),
        scanned_files_count=int(row["scanned_files_count"]),
        skipped_files_count=int(row["skipped_files_count"]),
        findings_count=int(row["findings_count"]),
        duration_seconds=float(row["duration_seconds"]),
        warnings_count=int(row["warnings_count"]),
        created_at=str(row["created_at"]),
    )


class SnapshotRepository:
    """SQLite repository for scan snapshot headers."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def insert(
        self,
        project_id: int,
        *,
        scanned_at: str,
        scanned_files_count: int,
        skipped_files_count: int,
        findings_count: int,
        duration_seconds: float,
        warnings_count: int,
    ) -> ScanSnapshotRecord:
        created_at = utc_now_iso()
        cursor = self._conn.execute(
            """
            INSERT INTO scan_snapshots (
                project_id, scanned_at, scanned_files_count,
                skipped_files_count, findings_count, duration_seconds,
                warnings_count, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                scanned_at,
                scanned_files_count,
                skipped_files_count,
                findings_count,
                duration_seconds,
                warnings_count,
                created_at,
            ),
        )
        record = self.get_by_id(int(cursor.lastrowid))
        if record is None:
            raise RuntimeError("Failed to load snapshot after insert")
        return record

    def get_by_id(self, snapshot_id: int) -> ScanSnapshotRecord | None:
        row = self._conn.execute(
            "SELECT * FROM scan_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
        return _row_to_snapshot(row) if row else None

    def list_history_for_project(
        self, project_id: int, *, limit: int = 50
    ) -> list[SnapshotHistoryEntry]:
        rows = self._conn.execute(
            """
            SELECT
                s.id,
                s.scanned_at,
                s.findings_count,
                s.scanned_files_count,
                s.duration_seconds,
                g.is_git_repo,
                g.current_branch,
                g.is_dirty
            FROM scan_snapshots s
            LEFT JOIN git_snapshots g ON g.snapshot_id = s.id
            WHERE s.project_id = ?
            ORDER BY s.scanned_at DESC, s.id DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
        return [
            SnapshotHistoryEntry(
                snapshot_id=int(row["id"]),
                scanned_at=str(row["scanned_at"]),
                findings_count=int(row["findings_count"]),
                scanned_files_count=int(row["scanned_files_count"]),
                duration_seconds=float(row["duration_seconds"]),
                is_git_repo=bool(row["is_git_repo"]) if row["is_git_repo"] is not None else False,
                git_branch=row["current_branch"],
                git_dirty=bool(row["is_dirty"]) if row["is_dirty"] is not None else None,
            )
            for row in rows
        ]
