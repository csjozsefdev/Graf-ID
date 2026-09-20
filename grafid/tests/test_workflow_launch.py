"""Tests for workflow launch (editor, Explorer, sessions)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from grafid.config.manager import AppConfig, ConfigManager
from grafid.core.exceptions import ValidationError
from grafid.ipc.dashboard_handlers import handle_open_folder, handle_open_project
from grafid.models.project import ProjectRecord
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.session_service import SessionService
from grafid.services.workflow_launch import (
    LaunchOutcome,
    WorkflowLaunchError,
    WorkflowLaunchService,
    launch_editor,
    normalize_ide_token,
    open_folder_in_explorer,
    resolve_preferred_ide,
)


def test_normalize_ide_token_aliases() -> None:
    assert normalize_ide_token("code") == "vscode"
    assert normalize_ide_token("Cursor") == "cursor"
    assert normalize_ide_token("explorer") == "explorer"
    assert normalize_ide_token(None) is None


def test_normalize_ide_token_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        normalize_ide_token("eclipse")


def test_resolve_preferred_ide_project_over_config(db_path, tmp_path: Path) -> None:
    registry = ProjectRegistryService(db_path)
    dir_a = tmp_path / "proj-a"
    dir_b = tmp_path / "proj-b"
    dir_a.mkdir()
    dir_b.mkdir()
    project_cursor = registry.add("cursor-proj", str(dir_a), preferred_ide="cursor")
    project_default = registry.add("default-proj", str(dir_b))
    config = AppConfig(default_project_opener="vscode")
    assert resolve_preferred_ide(project_cursor, config) == "cursor"
    assert resolve_preferred_ide(project_default, config) == "vscode"


@patch("grafid.services.workflow_launch.subprocess.Popen")
def test_launch_editor_vscode(mock_popen: MagicMock, tmp_path: Path) -> None:
    mock_popen.return_value.pid = 4242
    with patch("grafid.services.workflow_launch.shutil.which", return_value=r"C:\code.exe"):
        pid = launch_editor("vscode", tmp_path)
    mock_popen.assert_called_once()
    assert pid == 4242
    args = mock_popen.call_args[0][0]
    assert "code" in args[0].lower()
    assert args[1] == str(tmp_path.resolve())


# subprocess.CREATE_NO_WINDOW is a real Win32-only stdlib attribute (absent
# on CPython's POSIX build entirely, not just falsy) — patching sys.platform
# doesn't help two ways: the attribute still doesn't exist to reference at
# assertion time, and workflow_launch's own _SUBPROCESS_CREATE_FLAGS is
# computed once at import time from the *real* platform, not re-evaluated
# per call. Genuinely Windows-only; skip cleanly rather than error on Docker/
# Linux (found running the containerized suite for the first time).
_WINDOWS_ONLY_REASON = (
    "subprocess.CREATE_NO_WINDOW does not exist on this platform — "
    "environment-only skip, not an app failure"
)


@pytest.mark.skipif(sys.platform != "win32", reason=_WINDOWS_ONLY_REASON)
@patch("grafid.services.workflow_launch.subprocess.Popen")
def test_launch_editor_uses_hidden_console_on_windows(
    mock_popen: MagicMock, tmp_path: Path
) -> None:
    import subprocess

    mock_popen.return_value.pid = 4242
    with patch("grafid.services.workflow_launch.shutil.which", return_value=r"C:\code.exe"):
        with patch("grafid.services.workflow_launch.sys.platform", "win32"):
            launch_editor("vscode", tmp_path)
    assert mock_popen.call_args.kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW


@pytest.mark.skipif(sys.platform != "win32", reason=_WINDOWS_ONLY_REASON)
@patch("grafid.services.workflow_launch.subprocess.Popen")
def test_open_folder_in_explorer_windows(mock_popen: MagicMock, tmp_path: Path) -> None:
    import subprocess

    with patch("grafid.services.workflow_launch.sys.platform", "win32"):
        open_folder_in_explorer(tmp_path)
    mock_popen.assert_called_once()
    args = mock_popen.call_args[0][0]
    assert args[0] == "explorer"
    assert mock_popen.call_args.kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW


@patch("grafid.services.workflow_launch.launch_editor")
@patch("grafid.services.workflow_launch.open_folder_in_explorer")
def test_open_project_launches_editor(
    mock_explorer: MagicMock,
    mock_editor: MagicMock,
    db_path,
    project_id: int,
) -> None:
    registry = ProjectRegistryService(db_path)
    record = registry.get_info(str(project_id))
    launcher = WorkflowLaunchService(db_path, registry)
    config = AppConfig(default_project_opener="vscode")

    with patch.object(registry, "open_project", return_value=record):
        with patch.object(launcher._sessions, "get_active_session", return_value=None):
            with patch.object(
                launcher._sessions,
                "start_session",
                return_value=MagicMock(id=99),
            ):
                _, outcome = launcher.open_project(project_id, config=config)

    mock_editor.assert_called_once()
    mock_explorer.assert_not_called()
    assert outcome.action == "editor"
    assert outcome.session_started is True
    assert outcome.open_explorer is False


@patch("grafid.services.workflow_launch.launch_editor", side_effect=WorkflowLaunchError("missing"))
@patch("grafid.services.workflow_launch.open_folder_in_explorer")
def test_open_project_falls_back_to_explorer(
    mock_explorer: MagicMock,
    mock_editor: MagicMock,
    db_path,
    project_id: int,
) -> None:
    registry = ProjectRegistryService(db_path)
    record = registry.get_info(str(project_id))
    launcher = WorkflowLaunchService(db_path, registry)
    config = AppConfig(default_project_opener="cursor")

    with patch.object(registry, "open_project", return_value=record):
        with patch.object(launcher._sessions, "get_active_session", return_value=MagicMock(id=1)):
            _, outcome = launcher.open_project(project_id, config=config)

    mock_explorer.assert_called_once()
    assert outcome.fallback_used is True
    assert outcome.action == "explorer"
    assert outcome.open_explorer is False


def test_open_project_invalid_path_fails(db_path, project_id: int) -> None:
    registry = ProjectRegistryService(db_path)
    record = registry.get_info(str(project_id))
    broken = ProjectRecord(
        id=record.id,
        name=record.name,
        path=str(db_path / "missing-folder-xyz"),
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_opened_at=record.last_opened_at,
        preferred_ide=record.preferred_ide,
        is_active=record.is_active,
        category=record.category,
        status=record.status,
        notes=record.notes,
        last_refreshed_at=record.last_refreshed_at,
    )
    launcher = WorkflowLaunchService(db_path, registry)

    with patch.object(registry, "open_project", return_value=broken):
        with pytest.raises(WorkflowLaunchError):
            launcher.open_project(project_id, config=AppConfig())


@patch("grafid.services.workflow_launch.open_folder_in_explorer")
def test_handle_open_folder_ipc(
    mock_explorer: MagicMock,
    config_manager: ConfigManager,
    project_id: int,
) -> None:
    response = handle_open_folder(project_id, config_manager)
    assert response.ok is True
    assert response.data is not None
    assert "message" in response.data
    mock_explorer.assert_called_once()


@patch("grafid.ipc.dashboard_handlers.WorkflowLaunchService.open_project")
def test_handle_open_project_ipc(
    mock_open: MagicMock,
    db_path,
    config_manager: ConfigManager,
    project_id: int,
) -> None:
    registry = ProjectRegistryService(db_path)
    record = registry.get_info(str(project_id))
    mock_open.return_value = (
        record,
        LaunchOutcome(
            action="editor",
            editor="vscode",
            message="ok",
            session_id=1,
            session_started=True,
            fallback_used=False,
            open_explorer=False,
        ),
    )
    response = handle_open_project(project_id, config_manager)
    assert response.ok is True
    assert response.data["launch"]["action"] == "editor"


@patch("grafid.services.workflow_launch.open_folder_in_explorer")
def test_repeated_open_reuses_session(
    mock_explorer: MagicMock,
    db_path,
    project_id: int,
) -> None:
    registry = ProjectRegistryService(db_path)
    sessions = SessionService(db_path)
    launcher = WorkflowLaunchService(db_path, registry)
    config = AppConfig(extra={"preferred_ide": "explorer"})

    launcher.open_project(project_id, config=config)
    active = sessions.get_active_session(project_id)
    assert active is not None
    first_id = active.id

    launcher.open_project(project_id, config=config)
    active_again = sessions.get_active_session(project_id)
    assert active_again is not None
    assert active_again.id == first_id
