"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from grafid.config.manager import ConfigManager
from grafid.services.db_init import DatabaseInitService
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.runtime import reset_runtime_cache
from grafid.utils.logging_setup import reset_logging_for_tests


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Isolated config directory for tests."""
    config_dir = tmp_path / "graf-id-test"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def config_manager(temp_config_dir: Path) -> ConfigManager:
    return ConfigManager(config_dir=temp_config_dir)


@pytest.fixture
def db_path(config_manager: ConfigManager) -> Path:
    config_manager.bootstrap_defaults()
    config = config_manager.load()
    path = config.resolved_database_path(config_manager.config_dir)
    DatabaseInitService(path).initialize()
    return path


@pytest.fixture
def project_id(db_path: Path, tmp_path: Path) -> int:
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    record = ProjectRegistryService(db_path).add("test-project", str(project_dir))
    return record.id


@pytest.fixture(autouse=True)
def _reset_logging() -> None:
    reset_logging_for_tests()
    reset_runtime_cache()
    yield
    reset_logging_for_tests()
    reset_runtime_cache()
