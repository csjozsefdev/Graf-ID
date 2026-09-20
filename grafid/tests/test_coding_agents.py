"""Tests for the Generic Coding Agent Launcher: config model, resolution,
settings integration, and lifecycle isolation from the editor flow (M11)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from grafid.config.coding_agents import (
    BUILTIN_CODING_AGENTS,
    CodingAgentConfig,
    agent_id_from_opener_value,
    describe_invalid_explicit_path,
    executable_candidates_for,
    find_agent,
    generate_agent_id,
    is_agent_opener_value,
    merged_agent_list,
    opener_value_for_agent,
    parse_custom_agent,
    parse_custom_agents,
    resolve_agent_executable,
    validate_custom_agents_payload,
)
from grafid.config.manager import AppConfig, ConfigManager
from grafid.config.preferences import normalize_default_project_opener
from grafid.core.exceptions import ConfigError
from grafid.ipc.coding_agent_handlers import handle_resolve_coding_agent_launch
from grafid.ipc.settings_handlers import handle_get_app_settings, handle_save_app_settings
from grafid.services.coding_agent_launch import (
    CodingAgentError,
    resolve_coding_agent_launch,
)
from grafid.services.workflow_launch import normalize_ide_token

# ---------------------------------------------------------------------------
# Built-ins (M3): detection
# ---------------------------------------------------------------------------


def test_claude_code_and_codex_cli_are_builtin_presets() -> None:
    ids = {p.id for p in BUILTIN_CODING_AGENTS}
    assert ids == {"claude-code", "codex-cli"}


def test_builtin_executable_candidates_are_bare_path_commands_not_hardcoded_paths() -> None:
    """M3/M5: PATH-only detection — no user-specific install path baked in."""
    for preset in BUILTIN_CODING_AGENTS:
        for candidate in preset.executable_candidates:
            assert "/" not in candidate and "\\" not in candidate
            assert ":" not in candidate  # no drive letter


def test_claude_detected_when_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_which(cmd: str) -> str | None:
        return r"C:\fake\claude.cmd" if cmd in ("claude", "claude.cmd") else None

    monkeypatch.setattr("grafid.config.coding_agents.shutil.which", fake_which)
    resolved = resolve_agent_executable(("claude", "claude.cmd"))
    assert resolved == str(Path(r"C:\fake\claude.cmd").resolve())


def test_codex_detected_when_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_which(cmd: str) -> str | None:
        return r"C:\fake\codex.cmd" if cmd in ("codex", "codex.cmd") else None

    monkeypatch.setattr("grafid.config.coding_agents.shutil.which", fake_which)
    resolved = resolve_agent_executable(("codex", "codex.cmd"))
    assert resolved is not None


def test_claude_unavailable_when_not_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("grafid.config.coding_agents.shutil.which", lambda cmd: None)
    resolved = resolve_agent_executable(("claude", "claude.cmd"))
    assert resolved is None


def test_codex_unavailable_when_not_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("grafid.config.coding_agents.shutil.which", lambda cmd: None)
    resolved = resolve_agent_executable(("codex", "codex.cmd"))
    assert resolved is None


def test_merged_agent_list_reports_availability_honestly(monkeypatch: pytest.MonkeyPatch) -> None:
    """M12: never fake success — availability must reflect real PATH state."""
    monkeypatch.setattr("grafid.config.coding_agents.shutil.which", lambda cmd: None)
    agents = merged_agent_list([])
    assert all(a["available"] is False for a in agents if a["built_in"])


# ---------------------------------------------------------------------------
# Custom agents: PATH command, absolute path, invalid executable, directory
# ---------------------------------------------------------------------------


def test_custom_agent_path_command_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "grafid.config.coding_agents.shutil.which",
        lambda cmd: r"C:\tools\myagent.exe" if cmd == "myagent" else None,
    )
    resolved = resolve_agent_executable(("myagent",))
    assert resolved == str(Path(r"C:\tools\myagent.exe").resolve())


def test_custom_agent_absolute_path_resolves(tmp_path: Path) -> None:
    exe = tmp_path / "agent.exe"
    exe.write_bytes(b"stub")
    resolved = resolve_agent_executable((str(exe),))
    assert resolved == str(exe.resolve())


def test_custom_agent_invalid_executable_reports_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.exe"
    resolved = resolve_agent_executable((str(missing),))
    assert resolved is None
    reason = describe_invalid_explicit_path(str(missing))
    assert reason is not None and "does not exist" in reason


def test_custom_agent_directory_instead_of_executable_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    resolved = resolve_agent_executable((str(directory),))
    assert resolved is None
    reason = describe_invalid_explicit_path(str(directory))
    assert reason is not None and "directory" in reason


def test_custom_agent_whitespace_path_resolves(tmp_path: Path) -> None:
    weird = tmp_path / "my agent dir"
    weird.mkdir()
    exe = weird / "agent.exe"
    exe.write_bytes(b"stub")
    resolved = resolve_agent_executable((str(exe),))
    assert resolved == str(exe.resolve())


def test_custom_agent_unicode_path_resolves(tmp_path: Path) -> None:
    weird = tmp_path / "café-агент-中文"
    weird.mkdir()
    exe = weird / "agent.exe"
    exe.write_bytes(b"stub")
    resolved = resolve_agent_executable((str(exe),))
    assert resolved == str(exe.resolve())


# ---------------------------------------------------------------------------
# Custom agents: create, edit, delete, persistence, duplicates, malformed
# ---------------------------------------------------------------------------


def test_parse_custom_agent_generates_id_from_display_name() -> None:
    agent = parse_custom_agent(
        {"display_name": "My Local Agent!", "executable": "myagent"},
        existing_ids=frozenset(),
    )
    assert agent.id == "my-local-agent"
    assert agent.built_in is False


def test_parse_custom_agent_rejects_missing_display_name() -> None:
    with pytest.raises(ConfigError):
        parse_custom_agent({"executable": "myagent"}, existing_ids=frozenset())


def test_parse_custom_agent_rejects_missing_executable() -> None:
    with pytest.raises(ConfigError):
        parse_custom_agent({"display_name": "X"}, existing_ids=frozenset())


def test_parse_custom_agent_rejects_id_colliding_with_builtin() -> None:
    with pytest.raises(ConfigError):
        parse_custom_agent(
            {"id": "claude-code", "display_name": "X", "executable": "x"},
            existing_ids=frozenset(),
        )


def test_generate_agent_id_dedupes_against_existing_and_builtin_ids() -> None:
    first = generate_agent_id("Codex CLI", existing_ids=frozenset())
    assert first != "codex-cli"  # collides with a built-in, must not reuse it
    second = generate_agent_id("Foo", existing_ids=frozenset({"foo"}))
    assert second == "foo-2"


def test_validate_custom_agents_payload_round_trips_create_edit_delete() -> None:
    created = validate_custom_agents_payload(
        [{"display_name": "Agent One", "executable": "agent1", "args": ["--flag"]}]
    )
    assert len(created) == 1
    agent_id = created[0].id

    edited = validate_custom_agents_payload(
        [{"id": agent_id, "display_name": "Agent One Renamed", "executable": "agent1new", "args": []}]
    )
    assert edited[0].id == agent_id
    assert edited[0].display_name == "Agent One Renamed"

    deleted = validate_custom_agents_payload([])
    assert deleted == []


def test_validate_custom_agents_payload_rejects_duplicate_ids() -> None:
    with pytest.raises(ConfigError):
        validate_custom_agents_payload(
            [
                {"id": "dup", "display_name": "A", "executable": "a"},
                {"id": "dup", "display_name": "B", "executable": "b"},
            ]
        )


def test_validate_custom_agents_payload_rejects_non_list() -> None:
    with pytest.raises(ConfigError):
        validate_custom_agents_payload({"not": "a list"})


def test_validate_custom_agents_payload_rejects_malformed_entry() -> None:
    with pytest.raises(ConfigError):
        validate_custom_agents_payload([{"display_name": 123, "executable": "x"}])


def test_parse_custom_agents_fails_open_on_malformed_entries() -> None:
    """The read path (config load) must not crash the whole app on one bad
    entry — unlike validate_custom_agents_payload's strict save-path
    behavior, this silently drops what it can't parse."""
    agents = parse_custom_agents(
        [
            {"display_name": "Good", "executable": "good"},
            {"display_name": None, "executable": "bad"},
            "not even a dict",
        ]
    )
    assert len(agents) == 1
    assert agents[0].display_name == "Good"


