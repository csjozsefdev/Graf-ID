"""Tests for reorder-projects IPC."""

from __future__ import annotations

from pathlib import Path

from grafid.ipc.project_handlers import handle_add_project, handle_reorder_projects


def test_reorder_projects_persists_order(
    db_path, config_manager, tmp_path: Path
) -> None:
    dirs = []
    for name in ("alpha", "beta", "gamma"):
        project_dir = tmp_path / name
        project_dir.mkdir()
        dirs.append(project_dir)

    ids = []
    for name, project_dir in zip(("alpha", "beta", "gamma"), dirs, strict=True):
        added = handle_add_project(name, str(project_dir), config_manager=config_manager)
        assert added.ok is True
        ids.append(added.data["project"]["id"])

    reordered = handle_reorder_projects([ids[2], ids[0], ids[1]], config_manager=config_manager)
    assert reordered.ok is True
    returned_ids = [project["id"] for project in reordered.data["projects"]]
    assert returned_ids == [ids[2], ids[0], ids[1]]
    assert all(project.get("sidebar_order") is not None for project in reordered.data["projects"])


def test_reorder_projects_rejects_invalid_ids(config_manager) -> None:
    response = handle_reorder_projects([1, 2, 2], config_manager=config_manager)
    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "validation_error"
