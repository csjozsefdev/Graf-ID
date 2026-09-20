"""Tests for configuration handling."""

from __future__ import annotations

import json

import pytest

from grafid.config.manager import AppConfig, ConfigManager
from grafid.core.exceptions import ConfigError


def test_bootstrap_creates_config_and_directories(
    config_manager: ConfigManager,
) -> None:
    config = config_manager.bootstrap_defaults()

    assert config_manager.config_dir.exists()
    assert (config_manager.config_dir / "logs").exists()
    assert config_manager.config_path.exists()
    assert config.log_level == "INFO"
    assert config.database_path is None


def test_load_returns_defaults_when_missing(temp_config_dir) -> None:
    manager = ConfigManager(config_dir=temp_config_dir)
    config = manager.load()
    assert config == AppConfig()


def test_save_and_reload_roundtrip(config_manager: ConfigManager) -> None:
    config = AppConfig(database_path="/custom/path.db", log_level="WARNING")
    config_manager.save(config)

    loaded = config_manager.load()
    assert loaded.database_path == "/custom/path.db"
    assert loaded.log_level == "WARNING"


def test_invalid_json_raises_config_error(config_manager: ConfigManager) -> None:
    config_manager.ensure_directories()
    config_manager.config_path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid config JSON"):
        config_manager.load()


def test_resolved_database_path_default(config_manager: ConfigManager) -> None:
    config = AppConfig()
    db_path = config.resolved_database_path(config_manager.config_dir)
    assert db_path.name == "graf-id.db"
    assert db_path.parent == config_manager.config_dir


def test_config_file_is_valid_json(config_manager: ConfigManager) -> None:
    config_manager.bootstrap_defaults()
    data = json.loads(config_manager.config_path.read_text(encoding="utf-8"))
    assert "log_level" in data


def test_invalid_log_level_raises(config_manager: ConfigManager) -> None:
    config_manager.ensure_directories()
    config_manager.config_path.write_text(
        json.dumps({"log_level": "VERBOSE"}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Invalid log_level"):
        config_manager.load()
