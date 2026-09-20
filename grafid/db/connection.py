"""Safe SQLite connection handling."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from grafid.core.exceptions import DatabaseError, GrafPermissionError


class DatabaseConnection:
    """Context-managed SQLite connection with pragmatic defaults."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path.resolve()
        self._connection: sqlite3.Connection | None = None

    @property
    def path(self) -> Path:
        return self._db_path

    def connect(self) -> sqlite3.Connection:
        if self._connection is not None:
            return self._connection

        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise GrafPermissionError(
                f"Cannot create database directory at {self._db_path.parent}: {exc}"
            ) from exc

        try:
            conn = sqlite3.connect(self._db_path, timeout=30.0)
        except sqlite3.Error as exc:
            raise DatabaseError(f"Cannot open database at {self._db_path}: {exc}") from exc

        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        self._connection = conn
        return conn

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> sqlite3.Connection:
        return self.connect()

    def __exit__(self, *args: object) -> None:
        self.close()
