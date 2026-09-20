"""SQLite write helpers — commits are owned by the service layer."""

from __future__ import annotations

import sqlite3


def commit_write(connection: sqlite3.Connection) -> None:
    """
    Persist pending INSERT/UPDATE/DELETE on this connection.

    Call from services after repository writes. Read-only code must not call this.
    """
    connection.commit()
