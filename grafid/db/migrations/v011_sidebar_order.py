"""v11: persisted sidebar project order."""

from __future__ import annotations

import sqlite3


def apply(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(projects)").fetchall()
    }
    if "sidebar_order" not in columns:
        connection.execute("ALTER TABLE projects ADD COLUMN sidebar_order INTEGER")
