"""SQLite schema definitions."""

from __future__ import annotations

import sqlite3

from grafid.core.constants import SCHEMA_VERSION

# Persisted-data compatibility only: settings live in config.json, and nothing reads
# or writes this key/value table. It stays in the schema so existing databases,
# migrations and backups remain valid; never drop it without a schema migration.
SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

META_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

PROJECTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_opened_at TEXT,
    preferred_ide TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT 'Personal Projects',
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    last_refreshed_at TEXT
);
"""

SCAN_SNAPSHOTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scan_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    scanned_at TEXT NOT NULL,
    scanned_files_count INTEGER NOT NULL,
    skipped_files_count INTEGER NOT NULL,
    findings_count INTEGER NOT NULL,
    duration_seconds REAL NOT NULL,
    warnings_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""

SCAN_FINDINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scan_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    marker TEXT NOT NULL,
    text TEXT NOT NULL,
    severity TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES scan_snapshots(id) ON DELETE CASCADE
);
"""

SCAN_SNAPSHOTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_scan_snapshots_project_scanned
ON scan_snapshots (project_id, scanned_at DESC);
"""

WORK_SESSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS work_sessions (
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
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    summary TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (snapshot_id_at_start) REFERENCES scan_snapshots(id) ON DELETE SET NULL,
    FOREIGN KEY (snapshot_id_at_end) REFERENCES scan_snapshots(id) ON DELETE SET NULL
);
"""

WORK_SESSIONS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_work_sessions_project_started
ON work_sessions (project_id, started_at DESC);
"""

RESUME_SUMMARIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS resume_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    session_id INTEGER,
    snapshot_id INTEGER,
    mode TEXT NOT NULL,
    summary_body TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES work_sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (snapshot_id) REFERENCES scan_snapshots(id) ON DELETE SET NULL
);
"""

RESUME_SUMMARIES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_resume_summaries_project_generated
ON resume_summaries (project_id, generated_at DESC);
"""

# Persisted-data compatibility only: the startup-card feature that wrote these
# rows was removed, and nothing reads or writes the table any more. It stays in
# the schema so existing databases, migrations and backups remain valid (and
# project deletion still cascades); never drop it without a schema migration.
STARTUP_SUMMARIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS startup_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    session_id INTEGER,
    snapshot_id INTEGER,
    headline TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    scroll_content TEXT NOT NULL,
    grifi_icon_state TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    dismissed_at TEXT,
    is_dismissed INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES work_sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (snapshot_id) REFERENCES scan_snapshots(id) ON DELETE SET NULL
);
"""

STARTUP_SUMMARIES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_startup_summaries_project_generated
ON startup_summaries (project_id, generated_at DESC);
"""

EXIT_NOTE_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS exit_note_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    exit_note TEXT,
    blocker TEXT,
    next_step TEXT,
    recorded_at TEXT NOT NULL,
    skipped INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES work_sessions(id) ON DELETE CASCADE
);
"""

EXIT_NOTE_HISTORY_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_exit_note_history_project_recorded
ON exit_note_history (project_id, recorded_at DESC);
"""

GIT_SNAPSHOTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS git_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL UNIQUE,
    is_git_repo INTEGER NOT NULL,
    current_branch TEXT,
    is_detached_head INTEGER NOT NULL DEFAULT 0,
    is_dirty INTEGER NOT NULL DEFAULT 0,
    modified_files_json TEXT NOT NULL DEFAULT '[]',
    staged_files_json TEXT NOT NULL DEFAULT '[]',
    latest_commits_json TEXT NOT NULL DEFAULT '[]',
    collected_at TEXT NOT NULL,
    warning_message TEXT,
    FOREIGN KEY (snapshot_id) REFERENCES scan_snapshots(id) ON DELETE CASCADE
);
"""


def apply_schema(connection: sqlite3.Connection) -> None:
    """Create required tables and apply incremental schema updates."""
    connection.execute(SETTINGS_TABLE_SQL)
    connection.execute(META_TABLE_SQL)
    connection.execute(PROJECTS_TABLE_SQL)
    connection.execute(SCAN_SNAPSHOTS_TABLE_SQL)
    connection.execute(SCAN_FINDINGS_TABLE_SQL)
    connection.execute(SCAN_SNAPSHOTS_INDEX_SQL)
    connection.execute(WORK_SESSIONS_TABLE_SQL)
    connection.execute(WORK_SESSIONS_INDEX_SQL)
    connection.execute(RESUME_SUMMARIES_TABLE_SQL)
    connection.execute(RESUME_SUMMARIES_INDEX_SQL)
    connection.execute(STARTUP_SUMMARIES_TABLE_SQL)
    connection.execute(STARTUP_SUMMARIES_INDEX_SQL)
    connection.execute(EXIT_NOTE_HISTORY_TABLE_SQL)
    connection.execute(EXIT_NOTE_HISTORY_INDEX_SQL)
    connection.execute(GIT_SNAPSHOTS_TABLE_SQL)
    _migrate_projects_category(connection)
    _migrate_mvp_v9(connection)
    from grafid.db.migrations import run_pending_migrations

    run_pending_migrations(connection)
    connection.execute(
        """
        INSERT INTO schema_meta (key, value)
        VALUES ('version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(SCHEMA_VERSION),),
    )
    connection.commit()


def _migrate_projects_category(connection: sqlite3.Connection) -> None:
    """Add projects.category for v8 when upgrading existing databases."""
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(projects)").fetchall()
    }
    if "category" not in columns:
        connection.execute(
            """
            ALTER TABLE projects
            ADD COLUMN category TEXT NOT NULL DEFAULT 'Personal Projects'
            """
        )


def _migrate_mvp_v9(connection: sqlite3.Connection) -> None:
    """Add MVP project/session fields for schema v9."""
    project_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(projects)").fetchall()
    }
    if "status" not in project_columns:
        connection.execute(
            """
            ALTER TABLE projects
            ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
            """
        )
    if "notes" not in project_columns:
        connection.execute("ALTER TABLE projects ADD COLUMN notes TEXT")
    if "last_refreshed_at" not in project_columns:
        connection.execute("ALTER TABLE projects ADD COLUMN last_refreshed_at TEXT")

    connection.execute(
        """
        UPDATE projects
        SET status = 'archived'
        WHERE category = 'Archived' AND (status IS NULL OR status = 'active')
        """
    )

    session_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(work_sessions)").fetchall()
    }
    if "status" not in session_columns:
        connection.execute(
            """
            ALTER TABLE work_sessions
            ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
            """
        )
    if "summary" not in session_columns:
        connection.execute("ALTER TABLE work_sessions ADD COLUMN summary TEXT")

    connection.execute(
        """
        UPDATE work_sessions
        SET status = 'completed'
        WHERE ended_at IS NOT NULL AND (status IS NULL OR status = 'active')
        """
    )
    connection.execute(
        """
        UPDATE work_sessions
        SET status = 'active'
        WHERE ended_at IS NULL AND (status IS NULL OR status = '')
        """
    )


def get_schema_version(connection: sqlite3.Connection) -> int | None:
    """Return stored schema version or None if metadata is missing."""
    try:
        row = connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None
