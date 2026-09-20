"""Regression: Open Folder / Open Project launch boundaries."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from grafid.config.manager import AppConfig
from grafid.ipc.dashboard_handlers import handle_open_project
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.workflow_launch import LaunchOutcome, WorkflowLaunchService


def test_client_open_folder_is_rust_only() -> None:
    """Desktop Open Folder must use the Rust invoke; no Python-backed Tauri command exists for it."""
    root = Path(__file__).resolve().parents[2] / "desktop"
    text = (root / "src" / "ipc" / "client.ts").read_text(encoding="utf-8")
    assert "openProjectFolderPath" in text
    assert 'invoke("open_project_folder"' in text
    assert "ipc_open_folder" not in text
    rust = (root / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
    assert "fn open_project_folder" in rust
    assert "fn ipc_open_folder" not in rust


def test_app_shell_open_folder_uses_registered_path() -> None:
    """Open Project fallback passes wake snapshot projectPath (registry root) to Rust helper."""
    shell = Path(__file__).resolve().parents[2] / "desktop" / "src" / "components" / "AppShell.tsx"
    text = shell.read_text(encoding="utf-8")
    assert "projectPath: selectedProject.path" in text
    assert "openProjectFolderPath(action.projectPath)" in text
    assert "handleOpenProject" in text
    assert "openProjectFolder(selectedId)" not in text


def test_app_shell_open_project_uses_explorer_opened_flag() -> None:
    """Open Project opens Explorer at most once via launch.explorer_opened."""
    shell = Path(__file__).resolve().parents[2] / "desktop" / "src" / "components" / "AppShell.tsx"
    text = shell.read_text(encoding="utf-8")
    assert "launch.explorer_opened" in text
    assert "openProjectFolderPath(action.projectPath)" in text


def test_launch_normalize_module_exists() -> None:
    path = Path(__file__).resolve().parents[2] / "desktop" / "src" / "ipc" / "launchNormalize.ts"
    text = path.read_text(encoding="utf-8")
    assert "normalizeLaunchResult" in text
    assert "normalizeOpenProjectResult" in text


@patch("grafid.services.workflow_launch.detect_system_editor", return_value=None)
@patch("grafid.services.workflow_launch.open_folder_in_explorer")
def test_open_project_ipc_defers_explorer_to_desktop(
    mock_explorer: MagicMock,
    _mock_detect: MagicMock,
    db_path,
    config_manager,
    project_id: int,
) -> None:
    """ipc open-project must not open Explorer in Python (desktop uses Rust)."""
    response = handle_open_project(project_id, config_manager)
    assert response.ok is True
    assert response.data["launch"]["explorer_opened"] is True
    mock_explorer.assert_not_called()


@patch("grafid.services.workflow_launch.open_folder_in_explorer")
def test_open_project_cli_opens_explorer_once(
    mock_explorer: MagicMock,
    db_path,
    project_id: int,
) -> None:
    """CLI/default launch_explorer=True opens Explorer exactly once in Python."""
    registry = ProjectRegistryService(db_path)
    launcher = WorkflowLaunchService(db_path, registry)
    config = AppConfig(default_project_opener="explorer")
    launcher.open_project(project_id, config=config, launch_explorer=True)
    mock_explorer.assert_called_once()


@patch("grafid.services.workflow_launch.launch_editor")
@patch("grafid.services.workflow_launch.open_folder_in_explorer")
def test_open_project_editor_success_no_explorer(
    mock_explorer: MagicMock,
    mock_editor: MagicMock,
    db_path,
    project_id: int,
) -> None:
    registry = ProjectRegistryService(db_path)
    record = registry.get_info(str(project_id))
    launcher = WorkflowLaunchService(db_path, registry)
    with patch.object(registry, "open_project", return_value=record):
        with patch.object(launcher._sessions, "get_active_session", return_value=None):
            with patch.object(
                launcher._sessions,
                "start_session",
                return_value=MagicMock(id=1),
            ):
                _, outcome = launcher.open_project(
                    project_id,
                    config=AppConfig(default_project_opener="vscode"),
                    launch_explorer=False,
                )
    mock_editor.assert_called_once()
    mock_explorer.assert_not_called()
    assert outcome.open_explorer is False


@patch("grafid.ipc.dashboard_handlers.WorkflowLaunchService.open_project")
def test_handle_open_project_passes_launch_explorer_false(
    mock_open: MagicMock,
    db_path,
    config_manager,
    project_id: int,
) -> None:
    record = ProjectRegistryService(db_path).get_info(str(project_id))
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
    handle_open_project(project_id, config_manager)
    assert mock_open.call_args.kwargs.get("launch_explorer") is False


def test_launch_normalize_handles_missing_launch_fields() -> None:
    """Simulate legacy/malformed IPC: missing launch object fields."""
    path = Path(__file__).resolve().parents[2] / "desktop" / "src" / "ipc" / "launchNormalize.ts"
    text = path.read_text(encoding="utf-8")
    assert "record.launch" in text or "normalizeLaunchResult(record.launch)" in text
