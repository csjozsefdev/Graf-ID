"""IPC stdio encoding — Unicode paths on Windows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


from grafid.ipc.stdio_config import configure_ipc_stdio_utf8


def test_configure_ipc_stdio_utf8_sets_utf8() -> None:
    configure_ipc_stdio_utf8()
    assert sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") == "utf8"


def test_ipc_app_settings_stdout_is_utf8_json() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "PYTHONPATH": str(repo_root),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, "-m", "grafid.cli.main", "ipc", "app-settings"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    line = next(l for l in result.stdout.decode("utf-8").splitlines() if l.strip())
    body = json.loads(line)
    data_dir = body["data"]["data_dir"]
    assert "?" not in data_dir or os.path.isdir(data_dir)
    assert os.path.isdir(data_dir)
