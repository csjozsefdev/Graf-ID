"""
CRUD access for the projects table.

Write methods do not commit — the service layer must call commit_write().
"""

from __future__ import annotations

import sqlite3

from grafid.core.project_categories import DEFAULT_PROJECT_CATEGORY
from grafid.core.project_status import DEFAULT_PROJECT_STATUS
from grafid.models.project import ProjectRecord
from grafid.utils.datetime_utils import utc_now_iso


def _row_to_record(row: sqlite3.Row) -> ProjectRecord:
    keys = row.keys()
    status = (
        str(row["status"])
        if "status" in keys and row["status"] is not None
        else DEFAULT_PROJECT_STATUS
    )
    notes = row["notes"] if "notes" in keys else None
    last_refreshed = (
        row["last_refreshed_at"] if "last_refreshed_at" in keys else None
    )
    sidebar_order = (
        int(row["sidebar_order"])
        if "sidebar_order" in keys and row["sidebar_order"] is not None
        else None
    )
    return ProjectRecord(
        id=int(row["id"]),
        name=str(row["name"]),
        path=str(row["path"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        last_opened_at=row["last_opened_at"],
        preferred_ide=row["preferred_ide"],
        is_active=bool(row["is_active"]),
        category=str(row["category"]) if row["category"] is not None else DEFAULT_PROJECT_CATEGORY,
        status=status,
        notes=notes,
        last_refreshed_at=last_refreshed,
        sidebar_order=sidebar_order,
    )


class ProjectRepository:
    """SQLite repository for registered projects."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def list_all(self) -> list[ProjectRecord]:
        rows = self._conn.execute(
            """
            SELECT * FROM projects
            ORDER BY sidebar_order IS NULL, sidebar_order ASC, name COLLATE NOCASE ASC
            """
        ).fetchall()
        return [_row_to_record(row) for row in rows]

    def next_sidebar_order(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(sidebar_order), 0) + 1 AS next_order FROM projects"
        ).fetchone()
        return int(row["next_order"]) if row is not None else 1

    def reorder(self, ordered_ids: list[int]) -> None:
        if not ordered_ids:
            raise ValueError("ordered_ids cannot be empty")
        if len(set(ordered_ids)) != len(ordered_ids):
            raise ValueError("ordered_ids contains duplicates")
        existing = {
            int(row["id"])
            for row in self._conn.execute("SELECT id FROM projects").fetchall()
        }
        if set(ordered_ids) != existing:
            raise ValueError("ordered_ids must include every registered project once")
        now = utc_now_iso()
        for index, project_id in enumerate(ordered_ids, start=1):
            self._conn.execute(
                """
                UPDATE projects
                SET sidebar_order = ?, updated_at = ?
                WHERE id = ?
                """,
                (index, now, project_id),
            )

    def clear_preferred_ide(self, values: list[str]) -> list[ProjectRecord]:
        """Reset preferred_ide to NULL (inherit the default opener) for every
        project using one of `values`; returns the affected projects."""
        if not values:
            return []
        placeholders = ",".join("?" for _ in values)
        rows = self._conn.execute(
            f"SELECT * FROM projects WHERE preferred_ide IN ({placeholders})",
            tuple(values),
        ).fetchall()
        records = [_row_to_record(row) for row in rows]
        if records:
            self._conn.execute(
                f"UPDATE projects SET preferred_ide = NULL, updated_at = ? "
                f"WHERE preferred_ide IN ({placeholders})",
                (utc_now_iso(), *values),
            )
        return records

    def get_by_id(self, project_id: int) -> ProjectRecord | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return _row_to_record(row) if row else None

    def get_by_name(self, name: str) -> ProjectRecord | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE name = ?", (name,)
        ).fetchone()
        return _row_to_record(row) if row else None

    def get_by_path(self, path: str) -> ProjectRecord | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE path = ?", (path,)
        ).fetchone()
        return _row_to_record(row) if row else None

    def insert(
        self,
        name: str,
        path: str,
        *,
        preferred_ide: str | None = None,
        category: str = DEFAULT_PROJECT_CATEGORY,
        status: str = DEFAULT_PROJECT_STATUS,
        notes: str | None = None,
    ) -> ProjectRecord:
        now = utc_now_iso()
        sidebar_order = self.next_sidebar_order()
        cursor = self._conn.execute(
            """
            INSERT INTO projects (
                name, path, created_at, updated_at,
                last_opened_at, preferred_ide, is_active, category,
                status, notes, sidebar_order
            )
            VALUES (?, ?, ?, ?, NULL, ?, 0, ?, ?, ?, ?)
            """,
            (name, path, now, now, preferred_ide, category, status, notes, sidebar_order),
        )
        record = self.get_by_id(int(cursor.lastrowid))
        if record is None:
            raise RuntimeError("Failed to load project after insert")
        return record

    def delete_by_id(self, project_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM projects WHERE id = ?", (project_id,)
        )
        return cursor.rowcount > 0

    def update_last_opened(self, project_id: int) -> ProjectRecord | None:
        now = utc_now_iso()
        self._conn.execute(
            """
            UPDATE projects
            SET last_opened_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, project_id),
        )
        return self.get_by_id(project_id)

    def update_metadata(
        self,
        project_id: int,
        *,
        name: str | None = None,
        path: str | None = None,
        category: str | None = None,
        status: str | None = None,
        notes: str | None = None,
        preferred_ide: str | None = None,
    ) -> ProjectRecord | None:
        """Update editable project fields (None values are left unchanged)."""
        existing = self.get_by_id(project_id)
        if existing is None:
            return None
        now = utc_now_iso()
        self._conn.execute(
            """
            UPDATE projects
            SET name = ?, path = ?, category = ?, status = ?,
                notes = ?, preferred_ide = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name if name is not None else existing.name,
                path if path is not None else existing.path,
                category if category is not None else existing.category,
                status if status is not None else existing.status,
                notes if notes is not None else existing.notes,
                preferred_ide
                if preferred_ide is not None
                else existing.preferred_ide,
                now,
                project_id,
            ),
        )
        return self.get_by_id(project_id)

    def set_last_refreshed(self, project_id: int, refreshed_at: str) -> ProjectRecord | None:
        now = utc_now_iso()
        self._conn.execute(
            """
            UPDATE projects
            SET last_refreshed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (refreshed_at, now, project_id),
        )
        return self.get_by_id(project_id)
