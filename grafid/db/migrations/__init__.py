"""Schema migration runner (forward-only)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from grafid.core.constants import SCHEMA_VERSION
from grafid.db.migrations import (
    v010_pro_metadata,
    v011_sidebar_order,
    v012_one_active_session_per_project,
)

MigrationFn = Callable[[sqlite3.Connection], None]

# Ordered list: target version after each step.
MIGRATIONS: list[tuple[int, MigrationFn]] = [
    (10, v010_pro_metadata.apply),
    (11, v011_sidebar_order.apply),
    (12, v012_one_active_session_per_project.apply),
]


def get_schema_version(connection: sqlite3.Connection) -> int | None:
    from grafid.db.schema import get_schema_version as _get

    return _get(connection)


def run_pending_migrations(connection: sqlite3.Connection) -> int:
    """
    Apply numbered migrations from current schema_meta version to SCHEMA_VERSION.

    Returns final schema version.
    """
    current = get_schema_version(connection) or 0
    for target_version, migrate_fn in MIGRATIONS:
        if current >= target_version:
            continue
        if target_version > SCHEMA_VERSION:
            break
        migrate_fn(connection)
        connection.execute(
            """
            INSERT INTO schema_meta (key, value)
            VALUES ('version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(target_version),),
        )
        current = target_version
    return current
