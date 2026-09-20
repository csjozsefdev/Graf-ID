"""Tests for default project opener preferences."""

from __future__ import annotations

import json

import pytest

from grafid.config.manager import AppConfig, ConfigManager
from grafid.config.preferences import (
    DEFAULT_PROJECT_OPENER_KEY,
    normalize_default_project_opener,
    opener_to_ide_token,
)
from grafid.core.exceptions import ConfigError
from grafid.ipc.settings_handlers import (
    handle_get_app_settings,
    handle_reset_app_settings,
    handle_save_app_settings,
    handle_set_default_project_opener,
)
from grafid.services.workflow_launch import detect_system_editor, resolve_preferred_ide
from grafid.services.project_registry import ProjectRegistryService


def test_normalize_default_project_opener_aliases() -> None:
    assert normalize_default_project_opener("VS Code") == "vscode"
    assert normalize_default_project_opener("Explorer only") == "explorer"
    assert normalize_default_project_opener("PyCharm") == "pycharm"
    assert normalize_default_project_opener(None) == "system"


def test_normalize_default_project_opener_rejects_unknown() -> None:
    with pytest.raises(ConfigError):
        normalize_default_project_opener("emacs")


def test_opener_to_ide_token_mapping() -> None:
    assert opener_to_ide_token("system") is None
    assert opener_to_ide_token("cursor") == "cursor"
    assert opener_to_ide_token("explorer") == "explorer"


def test_config_save_reload_default_opener(config_manager: ConfigManager) -> None:
    config = AppConfig(default_project_opener="cursor")
    config_manager.save(config)
    loaded = config_manager.load()
    assert loaded.default_project_opener == "cursor"
    data = json.loads(config_manager.config_path.read_text(encoding="utf-8"))
    assert data[DEFAULT_PROJECT_OPENER_KEY] == "cursor"


def test_config_migrates_legacy_preferred_ide(config_manager: ConfigManager) -> None:
    config_manager.ensure_directories()
    config_manager.config_path.write_text(
        json.dumps({"preferred_ide": "vscode"}),
        encoding="utf-8",
    )
    loaded = config_manager.load()
    assert loaded.default_project_opener == "vscode"


def test_app_settings_returns_defaults_on_invalid_config(
    config_manager: ConfigManager,
) -> None:
    config_manager.ensure_directories()
    config_manager.config_path.write_text("{ not json", encoding="utf-8")
    response = handle_get_app_settings(config_manager)
    assert response.ok is True
    assert response.data["default_project_opener"] == "system"
    assert response.data["usage_journal_enabled"] is False


def test_settings_ipc_roundtrip(config_manager: ConfigManager) -> None:
    response = handle_set_default_project_opener("explorer", config_manager)
    assert response.ok
    assert response.data["default_project_opener"] == "explorer"

    loaded = handle_get_app_settings(config_manager)
    assert loaded.ok
    assert loaded.data["default_project_opener"] == "explorer"
    assert loaded.data["usage_journal_enabled"] is False
    assert loaded.data["debug_timing_enabled"] is False
    assert "data_dir" in loaded.data
    assert "logs_dir" in loaded.data
    assert any(opt["id"] == "cursor" for opt in loaded.data["opener_options"])


def test_save_app_settings_persists_all_fields(config_manager: ConfigManager) -> None:
    response = handle_save_app_settings(
        "cursor",
        usage_journal="true",
        debug_timing="true",
        config_manager=config_manager,
    )
    assert response.ok
    assert response.data["default_project_opener"] == "cursor"
    assert response.data["usage_journal_enabled"] is True
    assert response.data["debug_timing_enabled"] is True

    reloaded = config_manager.load()
    assert reloaded.default_project_opener == "cursor"
    assert reloaded.usage_journal is True
    assert reloaded.debug_timing is True


def test_reset_app_settings(config_manager: ConfigManager) -> None:
    handle_save_app_settings(
        "vscode",
        usage_journal="true",
        debug_timing="true",
        config_manager=config_manager,
    )
    response = handle_reset_app_settings(config_manager)
    assert response.ok
    assert response.data["default_project_opener"] == "system"
    assert response.data["usage_journal_enabled"] is False
    assert response.data["debug_timing_enabled"] is False


def test_resolve_uses_default_opener(db_path, tmp_path) -> None:
    registry = ProjectRegistryService(db_path)
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    project = registry.add("demo", str(project_dir))
    config = AppConfig(default_project_opener="explorer")
    assert resolve_preferred_ide(project, config) == "explorer"


def test_detect_system_editor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "grafid.services.workflow_launch.shutil.which",
        lambda name: "cursor" if name == "cursor" else None,
    )
    assert detect_system_editor() == "cursor"