def test_parse_custom_agents_handles_completely_malformed_config() -> None:
    assert parse_custom_agents("not a list") == []
    assert parse_custom_agents(None) == []
    assert parse_custom_agents(42) == []


def test_config_manager_persists_and_reloads_coding_agents(tmp_path: Path) -> None:
    manager = ConfigManager(config_dir=tmp_path)
    config = AppConfig(
        coding_agents=[
            CodingAgentConfig(
                id="my-agent", display_name="My Agent", executable="myagent", args=("--x",)
            )
        ]
    )
    manager.save(config)
    reloaded = manager.load()
    assert len(reloaded.coding_agents) == 1
    assert reloaded.coding_agents[0].id == "my-agent"
    assert reloaded.coding_agents[0].args == ("--x",)


def test_existing_editor_preferences_survive_a_config_round_trip_unaffected(
    tmp_path: Path,
) -> None:
    """M1: existing editor preferences must not be broken by this addition."""
    manager = ConfigManager(config_dir=tmp_path)
    config = AppConfig(default_project_opener="cursor")
    manager.save(config)
    reloaded = manager.load()
    assert reloaded.default_project_opener == "cursor"
    assert reloaded.coding_agents == []


def test_loading_a_pre_existing_config_without_coding_agents_key_works(tmp_path: Path) -> None:
    """Backwards compatible: an old config.json with no coding_agents key at
    all (M1) must load cleanly with an empty custom-agent list."""
    config_dir = tmp_path
    config_dir.mkdir(exist_ok=True)
    (config_dir / "config.json").write_text(
        '{"default_project_opener": "vscode", "usage_journal": true}',
        encoding="utf-8",
    )
    manager = ConfigManager(config_dir=config_dir)
    loaded = manager.load()
    assert loaded.default_project_opener == "vscode"
    assert loaded.coding_agents == []


