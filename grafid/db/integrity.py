"""Database integrity verification."""

from __future__ import annotations

import sqlite3

from grafid.core.exceptions import DatabaseError


def run_integrity_check(connection: sqlite3.Connection) -> None:
    """
    Run PRAGMA integrity_check and raise DatabaseError if corrupted.

    SQLite returns a single row 'ok' when healthy.
    """
    try:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError(f"Integrity check failed to run: {exc}") from exc

    if not rows:
        raise DatabaseError("Integrity check returned no result")

    messages = [str(row[0]) for row in rows]
    if len(messages) == 1 and messages[0].lower() == "ok":
        return

    raise DatabaseError(
        "Database integrity check failed: " + "; ".join(messages[:5])
    )
