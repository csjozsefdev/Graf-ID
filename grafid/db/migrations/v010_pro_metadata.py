"""PRO v10: reserved migration hook (no-op for existing v9 databases)."""

from __future__ import annotations

import sqlite3


def apply(connection: sqlite3.Connection) -> None:
    """Bump schema marker; structural changes already applied via legacy migrators."""
    _ = connection
