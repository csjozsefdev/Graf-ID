"""IPC close-session tests."""

from __future__ import annotations

from pathlib import Path

from grafid.ipc.session_handlers import handle_close_session
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.session_service import SessionService


def test_close_session_with_exit_note(db_path, config_manager, tmp_path: Path) -> None:
    project_dir = tmp_path / "sess-proj"
    project_dir.mkdir()
    registry = ProjectRegistryService(db_path)
    record = registry.add("demo", str(project_dir))
    SessionService(db_path).start_session(record.id)

    response = handle_close_session(
        record.id,
        exit_note="Finished auth module",
        next_step="Add tests",
        blocker="Waiting on API keys",
        config_manager=config_manager,
    )
    assert response.ok is True
    panel = response.data["resume_panel"]
    assert panel["exit_note"] == "Finished auth module"
    assert panel["latest_session"]["is_active"] is False
    assert panel["latest_session"]["status"] == "completed"
