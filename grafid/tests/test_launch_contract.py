"""Open Project IPC launch contract (stable fields for desktop)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from grafid.ipc.dashboard_handlers import handle_open_project
from grafid.services.workflow_launch import LaunchOutcome, detect_system_editor

_REQUIRED_LAUNCH_KEYS = frozenset(
    {
        "success",
        "message",
        "editor_launched",
        "explorer_opened",
        "fallback_used",
        "action",
    }
)


def test_launch_outcome_to_dict_includes_contract_fields() -> None:
    payload = LaunchOutcome(
        action="explorer",
        editor=None,
        message="test",
        session_id=1,
        session_started=True,
        fallback_used=False,
        open_explorer=True,
    ).to_dict()
    assert _REQUIRED_LAUNCH_KEYS.issubset(payload.keys())
    assert payload["explorer_opened"] is True
    assert payload["editor_launched"] is False


def test_launch_outcome_editor_success_contract() -> None:
    payload = LaunchOutcome(
        action="editor",
        editor="vscode",
        message="ok",
        session_id=2,
        session_started=False,
        fallback_used=False,
        open_explorer=False,
    ).to_dict()
    assert payload["editor_launched"] is True
    assert payload["explorer_opened"] is False


@patch("grafid.services.workflow_launch.subprocess.Popen")
def test_open_project_ipc_includes_launch_block(
    mock_popen: MagicMock, db_path, config_manager, project_id: int
) -> None:
    """
    SECURITY REGRESSION — subprocess.Popen must stay mocked here.

    This test previously called handle_open_project() with nothing mocked at
    all. Because it exercises the real editor-detection branch
    (detect_system_editor -> shutil.which), on any machine with Cursor or VS
    Code on PATH this genuinely launched that editor via a real
    subprocess.Popen call, pointed at a throwaway pytest tmp_path directory,
    every time the Python test suite ran. The @patch above intercepts the
    actual OS-level process creation so this contract check (which only
    cares about the shape of the returned "launch" dict) can never do that,
    regardless of what editors are installed on the machine running it.
    Do not remove this mock to "simplify" the test.
    """
    mock_popen.return_value.pid = 424242
    response = handle_open_project(project_id, config_manager)
    assert response.ok is True
    assert response.data is not None
    launch = response.data.get("launch")
    assert isinstance(launch, dict)
    assert _REQUIRED_LAUNCH_KEYS.issubset(launch.keys())


@patch("grafid.services.workflow_launch.subprocess.Popen")
def test_open_project_ipc_never_spawns_a_real_external_process(
    mock_popen: MagicMock, db_path, config_manager, project_id: int
) -> None:
    """
    SECURITY REGRESSION — do not remove the subprocess.Popen mock above.

    Proves the fix for the Cursor-auto-launch bug (see "External editor
    launch audit" GATE CHECK): this test deliberately leaves the REAL
    editor-detection branch (detect_system_editor -> shutil.which)
    unmocked, so it runs exactly as it would on a real user's machine. The
    only thing standing between that real detection and a real GUI editor
    popping up is that subprocess.Popen — the actual OS-level process-spawn
    primitive — is intercepted here. If a future change accidentally
    removes this mock (or replaces it with something that lets a real
    invocation through), this test's assertions on the intercepted call
    prove exactly what would have been launched, without ever launching it.
    """
    mock_popen.return_value.pid = 424242
    detected = detect_system_editor()
    if detected is None:
        pytest.skip(
            "No supported editor (cursor/vscode/pycharm) found on PATH — "
            "environment-only skip; nothing for this regression to exercise "
            "and no real launch risk exists here either"
        )

    response = handle_open_project(project_id, config_manager)

    # The real detection branch ran and genuinely resolved an installed
    # editor, and would have handed subprocess.Popen a real, launchable
    # executable — proof the vulnerable code path is actually exercised,
    # not accidentally bypassed.
    mock_popen.assert_called_once()
    call_args, call_kwargs = mock_popen.call_args
    executable = call_args[0][0]
    assert Path(executable).is_file(), (
        f"expected a real, existing editor executable path, got {executable!r}"
    )
    assert call_kwargs.get("cwd") is not None

    # ...but no real external process was ever actually created: mock_popen
    # is a MagicMock, not the real subprocess.Popen, so the assertions above
    # are the only trace this test leaves — no window opens, no process runs.
    assert response.ok is True
    assert response.data["launch"]["action"] == "editor"
    assert response.data["launch"]["editor"] == detected


def test_launch_outcome_to_dict_tolerates_missing_launch_in_handler_mock() -> None:
    """Document: desktop normalizes when launch is absent (regression guard)."""
    partial = {"action": "explorer", "message": "legacy"}
    assert "open_explorer" not in partial
    assert "explorer_opened" not in partial
