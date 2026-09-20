"""Tests for database initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from grafid.config.manager import ConfigManager
from grafid.core.constants import SCHEMA_VERSION
from grafid.core.exceptions import DatabaseError
from grafid.db.schema import get_schema_version
from grafid.services.db_init import DatabaseInitService
from grafid.services.startup import StartupService


def test_initialize_creates_database_and_settings_table(
    config_manager: ConfigManager,
) -> None:
    config = config_manager.bootstrap_defaults()
    db_path = config.resolved_database_path(config_manager.config_dir)

    DatabaseInitService(db_path).initialize()

    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        version = get_schema_version(conn)
    assert "settings" in tables
    assert "schema_meta" in tables
    assert version == SCHEMA_VERSION


def test_initialize_is_idempotent(config_manager: ConfigManager) -> None:
    config = config_manager.bootstrap_defaults()
    db_path = config.resolved_database_path(config_manager.config_dir)
    service = DatabaseInitService(db_path)

    service.initialize()
    service.initialize()

    assert db_path.exists()


def test_integrity_check_on_missing_db_raises(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    with pytest.raises(DatabaseError, match="not found"):
        DatabaseInitService(missing).check_integrity()


def test_corrupted_db_fails_integrity_check(
    config_manager: ConfigManager,
) -> None:
    config = config_manager.bootstrap_defaults()
    db_path = config.resolved_database_path(config_manager.config_dir)
    DatabaseInitService(db_path).initialize()

    # Truncate file to simulate corruption
    db_path.write_bytes(b"not a valid sqlite file")

    with pytest.raises(DatabaseError, match="(?i)integrity|database"):
        DatabaseInitService(db_path).check_integrity()


def test_startup_service_full_flow(config_manager: ConfigManager) -> None:
    result = StartupService(config_manager=config_manager).run()

    assert result.config_dir == config_manager.config_dir
    assert result.database_path.exists()
    assert result.config_path.exists()
