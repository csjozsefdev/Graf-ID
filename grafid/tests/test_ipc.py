"""Tests for desktop IPC JSON layer (Milestone 7)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


from grafid.core.constants import SCHEMA_VERSION
from grafid.ipc.envelope import IpcResponse
from grafid.ipc.handlers import handle_bootstrap, handle_health, handle_list_projects


def _parse_stdout(raw: str) -> dict:
    line = next(line for line in raw.splitlines() if line.strip())
    return json.loads(line)


def test_health_handler_ok() -> None:
    response = handle_health()
    assert response.ok is True
    assert response.data is not None
    assert response.data["schema_version"] == SCHEMA_VERSION
    assert "config_dir" in response.data


def test_bootstrap_handler_ok(db_path, config_manager, project_id: int) -> None:
    response = handle_bootstrap(config_manager=config_manager)
    assert response.ok is True
    assert response.data is not None
    assert response.data["schema_version"] == SCHEMA_VERSION
    assert isinstance(response.data["projects"], list)
    assert len(response.data["projects"]) >= 1
    first = response.data["projects"][0]
    assert "git_status" in first
    assert "latest_session" in first
    assert "startup_card" not in response.data


def test_list_projects_handler(db_path, config_manager, project_id: int) -> None:
    response = handle_list_projects(config_manager)
    assert response.ok is True
    assert response.data is not None
    assert any(p["id"] == project_id for p in response.data["projects"])


def test_ipc_envelope_json_roundtrip() -> None:
    payload = IpcResponse(ok=True, data={"hello": "world"})
    encoded = json.dumps(payload.to_dict())
    decoded = json.loads(encoded)
    assert decoded["ok"] is True
    assert decoded["data"]["hello"] == "world"


def test_ipc_cli_health_emits_json() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "grafid.cli.main", "ipc", "health"],
        cwd=repo_root,
        env={**__import__("os").environ, "PYTHONPATH": str(repo_root)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    body = _parse_stdout(result.stdout)
    assert body["ok"] is True
    assert body["data"]["app"] == "graf-id"


def test_desktop_ipc_entry_health_emits_json() -> None:
    """Tauri uses `python -m grafid.ipc` (lightweight entry, not grafid.cli.main)."""
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "grafid.ipc", "health"],
        cwd=repo_root,
        env={**__import__("os").environ, "PYTHONPATH": str(repo_root)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    body = _parse_stdout(result.stdout)
    assert body["ok"] is True
    assert body["data"]["app"] == "graf-id"


def test_ipc_cli_bootstrap_emits_json(db_path, project_id: int) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "grafid.cli.main", "ipc", "bootstrap"],
        cwd=repo_root,
        env={**__import__("os").environ, "PYTHONPATH": str(repo_root)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    body = _parse_stdout(result.stdout)
    assert body["ok"] is True
    assert "projects" in body["data"]
