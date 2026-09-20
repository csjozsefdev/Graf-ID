"""Tests for remove-project IPC."""

from __future__ import annotations

from pathlib import Path

from grafid.ipc.project_handlers import handle_add_project, handle_remove_project


def test_remove_project_registry_only(
    db_path, config_manager, tmp_path: Path
) -> None:
    project_dir = tmp_path / "keep-on-disk"
    project_dir.mkdir()
    readme = project_dir / "README.md"
    readme.write_text("stay", encoding="utf-8")

    added = handle_add_project("keep-on-disk", str(project_dir), config_manager=config_manager)
    assert added.ok is True
    project_id = added.data["project"]["id"]

    removed = handle_remove_project(project_id, config_manager)
    assert removed.ok is True
    assert removed.data["project_id"] == project_id
    assert removed.data["project_name"] == "keep-on-disk"

    assert readme.exists()
    assert readme.read_text(encoding="utf-8") == "stay"


def test_remove_project_not_found(config_manager) -> None:
    response = handle_remove_project(99999, config_manager)
    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "project_error"
