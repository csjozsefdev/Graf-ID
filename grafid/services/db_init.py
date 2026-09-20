"""Database creation and schema initialization."""

from __future__ import annotations

from pathlib import Path

from grafid.core.constants import SCHEMA_VERSION
from grafid.core.exceptions import DatabaseError
from grafid.db.connection import DatabaseConnection
from grafid.db.integrity import run_integrity_check
from grafid.db.schema import apply_schema, get_schema_version
from grafid.utils.logging_setup import get_logger

logger = get_logger("db_init")


class DatabaseInitService:
    """Creates the database file, applies schema, and verifies integrity."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    def initialize(self, *, verify: bool = True) -> Path:
        """
        Ensure database exists with current schema and optional integrity check.

        Returns the resolved database path.
        """
        existed = self._db_path.exists()
        log = logger.debug if existed else logger.info
        log("Initializing database at %s", self._db_path)

        with DatabaseConnection(self._db_path) as conn:
            apply_schema(conn)
            version = get_schema_version(conn)
            if version != SCHEMA_VERSION:
                raise DatabaseError(
                    f"Unexpected schema version {version}; expected {SCHEMA_VERSION}"
                )
            if verify:
                run_integrity_check(conn)

        log("Database ready at %s", self._db_path)
        return self._db_path

    def check_integrity(self) -> None:
        """Run integrity check on an existing database."""
        if not self._db_path.exists():
            raise DatabaseError(f"Database file not found at {self._db_path}")

        with DatabaseConnection(self._db_path) as conn:
            run_integrity_check(conn)

        logger.info("Integrity check passed for %s", self._db_path)
