"""Tests for dashboard IPC (Milestone 8)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.resume_repository import ResumeRepository
from grafid.ipc.dashboard_handlers import (
    handle_dashboard,
    handle_open_project,
    handle_project_detail,
    handle_project_history,
    handle_refresh_resume,
)
from grafid.services.snapshot_persistence import SnapshotPersistenceService
from grafid.scanner.models import ScanResult


def test_dashboard_lists_enriched_project(db_path, config_manager, project_id: int) -> None:
    response = handle_dashboard(config_manager)
    assert response.ok is True
    assert response.data is not None
    row = next(p for p in response.data["projects"] if p["id"] == project_id)
    assert row["name"] == "test-project"
    assert "git_status" in row
    assert row["git_status"]["state"] in ("unknown", "not_repo", "clean", "dirty")
    assert "latest_session" in row


def test_dashboard_builds_summary_fresh_not_from_stored_text(
    db_path, config_manager, project_id: int
) -> None:
    with DatabaseConnection(db_path) as conn:
        ResumeRepository(conn).insert(
            project_id=project_id,
            session_id=None,
            snapshot_id=None,
            mode="short",
            summary_body="Old stored resume headline\nMore resume detail",
        )
        conn.commit()

    panel = handle_project_detail(project_id, config_manager).data["resume_panel"]
    assert panel["startup_summary"]["source"] == "summary_engine"
    assert "Old stored resume headline" not in panel["startup_summary"]["headline"]

    row = next(
        p for p in handle_dashboard(config_manager).data["projects"] if p["id"] == project_id
    )
    assert row["summary_preview"]["source"] == "summary_engine"


def test_refresh_resume_updates_stored_summary(
    db_path, config_manager, project_id: int
) -> None:
    from grafid.services.resume_service import ResumeService

    ResumeService(db_path).generate_resume(project_id, mode="short", persist=True)
    before = handle_project_detail(project_id, config_manager).data["resume_panel"]
    ResumeService(db_path).generate_resume(project_id, mode="short", persist=True)
    response = handle_refresh_resume(project_id, config_manager)
    assert response.ok is True
    after = response.data["resume_panel"]
    assert after["has_stored_resume"] is True
    assert after["startup_summary"] is not None
    assert before is not None


def test_project_detail_includes_resume_panel(db_path, config_manager, project_id: int) -> None:
    response = handle_project_detail(project_id, config_manager)
    assert response.ok is True
    assert response.data is not None
    assert response.data["project"]["id"] == project_id
    panel = response.data["resume_panel"]
    assert "blocker" in panel
    assert "modified_files" in panel
    assert "git_status" in panel
    assert "latest_session" in panel
    assert "open_task_count" in panel
    assert "latest_scan_at" in panel
    project = response.data["project"]
    assert project["open_task_count"] is None or isinstance(project["open_task_count"], int)


def test_project_history_after_scan(db_path, config_manager, project_id: int) -> None:
    SnapshotPersistenceService(db_path).save_snapshot(
        project_id, ScanResult(project_name="test", project_path="/tmp")
    )
    response = handle_project_history(project_id, config_manager=config_manager)
    assert response.ok is True
    assert len(response.data["history"]) >= 1


def test_open_project_returns_enriched_dashboard_project(
    db_path, config_manager, project_id: int
) -> None:
    from unittest.mock import patch

    from grafid.services.project_registry import ProjectRegistryService
    from grafid.services.workflow_launch import LaunchOutcome

    opened = ProjectRegistryService(db_path).open_project(str(project_id))

    with patch("grafid.ipc.dashboard_handlers.WorkflowLaunchService.open_project") as mock_open:
        mock_open.return_value = (
            opened,
            LaunchOutcome(
                action="editor",
                editor="cursor",
                message="Opened",
                session_id=1,
                session_started=False,
                fallback_used=False,
                open_explorer=False,
            ),
        )
        response = handle_open_project(project_id, config_manager)

    assert response.ok is True
    project = response.data["project"]
    assert "git_status" in project
    assert project["git_status"]["state"] in ("unknown", "not_repo", "clean", "dirty")
    assert "latest_session" in project


@patch("grafid.ipc.dashboard_handlers.WorkflowLaunchService.open_project")
def test_open_project_returns_launch_payload(
    mock_open,
    db_path,
    config_manager,
    project_id: int,
) -> None:
    from grafid.services.project_registry import ProjectRegistryService
    from grafid.services.workflow_launch import LaunchOutcome

    opened = ProjectRegistryService(db_path).open_project(str(project_id))
    mock_open.return_value = (
        opened,
        LaunchOutcome(
            action="explorer",
            editor=None,
            message="Opened folder",
            session_id=1,
            session_started=True,
            fallback_used=False,
            open_explorer=True,
        ),
    )
    response = handle_open_project(project_id, config_manager)
    assert response.ok is True
    assert response.data["project"]["last_opened_at"] is not None
    assert response.data["launch"]["action"] == "explorer"


def test_ipc_cli_dashboard_emits_json(db_path, config_manager, project_id: int) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "grafid.cli.main", "ipc", "dashboard"],
        cwd=repo_root,
        env={**__import__("os").environ, "PYTHONPATH": str(repo_root)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    line = next(l for l in result.stdout.splitlines() if l.strip())
    body = json.loads(line)
    assert body["ok"] is True
    assert "projects" in body["data"]