# ---------------------------------------------------------------------------
# Dangling reference (M9): deleted custom agent still set as opener
# ---------------------------------------------------------------------------


def test_find_agent_returns_none_for_a_deleted_custom_agent() -> None:
    assert find_agent("deleted-agent-id", custom_agents=[]) is None


def test_resolve_launch_for_dangling_agent_reference_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(CodingAgentError, match="not configured"):
        resolve_coding_agent_launch("deleted-agent-id", str(tmp_path), custom_agents=[])


def test_opener_value_helpers_round_trip() -> None:
    value = opener_value_for_agent("claude-code")
    assert value == "agent:claude-code"
    assert is_agent_opener_value(value) is True
    assert agent_id_from_opener_value(value) == "claude-code"
    assert is_agent_opener_value("cursor") is False
    assert agent_id_from_opener_value("cursor") is None


def test_normalize_default_project_opener_accepts_agent_values() -> None:
    assert normalize_default_project_opener("agent:claude-code") == "agent:claude-code"
    assert normalize_default_project_opener("agent:my-custom-thing") == "agent:my-custom-thing"


def test_normalize_default_project_opener_still_validates_editor_tokens() -> None:
    """M8: existing editor-token validation must be completely unaffected."""
    assert normalize_default_project_opener("cursor") == "cursor"
    with pytest.raises(ConfigError):
        normalize_default_project_opener("not-a-real-editor")


def test_normalize_ide_token_gracefully_ignores_agent_values() -> None:
    """M9: a dangling/legacy CLI path with an agent-type opener must not
    crash — falls through to None (Explorer fallback), never raises."""
    assert normalize_ide_token("agent:claude-code") is None
    assert normalize_ide_token("agent:some-deleted-agent") is None


def test_normalize_ide_token_still_validates_editor_tokens_and_raises_for_unknown() -> None:
    """M8: existing editor-token behavior (including raising on garbage) is
    completely unaffected."""
    assert normalize_ide_token("cursor") == "cursor"
    with pytest.raises(Exception):
        normalize_ide_token("not-a-real-editor")


# ---------------------------------------------------------------------------
# Launch resolution: cwd, executable, args order
# ---------------------------------------------------------------------------


def test_resolve_launch_uses_project_root_as_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "grafid.services.coding_agent_launch.resolve_agent_executable",
        lambda candidates: r"C:\fake\claude.cmd",
    )
    spec = resolve_coding_agent_launch("claude-code", str(tmp_path), custom_agents=[])
    assert Path(spec.cwd) == tmp_path.resolve()


def test_resolve_launch_preserves_args_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "grafid.services.coding_agent_launch.resolve_agent_executable",
        lambda candidates: r"C:\fake\myagent.exe",
    )
    agent = CodingAgentConfig(
        id="my-agent",
        display_name="My Agent",
        executable="myagent",
        args=("--profile", "coding", "--verbose"),
    )
    spec = resolve_coding_agent_launch("my-agent", str(tmp_path), custom_agents=[agent])
    assert spec.args == ("--profile", "coding", "--verbose")


def test_resolve_launch_reports_missing_project_folder() -> None:
    with pytest.raises(CodingAgentError):
        resolve_coding_agent_launch(
            "claude-code", r"C:\graf-id-definitely-does-not-exist-xyz", custom_agents=[]
        )


def test_resolve_launch_unavailable_builtin_gives_actionable_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "grafid.services.coding_agent_launch.resolve_agent_executable", lambda candidates: None
    )
    with pytest.raises(CodingAgentError, match="PATH"):
        resolve_coding_agent_launch("claude-code", str(tmp_path), custom_agents=[])


