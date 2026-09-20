"""IPC update-project tests."""

from __future__ import annotations

from pathlib import Path


from grafid.ipc.project_handlers import handle_update_project
from grafid.services.project_registry import ProjectRegistryService


def test_update_project_status(db_path, config_manager, tmp_path: Path) -> None:
    project_dir = tmp_path / "demo-proj"
    project_dir.mkdir()
    registry = ProjectRegistryService(db_path)
    record = registry.add("demo", str(project_dir))
    response = handle_update_project(
        record.id,
        status="paused",
        notes="Side project on hold",
        config_manager=config_manager,
    )
    assert response.ok is True
    assert response.data["project"]["status"] == "paused"
    assert response.data["project"]["notes"] == "Side project on hold"


def test_update_project_rename(db_path, config_manager, tmp_path: Path) -> None:
    project_dir = tmp_path / "demo2-proj"
    project_dir.mkdir()
    registry = ProjectRegistryService(db_path)
    record = registry.add("demo2", str(project_dir))
    response = handle_update_project(
        record.id, name="demo-renamed", config_manager=config_manager
    )
    assert response.ok is True
    assert response.data["project"]["name"] == "demo-renamed"
