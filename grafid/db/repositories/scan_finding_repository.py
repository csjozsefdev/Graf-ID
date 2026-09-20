"""CRUD access for scan_findings."""

from __future__ import annotations

import sqlite3

from grafid.models.snapshot import PersistedFindingRecord
from grafid.scanner.models import TaskFinding


def _row_to_finding(row: sqlite3.Row) -> PersistedFindingRecord:
    return PersistedFindingRecord(
        id=int(row["id"]),
        snapshot_id=int(row["snapshot_id"]),
        file_path=str(row["file_path"]),
        line_number=int(row["line_number"]),
        marker=str(row["marker"]),
        text=str(row["text"]),
        severity=str(row["severity"]),
        created_at=str(row["created_at"]),
    )


class ScanFindingRepository:
    """SQLite repository for findings linked to a snapshot."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def insert_many(self, snapshot_id: int, findings: list[TaskFinding]) -> int:
        """Insert findings for one snapshot. Returns number of rows inserted."""
        if not findings:
            return 0

        rows = [
            (
                snapshot_id,
                finding.file_path,
                finding.line_number,
                finding.marker,
                finding.text,
                finding.severity,
                finding.created_at,
            )
            for finding in findings
        ]
        self._conn.executemany(
            """
            INSERT INTO scan_findings (
                snapshot_id, file_path, line_number, marker,
                text, severity, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        return len(rows)

    def list_for_snapshot(self, snapshot_id: int) -> list[PersistedFindingRecord]:
        rows = self._conn.execute(
            """
            SELECT * FROM scan_findings
            WHERE snapshot_id = ?
            ORDER BY file_path ASC, line_number ASC, marker ASC
            """,
            (snapshot_id,),
        ).fetchall()
        return [_row_to_finding(row) for row in rows]

    def count_for_snapshot(self, snapshot_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM scan_findings WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        return int(row["total"]) if row else 0