def test_built_in_and_custom_agent_use_the_same_resolution_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M3: same infra for built-in and custom agents."""
    calls: list[tuple[str, ...]] = []

    def fake_resolve(candidates: tuple[str, ...]) -> str | None:
        calls.append(candidates)
        return r"C:\fake\exe.exe"

    monkeypatch.setattr("grafid.services.coding_agent_launch.resolve_agent_executable", fake_resolve)
    custom = CodingAgentConfig(id="custom-1", display_name="Custom", executable="customexe")

    resolve_coding_agent_launch("claude-code", str(tmp_path), custom_agents=[custom])
    resolve_coding_agent_launch("custom-1", str(tmp_path), custom_agents=[custom])

    assert len(calls) == 2
    assert calls[0] == ("claude", "claude.cmd")
    assert calls[1] == ("customexe",)


def test_executable_candidates_for_uses_preset_candidates_for_builtins() -> None:
    claude = find_agent("claude-code", custom_agents=[])
    assert claude is not None
    assert executable_candidates_for(claude) == ("claude", "claude.cmd")


# ---------------------------------------------------------------------------
# IPC: settings payload + save, resolve-launch handler
# ---------------------------------------------------------------------------


def test_settings_payload_includes_coding_agents(config_manager: ConfigManager) -> None:
    response = handle_get_app_settings(config_manager)
    assert response.ok is True
    ids = {a["id"] for a in response.data["coding_agents"]}
    assert {"claude-code", "codex-cli"}.issubset(ids)


def test_save_app_settings_persists_coding_agents_json_string(
    config_manager: ConfigManager,
) -> None:
    import json

    payload = json.dumps([{"display_name": "Saved Agent", "executable": "savedagent"}])
    response = handle_save_app_settings(
        "system", False, False, coding_agents=payload, config_manager=config_manager
    )
    assert response.ok is True
    custom = [a for a in response.data["coding_agents"] if not a["built_in"]]
    assert len(custom) == 1
    assert custom[0]["display_name"] == "Saved Agent"

    reloaded = config_manager.load()
    assert len(reloaded.coding_agents) == 1


def test_save_app_settings_rejects_invalid_coding_agents_json(
    config_manager: ConfigManager,
) -> None:
    response = handle_save_app_settings(
        "system", False, False, coding_agents="not valid json", config_manager=config_manager
    )
    assert response.ok is False


def test_save_app_settings_without_coding_agents_keeps_existing(
    config_manager: ConfigManager,
) -> None:
    import json

    payload = json.dumps([{"display_name": "Keep Me", "executable": "keepme"}])
    handle_save_app_settings(
        "system", False, False, coding_agents=payload, config_manager=config_manager
    )
    # Saving again without touching coding_agents must not wipe it.
    response = handle_save_app_settings(
        "vscode", False, False, config_manager=config_manager
    )
    custom = [a for a in response.data["coding_agents"] if not a["built_in"]]
    assert len(custom) == 1
    assert custom[0]["display_name"] == "Keep Me"


def test_resolve_coding_agent_launch_handler_never_touches_sessions(
    config_manager: ConfigManager, project_id: int, db_path: Path
) -> None:
    with patch("grafid.services.coding_agent_launch.resolve_agent_executable") as mock_resolve:
        mock_resolve.return_value = r"C:\fake\claude.cmd"
        with patch("grafid.services.runtime.StartupService") as mock_startup:
            mock_result = MagicMock()
            mock_result.database_path = db_path
            mock_startup.return_value.run.return_value = mock_result
            from grafid.services.runtime import reset_runtime_cache

            reset_runtime_cache()
            response = handle_resolve_coding_agent_launch(
                "claude-code", project_id, config_manager=config_manager
            )
    assert response.ok is True
    assert "executable" in response.data
    assert "cwd" in response.data
    # No session-related keys anywhere in the response (M7).
    assert "session_id" not in response.data
    assert "session_started" not in response.data


# ---------------------------------------------------------------------------
# Lifecycle isolation (M7): launch resolution must never start a session
# ---------------------------------------------------------------------------


def test_resolve_coding_agent_launch_does_not_create_a_work_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "grafid.services.coding_agent_launch.resolve_agent_executable",
        lambda candidates: r"C:\fake\claude.cmd",
    )
    with patch("grafid.services.session_service.SessionService") as mock_session_service:
        resolve_coding_agent_launch("claude-code", str(tmp_path), custom_agents=[])
        mock_session_service.assert_not_called()


def test_coding_agent_launch_module_does_not_import_session_service() -> None:
    """Structural guarantee, not just a mock check: the launch-resolution
    module has no dependency on session machinery at all."""
    import grafid.services.coding_agent_launch as mod

    assert "SessionService" not in dir(mod)
    assert "session_service" not in mod.__file__


def test_coding_agent_launch_module_does_not_reference_exit_note() -> None:
    import inspect

    import grafid.services.coding_agent_launch as mod

    source = inspect.getsource(mod)
    assert "exit_note" not in source.lower()
    assert "exit note" not in source.lower()
