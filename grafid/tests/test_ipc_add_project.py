"""Tests for add-project IPC."""

from __future__ import annotations

from pathlib import Path

from grafid.ipc.project_handlers import handle_add_project


def test_add_project_returns_dashboard_row(
    db_path, config_manager, tmp_path: Path
) -> None:
    project_dir = tmp_path / "my-app"
    project_dir.mkdir()
    response = handle_add_project("my-app", str(project_dir), config_manager=config_manager)
    assert response.ok is True
    project = response.data["project"]
    assert project["name"] == "my-app"
    assert project["path"] == str(project_dir.resolve())
    assert "git_status" in project
    assert "summary_preview" in project


def test_add_project_rejects_duplicate_path(
    db_path, config_manager, tmp_path: Path
) -> None:
    project_dir = tmp_path / "dup-app"
    project_dir.mkdir()
    first = handle_add_project("first-name", str(project_dir), config_manager=config_manager)
    assert first.ok is True
    second = handle_add_project("second-name", str(project_dir), config_manager=config_manager)
    assert second.ok is False
    assert second.error is not None
    assert second.error.code == "duplicate_project"


def test_add_project_with_category(
    db_path, config_manager, tmp_path: Path
) -> None:
    project_dir = tmp_path / "client-app"
    project_dir.mkdir()
    response = handle_add_project(
        "client-app",
        str(project_dir),
        category="Client Work",
        config_manager=config_manager,
    )
    assert response.ok is True
    assert response.data["project"]["category"] == "Client Work"


def test_add_project_rejects_invalid_path(config_manager) -> None:
    response = handle_add_project("missing", r"C:\graf-id-nonexistent-path-xyz", config_manager=config_manager)
    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "validation_error"
