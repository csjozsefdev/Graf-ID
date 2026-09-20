"""Schema v9 migration tests."""

from __future__ import annotations

import sqlite3

import pytest

from grafid.core.constants import SCHEMA_VERSION
from grafid.db.schema import apply_schema, get_schema_version


@pytest.fixture
def v8_db(tmp_path):
    """Simulate a v8 database without status/notes columns."""
    db_path = tmp_path / "graf-id.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)
        """
    )
    conn.execute("INSERT INTO schema_meta VALUES ('version', '8')")
    conn.execute(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            path TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_opened_at TEXT,
            preferred_ide TEXT,
            is_active INTEGER NOT NULL DEFAULT 0,
            category TEXT NOT NULL DEFAULT 'Personal Projects'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO projects (
            name, path, created_at, updated_at, is_active, category
        ) VALUES ('archived', '/tmp/a', 't', 't', 0, 'Archived')
        """
    )
    conn.execute(
        """
        INSERT INTO projects (
            name, path, created_at, updated_at, is_active, category
        ) VALUES ('active', '/tmp/b', 't', 't', 1, 'Client Work')
        """
    )
    conn.execute(
        """
        CREATE TABLE work_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            exit_note TEXT,
            blocker TEXT,
            next_step TEXT,
            snapshot_id_at_start INTEGER,
            snapshot_id_at_end INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO work_sessions (
            project_id, started_at, ended_at, created_at, updated_at
        ) VALUES (1, 't', 't', 't', 't')
        """
    )
    conn.commit()
    conn.close()
    return db_path


def test_migrate_v8_to_v9_adds_columns_and_status(v8_db) -> None:
    conn = sqlite3.connect(v8_db)
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    assert get_schema_version(conn) == SCHEMA_VERSION
    row = conn.execute("SELECT status FROM projects WHERE name = 'archived'").fetchone()
    assert row["status"] == "archived"
    session = conn.execute("SELECT status FROM work_sessions").fetchone()
    assert session["status"] == "completed"
    conn.close()
