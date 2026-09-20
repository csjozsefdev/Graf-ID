"""Tests for startup integrity verification."""

from __future__ import annotations

import sqlite3

import pytest

from grafid.config.manager import ConfigManager
from grafid.core.exceptions import StartupError
from grafid.db.integrity import run_integrity_check
from grafid.services.db_init import DatabaseInitService
from grafid.services.startup import StartupService


def test_integrity_check_passes_on_healthy_db(
    config_manager: ConfigManager,
) -> None:
    config = config_manager.bootstrap_defaults()
    db_path = config.resolved_database_path(config_manager.config_dir)
    DatabaseInitService(db_path).initialize()

    with sqlite3.connect(db_path) as conn:
        run_integrity_check(conn)


def test_startup_wraps_database_errors(config_manager: ConfigManager) -> None:
    config_manager.bootstrap_defaults()
    config = config_manager.load()
    db_path = config.resolved_database_path(config_manager.config_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"corrupt")

    with pytest.raises(StartupError):
        StartupService(config_manager=config_manager).run()


def test_settings_table_columns(config_manager: ConfigManager) -> None:
    config = config_manager.bootstrap_defaults()
    db_path = config.resolved_database_path(config_manager.config_dir)
    DatabaseInitService(db_path).initialize()

    with sqlite3.connect(db_path) as conn:
        info = conn.execute("PRAGMA table_info(settings)").fetchall()
    columns = {row[1] for row in info}
    assert columns == {"id", "key", "value", "created_at", "updated_at"}
