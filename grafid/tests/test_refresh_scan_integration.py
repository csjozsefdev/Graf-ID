"""Refresh context runs scan and updates task markers."""

from __future__ import annotations

from pathlib import Path

from grafid.ipc.dashboard_handlers import handle_refresh_resume
from grafid.services.project_registry import ProjectRegistryService


def test_refresh_resume_updates_scan_context(
    db_path, config_manager, tmp_path: Path
) -> None:
    project_dir = tmp_path / "scan-proj"
    project_dir.mkdir()
    registry = ProjectRegistryService(db_path)
    record = registry.add("scan-demo", str(project_dir))
    sample = project_dir / "sample.py"
    sample.write_text("# TODO: wire refresh scan\n", encoding="utf-8")

    response = handle_refresh_resume(record.id, config_manager=config_manager)
    assert response.ok is True
    project = response.data["project"]
    assert project.get("last_refreshed_at") is not None
    assert project.get("latest_scan_at") is not None
    assert project.get("open_task_count", 0) >= 1
