"""Tests for development vs packaged runtime path resolution."""

from __future__ import annotations

from pathlib import Path


from grafid.config.manager import AppConfig
from grafid.config.paths import resolve_app_config_dir
from grafid.packaging.runtime import detect_runtime_mode, resolve_runtime_layout
from grafid.packaging.validation import validate_runtime


def test_resolve_app_config_dir_from_env(monkeypatch, tmp_path: Path) -> None:
    data = tmp_path / "user-data"
    monkeypatch.setenv("GRAFID_DATA_DIR", str(data))
    assert resolve_app_config_dir() == data.resolve()


def test_relative_database_path_resolves_under_config_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    config = AppConfig(database_path="custom.db")
    resolved = config.resolved_database_path(config_dir)
    assert resolved == (config_dir / "custom.db").resolve()


def test_detect_packaged_mode_from_env(monkeypatch) -> None:
    monkeypatch.setenv("GRAFID_RUNTIME_MODE", "packaged")
    assert detect_runtime_mode() == "packaged"


def test_detect_development_mode_default(monkeypatch) -> None:
    monkeypatch.delenv("GRAFID_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("GRAFID_PYTHON", raising=False)
    monkeypatch.delenv("GRAFID_RESOURCE_ROOT", raising=False)
    assert detect_runtime_mode() == "development"


def test_runtime_layout_uses_data_dir(monkeypatch, tmp_path: Path) -> None:
    data = tmp_path / "packaged-data"
    monkeypatch.setenv("GRAFID_DATA_DIR", str(data))
    monkeypatch.setenv("GRAFID_RUNTIME_MODE", "packaged")
    layout = resolve_runtime_layout()
    assert layout.mode == "packaged"
    assert layout.data_dir == data.resolve()
    assert layout.database_path == (data / "graf-id.db").resolve()


def test_validate_runtime_ok(monkeypatch, tmp_path: Path) -> None:
    data = tmp_path / "valid"
    monkeypatch.setenv("GRAFID_DATA_DIR", str(data))
    report = validate_runtime(config_dir_override=data)
    assert report.ok is True
    assert report.config_valid is True
    assert report.database_ok is True


def test_validate_runtime_corrupt_config(monkeypatch, tmp_path: Path) -> None:
    data = tmp_path / "bad-config"
    data.mkdir()
    (data / "config.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("GRAFID_DATA_DIR", str(data))
    report = validate_runtime(config_dir_override=data)
    assert report.ok is False
    assert report.config_valid is False
    assert any("Config" in issue for issue in report.issues)


def test_ipc_runtime_check_handler(config_manager, monkeypatch) -> None:
    from grafid.ipc.handlers import handle_runtime_check

    monkeypatch.setenv("GRAFID_DATA_DIR", str(config_manager.config_dir))
    response = handle_runtime_check()
    assert response.ok is True
    assert response.data is not None
    assert response.data["mode"] in ("development", "packaged")


def test_packaged_resource_root_prefers_site_packages(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    site = runtime / "Lib" / "site-packages"
    site.mkdir(parents=True)
    (site / "grafid").mkdir()
    (runtime / "python.exe").write_bytes(b"")

    monkeypatch.setenv("GRAFID_PYTHON", str(runtime / "python.exe"))
    monkeypatch.setenv("GRAFID_RUNTIME_MODE", "packaged")

    from grafid.packaging.runtime import resolve_resource_root

    assert resolve_resource_root() == site.resolve()
