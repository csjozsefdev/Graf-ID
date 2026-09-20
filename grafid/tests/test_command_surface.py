"""Contract: the desktop command surface is consistent across TypeScript, Rust and Python.

Three hand-written layers describe the same commands (the TS client invokes Tauri
commands, lib.rs registers them and spawns `python -m grafid.ipc <name>`, and
grafid.ipc.desktop_entry.COMMANDS is the single Python table). Nothing else
checks that they agree, so this test does.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from grafid.ipc.desktop_entry import COMMANDS, usage

REPO = Path(__file__).resolve().parents[2]
LIB_RS = REPO / "desktop" / "src-tauri" / "src" / "lib.rs"
TS_ROOT = REPO / "desktop" / "src"


def _registered_rust_commands() -> set[str]:
    text = LIB_RS.read_text(encoding="utf-8")
    block = re.search(r"generate_handler!\[(.*?)\]", text, re.S)
    assert block, "generate_handler! not found in lib.rs"
    return {item.strip().split("::")[-1] for item in block.group(1).split(",") if item.strip()}


def _rust_python_calls() -> set[str]:
    return set(re.findall(r'run_ipc\(\s*"([a-z-]+)"', LIB_RS.read_text(encoding="utf-8")))


def _ts_invoked_commands() -> set[str]:
    """Tauri command names: invoke("cmd", ...) and invokeIpc("action label", "cmd", ...)."""
    direct = re.compile(r'\binvoke\s*(?:<[^()]*>)?\s*\(\s*"([a-z_]+)"')
    wrapped = re.compile(r'\binvokeIpc\s*(?:<[^()]*>)?\s*\(\s*"[^"]+"\s*,\s*"([a-z_]+)"')
    invoked: set[str] = set()
    for path in TS_ROOT.rglob("*.ts*"):
        if ".test." in path.name or path.name.endswith(".d.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        invoked.update(direct.findall(text))
        invoked.update(wrapped.findall(text))
    return invoked


def test_every_rust_command_is_used_by_the_frontend() -> None:
    unused = _registered_rust_commands() - _ts_invoked_commands()
    assert not unused, f"registered Tauri commands nothing invokes: {sorted(unused)}"


def test_every_frontend_ipc_command_is_registered_in_rust() -> None:
    registered = _registered_rust_commands()
    invoked = _ts_invoked_commands()
    assert invoked <= registered, f"invoked but not registered: {sorted(invoked - registered)}"


def test_every_rust_backend_call_exists_in_the_python_table() -> None:
    missing = _rust_python_calls() - set(COMMANDS)
    assert not missing, f"lib.rs spawns unknown Python commands: {sorted(missing)}"


def test_every_desktop_wrapper_maps_to_a_python_command() -> None:
    """ipc_foo_bar in Rust must call the Python command `foo-bar` (naming stays mechanical)."""
    text = LIB_RS.read_text(encoding="utf-8")
    for match in re.finditer(r'fn (ipc_[a-z_]+)\(.*?run_ipc\(\s*"([a-z-]+)"', text, re.S):
        function, command = match.groups()
        assert command == function.removeprefix("ipc_").replace("_", "-"), (function, command)


def test_help_lists_every_command_and_terminal_passthrough_uses_the_same_table() -> None:
    assert all(name in usage() for name in COMMANDS)
    result = subprocess.run(
        [sys.executable, "-m", "grafid.cli.main", "ipc", "--help"],
        capture_output=True, text=True, check=False, cwd=REPO,
    )
    assert result.returncode == 0
    assert all(name in result.stdout for name in COMMANDS)


def test_unknown_command_is_a_usage_error() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "grafid.cli.main", "ipc", "no-such-command"],
        capture_output=True, text=True, check=False, cwd=REPO,
    )
    assert result.returncode == 2
