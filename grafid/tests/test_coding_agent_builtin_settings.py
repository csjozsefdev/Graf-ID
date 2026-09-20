"""Built-in Coding Agent presets are removable/restorable and accept an
explicit executable override (PATH detection stays the default).

Every spawn is guarded: nothing in this module may start a real process.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from grafid.config import coding_agents as agents_mod
from grafid.config.coding_agents import (
    BuiltinAgentSettings,
    CodingAgentConfig,
    find_agent,
    merged_agent_list,
    parse_builtin_agent_settings,
    removed_builtin_agents,
    validate_builtin_agent_settings_payload,
)
from grafid.config.manager import ConfigManager
from grafid.core.exceptions import ConfigError
from grafid.ipc import desktop_entry
from grafid.ipc.coding_agent_handlers import handle_resolve_coding_agent_launch
from grafid.ipc.settings_handlers import (
    handle_get_app_settings,
    handle_reset_app_settings,
    handle_save_app_settings,
)
from grafid.services.coding_agent_launch import CodingAgentError, resolve_coding_agent_launch
from grafid.services.portability import _sanitized_config_json
from grafid.services.project_registry import ProjectRegistryService


@pytest.fixture(autouse=True)
def _no_real_process_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test tried to spawn a real process")

    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "run", boom)


def _fake_exe(tmp_path: Path, name: str = "tool.cmd") -> Path:
    exe = tmp_path / name
    exe.write_text("@echo off\n", encoding="utf-8")
    return exe


def _which_returning(mapping: dict[str, str]):
    return lambda cmd: mapping.get(cmd)


def _by_id(entries: list[dict], agent_id: str) -> dict:
    return next(e for e in entries if e["id"] == agent_id)


# ---------------------------------------------------------------------------
# PATH detection stays the default (no install-location heuristics)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("agent_id", "command"), [("claude-code", "claude"), ("codex-cli", "codex")]
)
def test_preset_detected_on_path_without_override(
    agent_id: str, command: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    found = _fake_exe(tmp_path, f"{command}.cmd")
    monkeypatch.setattr(agents_mod.shutil, "which", _which_returning({command: str(found)}))

    entry = _by_id(merged_agent_list([]), agent_id)
    assert entry["available"] is True
    assert entry["executable_override"] is None

    spec = resolve_coding_agent_launch(agent_id, str(tmp_path), custom_agents=[])
    assert Path(spec.executable) == found.resolve()


@pytest.mark.parametrize("agent_id", ["claude-code", "codex-cli"])
def test_preset_not_found_when_neither_override_nor_path(
    agent_id: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(agents_mod.shutil, "which", lambda cmd: None)
    entry = _by_id(merged_agent_list([]), agent_id)
    assert entry["available"] is False
    with pytest.raises(CodingAgentError, match="PATH"):
        resolve_coding_agent_launch(agent_id, str(tmp_path), custom_agents=[])


# ---------------------------------------------------------------------------
# Explicit executable override
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent_id", ["claude-code", "codex-cli"])
def test_preset_explicit_override_is_used_even_when_not_on_path(
    agent_id: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(agents_mod.shutil, "which", lambda cmd: None)
    exe = _fake_exe(tmp_path)
    settings = {agent_id: BuiltinAgentSettings(executable=str(exe), args=("--flag", "a b"))}

    entry = _by_id(merged_agent_list([], settings), agent_id)
    assert entry["available"] is True
    assert entry["executable_override"] == str(exe)
    assert entry["args"] == ["--flag", "a b"]

    spec = resolve_coding_agent_launch(
        agent_id, str(tmp_path), custom_agents=[], builtin_settings=settings
    )
    assert Path(spec.executable) == exe.resolve()
    assert spec.args == ("--flag", "a b")


def test_override_takes_precedence_over_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    on_path = _fake_exe(tmp_path, "claude.cmd")
    override_dir = tmp_path / "custom"
    override_dir.mkdir()
    override = _fake_exe(override_dir, "my-claude.cmd")
    monkeypatch.setattr(agents_mod.shutil, "which", _which_returning({"claude": str(on_path)}))

    settings = {"claude-code": BuiltinAgentSettings(executable=str(override))}
    spec = resolve_coding_agent_launch(
        "claude-code", str(tmp_path), custom_agents=[], builtin_settings=settings
    )
    assert Path(spec.executable) == override.resolve()
    assert Path(spec.executable) != on_path.resolve()


def test_invalid_override_never_silently_falls_back_to_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    on_path = _fake_exe(tmp_path, "claude.cmd")
    monkeypatch.setattr(agents_mod.shutil, "which", _which_returning({"claude": str(on_path)}))
    settings = {"claude-code": BuiltinAgentSettings(executable=str(tmp_path / "gone.cmd"))}

    entry = _by_id(merged_agent_list([], settings), "claude-code")
    assert entry["available"] is False
    assert "does not exist" in entry["unavailable_reason"]

    with pytest.raises(CodingAgentError, match="does not exist"):
        resolve_coding_agent_launch(
            "claude-code", str(tmp_path), custom_agents=[], builtin_settings=settings
        )


def test_override_that_is_a_bare_command_is_looked_up_on_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    beta = _fake_exe(tmp_path, "claude-beta.cmd")
    monkeypatch.setattr(agents_mod.shutil, "which", _which_returning({"claude-beta": str(beta)}))
    settings = {"claude-code": BuiltinAgentSettings(executable="claude-beta")}
    spec = resolve_coding_agent_launch(
        "claude-code", str(tmp_path), custom_agents=[], builtin_settings=settings
    )
    assert Path(spec.executable) == beta.resolve()


# ---------------------------------------------------------------------------
# Save-time validation of an explicit override
# ---------------------------------------------------------------------------


def test_save_rejects_override_path_that_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Claude Code.*does not exist"):
        validate_builtin_agent_settings_payload(
            {"claude-code": {"executable": str(tmp_path / "nope.cmd")}}
        )


def test_save_rejects_override_that_is_a_directory(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    with pytest.raises(ConfigError, match="directory"):
        validate_builtin_agent_settings_payload({"codex-cli": {"executable": str(folder)}})


def test_save_rejects_override_that_windows_cannot_launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(agents_mod, "_is_windows", lambda: True)
    script = _fake_exe(tmp_path, "tool.ps1")
    with pytest.raises(ConfigError, match=r"\.exe, \.cmd, \.bat or \.com"):
        validate_builtin_agent_settings_payload({"claude-code": {"executable": str(script)}})
    ok = _fake_exe(tmp_path, "tool.exe")
    assert validate_builtin_agent_settings_payload(
        {"claude-code": {"executable": str(ok)}}
    )["claude-code"].executable == str(ok)


def test_save_rejects_unknown_preset_and_bad_shapes() -> None:
    with pytest.raises(ConfigError, match="Unknown built-in"):
        validate_builtin_agent_settings_payload({"grok-cli": {"hidden": True}})
    with pytest.raises(ConfigError):
        validate_builtin_agent_settings_payload(["claude-code"])
    with pytest.raises(ConfigError):
        validate_builtin_agent_settings_payload({"claude-code": {"hidden": "yes"}})
    with pytest.raises(ConfigError):
        validate_builtin_agent_settings_payload({"claude-code": {"args": "--x"}})


def test_hidden_preset_drops_any_stale_override(tmp_path: Path) -> None:
    result = validate_builtin_agent_settings_payload(
        {"claude-code": {"hidden": True, "executable": str(tmp_path / "stale.cmd")}}
    )
    assert result["claude-code"] == BuiltinAgentSettings(hidden=True)


def test_empty_override_means_default_and_is_not_stored() -> None:
    assert validate_builtin_agent_settings_payload({"claude-code": {"executable": "  "}}) == {}


def test_load_path_fails_open_on_malformed_or_unknown_entries() -> None:
    parsed = parse_builtin_agent_settings(
        {
            "claude-code": {"hidden": True},
            "codex-cli": {"executable": 42},
            "grok-cli": {"hidden": True},
            "bogus": "x",
        }
    )
    assert parsed == {"claude-code": BuiltinAgentSettings(hidden=True)}
    assert parse_builtin_agent_settings("garbage") == {}
    assert parse_builtin_agent_settings(None) == {}


# ---------------------------------------------------------------------------
# Remove / restore through the settings IPC
# ---------------------------------------------------------------------------


def _save(manager: ConfigManager, opener: str = "system", **kwargs: object):
    return handle_save_app_settings(opener, False, False, config_manager=manager, **kwargs)


def test_removing_a_preset_hides_it_but_keeps_it_restorable(config_manager: ConfigManager) -> None:
    response = _save(config_manager, builtin_agents=json.dumps({"claude-code": {"hidden": True}}))
    assert response.ok is True
    ids = [a["id"] for a in response.data["coding_agents"]]
    assert "claude-code" not in ids and "codex-cli" in ids
    removed = [a["id"] for a in response.data["removed_builtin_agents"]]
    assert removed == ["claude-code"]
    assert config_manager.load().builtin_agents == {"claude-code": BuiltinAgentSettings(hidden=True)}

    # The removal survives an unrelated save that does not send builtin_agents.
    again = _save(config_manager, opener="cursor")
    assert "claude-code" not in [a["id"] for a in again.data["coding_agents"]]


def test_restoring_a_preset_brings_it_back_with_default_detection(
    config_manager: ConfigManager,
) -> None:
    _save(config_manager, builtin_agents=json.dumps({"claude-code": {"hidden": True}}))
    response = _save(config_manager, builtin_agents=json.dumps({}))
    ids = [a["id"] for a in response.data["coding_agents"]]
    assert ids[:2] == ["claude-code", "codex-cli"]
    assert response.data["removed_builtin_agents"] == []
    assert config_manager.load().builtin_agents == {}


def test_both_presets_can_be_removed_leaving_only_custom_agents(
    config_manager: ConfigManager,
) -> None:
    response = _save(
        config_manager,
        coding_agents=json.dumps([{"display_name": "Mine", "executable": "mine"}]),
        builtin_agents=json.dumps(
            {"claude-code": {"hidden": True}, "codex-cli": {"hidden": True}}
        ),
    )
    assert [a["display_name"] for a in response.data["coding_agents"]] == ["Mine"]
    assert len(response.data["removed_builtin_agents"]) == 2


def test_removed_preset_is_gone_from_the_offered_list_and_cannot_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agents_mod.shutil, "which", _which_returning({"claude": "C:/x/claude.cmd"}))
    settings = {"claude-code": BuiltinAgentSettings(hidden=True)}
    assert "claude-code" not in [a["id"] for a in merged_agent_list([], settings)]
    assert [a["id"] for a in removed_builtin_agents(settings)] == ["claude-code"]
    assert find_agent("claude-code", [], settings) is None
    with pytest.raises(CodingAgentError, match="not configured"):
        resolve_coding_agent_launch(
            "claude-code", str(tmp_path), custom_agents=[], builtin_settings=settings
        )


def test_override_is_saved_reported_and_survives_reload(
    config_manager: ConfigManager, tmp_path: Path
) -> None:
    exe = _fake_exe(tmp_path)
    response = _save(
        config_manager,
        builtin_agents=json.dumps({"codex-cli": {"executable": str(exe), "args": ["--x"]}}),
    )
    assert response.ok is True
    entry = _by_id(response.data["coding_agents"], "codex-cli")
    assert entry["executable_override"] == str(exe)
    assert entry["available"] is True
    assert config_manager.load().builtin_agents["codex-cli"].executable == str(exe)


def test_save_with_invalid_override_is_rejected_and_config_is_untouched(
    config_manager: ConfigManager, tmp_path: Path
) -> None:
    before = _save(config_manager, opener="cursor")
    assert before.ok
    response = _save(
        config_manager,
        opener="vscode",
        builtin_agents=json.dumps({"claude-code": {"executable": str(tmp_path / "nope.exe")}}),
    )
    assert response.ok is False
    assert config_manager.load().default_project_opener == "cursor"


def test_reset_restores_presets_and_drops_custom_agents(config_manager: ConfigManager) -> None:
    _save(
        config_manager,
        coding_agents=json.dumps([{"display_name": "Mine", "executable": "mine"}]),
        builtin_agents=json.dumps({"claude-code": {"hidden": True}}),
    )
    response = handle_reset_app_settings(config_manager)
    assert [a["id"] for a in response.data["coding_agents"]] == ["claude-code", "codex-cli"]
    assert response.data["removed_builtin_agents"] == []


# ---------------------------------------------------------------------------
# No dangling opener references after removal
# ---------------------------------------------------------------------------


def test_removing_the_preset_used_as_default_falls_back_to_auto_detect_with_notice(
    config_manager: ConfigManager,
) -> None:
    assert _save(config_manager, opener="agent:claude-code").ok
    assert config_manager.load().default_project_opener == "agent:claude-code"

    response = _save(
        config_manager,
        opener="agent:claude-code",
        builtin_agents=json.dumps({"claude-code": {"hidden": True}}),
    )
    assert response.ok is True
    assert response.data["default_project_opener"] == "system"
    assert config_manager.load().default_project_opener == "system"
    assert "Auto Detect" in response.data["message"]
    assert "Claude Code" in response.data["message"]


def test_removing_a_custom_agent_used_as_default_also_falls_back(
    config_manager: ConfigManager,
) -> None:
    saved = _save(
        config_manager, coding_agents=json.dumps([{"display_name": "Mine", "executable": "mine"}])
    )
    custom_id = _by_id(saved.data["coding_agents"], "mine")["id"]
    _save(config_manager, opener=f"agent:{custom_id}")
    response = _save(config_manager, opener=f"agent:{custom_id}", coding_agents=json.dumps([]))
    assert response.data["default_project_opener"] == "system"


def test_default_opener_naming_an_unknown_agent_is_never_stored(
    config_manager: ConfigManager,
) -> None:
    response = _save(config_manager, opener="agent:never-existed")
    assert response.data["default_project_opener"] == "system"


def _registry_for(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProjectRegistryService:
    registry = ProjectRegistryService(db_path)
    monkeypatch.setattr(
        "grafid.services.runtime.prepare_runtime",
        lambda manager=None: SimpleNamespace(registry=registry, database_path=db_path),
    )
    return registry


def _set_project_opener(db_path: Path, project_id: int, value: str) -> None:
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE projects SET preferred_ide = ? WHERE id = ?", (value, project_id))
    conn.commit()
    conn.close()


def test_removing_a_preset_resets_project_specific_openers_that_used_it(
    config_manager: ConfigManager, project_id: int, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry_for(db_path, monkeypatch)
    _set_project_opener(db_path, project_id, "agent:claude-code")
    assert registry.get_info(str(project_id)).preferred_ide == "agent:claude-code"

    response = _save(config_manager, builtin_agents=json.dumps({"claude-code": {"hidden": True}}))

    assert registry.get_info(str(project_id)).preferred_ide is None
    assert "test-project" in response.data["message"]


def test_removing_an_agent_leaves_other_project_openers_alone(
    config_manager: ConfigManager, project_id: int, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry_for(db_path, monkeypatch)
    _set_project_opener(db_path, project_id, "agent:codex-cli")
    _save(config_manager, builtin_agents=json.dumps({"claude-code": {"hidden": True}}))
    assert registry.get_info(str(project_id)).preferred_ide == "agent:codex-cli"


def test_removing_a_custom_agent_resets_project_openers_that_used_it(
    config_manager: ConfigManager, project_id: int, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry_for(db_path, monkeypatch)
    saved = _save(
        config_manager, coding_agents=json.dumps([{"display_name": "Mine", "executable": "mine"}])
    )
    custom_id = _by_id(saved.data["coding_agents"], "mine")["id"]
    _set_project_opener(db_path, project_id, f"agent:{custom_id}")

    _save(config_manager, coding_agents=json.dumps([]))
    assert registry.get_info(str(project_id)).preferred_ide is None


def test_project_opener_cleanup_failure_never_fails_the_settings_save(
    config_manager: ConfigManager,
) -> None:
    with patch("grafid.services.runtime.prepare_runtime", side_effect=RuntimeError("db down")):
        response = _save(
            config_manager, builtin_agents=json.dumps({"claude-code": {"hidden": True}})
        )
    assert response.ok is True
    assert "Could not reset project openers" in response.data["message"]


# ---------------------------------------------------------------------------
# Custom agents unchanged; session behavior unchanged
# ---------------------------------------------------------------------------


def test_custom_agents_are_unaffected_by_builtin_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exe = _fake_exe(tmp_path, "mine.cmd")
    custom = CodingAgentConfig(id="mine", display_name="Mine", executable=str(exe), args=("-x",))
    settings = {
        "claude-code": BuiltinAgentSettings(hidden=True),
        "codex-cli": BuiltinAgentSettings(executable=str(exe)),
    }
    entries = merged_agent_list([custom], settings)
    mine = _by_id(entries, "mine")
    assert mine["built_in"] is False and mine["available"] is True
    assert mine["executable"] == str(exe) and mine["args"] == ["-x"]
    spec = resolve_coding_agent_launch(
        "mine", str(tmp_path), custom_agents=[custom], builtin_settings=settings
    )
    assert Path(spec.executable) == exe.resolve() and spec.args == ("-x",)


def test_launching_a_preset_with_override_never_touches_sessions(tmp_path: Path) -> None:
    exe = _fake_exe(tmp_path)
    settings = {"claude-code": BuiltinAgentSettings(executable=str(exe))}
    with patch("grafid.services.session_service.SessionService") as sessions:
        resolve_coding_agent_launch(
            "claude-code", str(tmp_path), custom_agents=[], builtin_settings=settings
        )
        sessions.assert_not_called()


def test_resolve_handler_honors_saved_builtin_settings(
    config_manager: ConfigManager, project_id: int, db_path: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _registry_for(db_path, monkeypatch)
    exe = _fake_exe(tmp_path)
    _save(config_manager, builtin_agents=json.dumps({"claude-code": {"executable": str(exe)}}))
    ok = handle_resolve_coding_agent_launch("claude-code", project_id, config_manager)
    assert ok.ok is True and Path(ok.data["executable"]) == exe.resolve()
    assert "session_id" not in ok.data

    _save(config_manager, builtin_agents=json.dumps({"claude-code": {"hidden": True}}))
    gone = handle_resolve_coding_agent_launch("claude-code", project_id, config_manager)
    assert gone.ok is False


# ---------------------------------------------------------------------------
# The real desktop IPC entry (python -m grafid.ipc) exposes all of this
# ---------------------------------------------------------------------------


def test_desktop_entry_saves_agents_and_presets(
    temp_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GRAFID_DATA_DIR", str(temp_config_dir))
    response = desktop_entry.dispatch(
        "save-app-settings",
        [
            "--opener", "system",
            "--coding-agents", json.dumps([{"display_name": "Mine", "executable": "mine"}]),
            "--builtin-agents", json.dumps({"codex-cli": {"hidden": True}}),
        ],
    )
    assert response.ok is True, response
    names = [a["display_name"] for a in response.data["coding_agents"]]
    assert names == ["Claude Code", "Mine"]
    assert [a["id"] for a in response.data["removed_builtin_agents"]] == ["codex-cli"]


def test_desktop_entry_knows_the_resolve_coding_agent_launch_command(
    temp_config_dir: Path, project_id: int, db_path: Path, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert "resolve-coding-agent-launch" in desktop_entry.COMMANDS
    monkeypatch.setenv("GRAFID_DATA_DIR", str(temp_config_dir))
    _registry_for(db_path, monkeypatch)
    exe = _fake_exe(tmp_path)
    ConfigManager(config_dir=temp_config_dir)
    desktop_entry.dispatch(
        "save-app-settings",
        ["--opener", "system", "--builtin-agents", json.dumps({"claude-code": {"executable": str(exe)}})],
    )
    response = desktop_entry.dispatch("resolve-coding-agent-launch", ["claude-code", str(project_id)])
    assert response.ok is True, response
    assert Path(response.data["executable"]) == exe.resolve()


# ---------------------------------------------------------------------------
# Imported bundles cannot smuggle in agent executables
# ---------------------------------------------------------------------------


def test_import_bundle_strips_agent_definitions_overrides_and_agent_openers() -> None:
    raw = {
        "default_project_opener": "agent:evil",
        "preferred_ide": "agent:evil",
        "coding_agents": [{"id": "evil", "display_name": "Evil", "executable": "C:/evil.exe"}],
        "builtin_agents": {"claude-code": {"executable": "C:/evil.exe"}},
        "usage_journal": True,
    }
    cleaned = json.loads(_sanitized_config_json(json.dumps(raw)))
    assert "coding_agents" not in cleaned and "builtin_agents" not in cleaned
    assert cleaned["default_project_opener"] == "system"
    assert cleaned["preferred_ide"] == "system"
    assert cleaned["usage_journal"] is True


# ---------------------------------------------------------------------------
# Settings payload shape used by the UI
# ---------------------------------------------------------------------------


def test_settings_payload_exposes_removed_presets_and_override_fields(
    config_manager: ConfigManager,
) -> None:
    response = handle_get_app_settings(config_manager)
    assert response.data["removed_builtin_agents"] == []
    claude = _by_id(response.data["coding_agents"], "claude-code")
    assert claude["default_executable"] == "claude"
    assert claude["executable_override"] is None


# ---------------------------------------------------------------------------
# Explicit paths on custom agents are validated when new/changed only
# ---------------------------------------------------------------------------


def test_new_custom_agent_pointing_at_a_folder_is_rejected_with_a_clear_message(
    tmp_path: Path,
) -> None:
    from grafid.config.coding_agents import validate_custom_agents_payload

    app_folder = tmp_path / "WindowsApps" / "Claude_2.2553.1.0_x64" / "app"
    app_folder.mkdir(parents=True)
    with pytest.raises(ConfigError, match="Claude Code: .*is a directory, not an executable file"):
        validate_custom_agents_payload(
            [{"display_name": "Claude Code", "executable": str(app_folder)}]
        )


def test_new_custom_agent_with_a_missing_explicit_path_is_rejected(tmp_path: Path) -> None:
    from grafid.config.coding_agents import validate_custom_agents_payload

    with pytest.raises(ConfigError, match="does not exist"):
        validate_custom_agents_payload(
            [{"display_name": "Gone", "executable": str(tmp_path / "gone.exe")}]
        )


def test_custom_agent_with_a_bare_command_is_still_accepted_even_if_not_installed() -> None:
    from grafid.config.coding_agents import validate_custom_agents_payload

    agents = validate_custom_agents_payload([{"display_name": "Later", "executable": "not-installed-yet"}])
    assert agents[0].executable == "not-installed-yet"


def test_unchanged_custom_agent_whose_tool_was_uninstalled_does_not_block_saves(
    tmp_path: Path,
) -> None:
    from grafid.config.coding_agents import validate_custom_agents_payload

    stored = CodingAgentConfig(
        id="old", display_name="Old", executable=str(tmp_path / "uninstalled.exe")
    )
    payload = [{"id": "old", "display_name": "Old", "executable": stored.executable}]
    assert validate_custom_agents_payload(payload, previous=[stored])[0].id == "old"
    # ...but editing its path to something else that does not exist is rejected.
    payload[0]["executable"] = str(tmp_path / "other-missing.exe")
    with pytest.raises(ConfigError, match="does not exist"):
        validate_custom_agents_payload(payload, previous=[stored])


def test_unchanged_stale_preset_override_does_not_block_unrelated_saves(
    config_manager: ConfigManager, tmp_path: Path
) -> None:
    exe = _fake_exe(tmp_path)
    assert _save(
        config_manager, builtin_agents=json.dumps({"claude-code": {"executable": str(exe)}})
    ).ok
    exe.unlink()  # the tool is uninstalled / moved later

    still_ok = _save(
        config_manager,
        opener="cursor",
        builtin_agents=json.dumps({"claude-code": {"executable": str(exe)}}),
    )
    assert still_ok.ok is True
    entry = _by_id(still_ok.data["coding_agents"], "claude-code")
    assert entry["available"] is False and "does not exist" in entry["unavailable_reason"]


def test_saving_a_folder_as_custom_agent_through_settings_reports_the_error(
    config_manager: ConfigManager, tmp_path: Path
) -> None:
    folder = tmp_path / "app"
    folder.mkdir()
    response = _save(
        config_manager,
        coding_agents=json.dumps([{"display_name": "Claude Code", "executable": str(folder)}]),
    )
    assert response.ok is False
    assert "directory" in response.error.message
