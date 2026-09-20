"""v12: DB-level guard for at most one active (unended) session per project (H5)."""

from __future__ import annotations

import sqlite3


def apply(connection: sqlite3.Connection) -> None:
    _heal_duplicate_active_sessions(connection)
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_session_per_project
        ON work_sessions (project_id)
        WHERE ended_at IS NULL
        """
    )


def _heal_duplicate_active_sessions(connection: sqlite3.Connection) -> None:
    """
    Defensive data repair before the unique index is created.

    The application layer has always enforced "one active session per project"
    (SessionService.start_session uses BEGIN IMMEDIATE + check-then-insert), so
    this should be a no-op on every real database. It exists only so that an
    unexpected pre-existing violation can't make this migration fail outright
    and leave the app unable to start. Where duplicates exist, the most
    recently started session per project is kept active; the rest are force-
    ended (status "abandoned") with a note — no in-progress work is discarded,
    it is simply marked as an ended session rather than silently deleted.
    """
    rows = connection.execute(
        """
        SELECT id, project_id
        FROM work_sessions
        WHERE ended_at IS NULL
        ORDER BY project_id, started_at DESC, id DESC
        """
    ).fetchall()

    seen_projects: set[int] = set()
    to_close: list[int] = []
    for row in rows:
        session_id = row[0]
        project_id = row[1]
        if project_id in seen_projects:
            to_close.append(session_id)
        else:
            seen_projects.add(project_id)

    if not to_close:
        return

    from grafid.utils.datetime_utils import utc_now_iso

    now = utc_now_iso()
    for session_id in to_close:
        connection.execute(
            """
            UPDATE work_sessions
            SET ended_at = ?,
                status = 'abandoned',
                summary = COALESCE(summary || ' ', '') ||
                    'Auto-closed: duplicate active session found during schema migration.',
                updated_at = ?
            WHERE id = ?
            """,
            (now, now, session_id),
        )
