"""Generic Coding Agent launcher config: built-in presets + user-defined agents.

A "coding agent" is any interactive CLI tool the user wants launched in a
project's root directory (Claude Code, Codex CLI, or something else
entirely — Graf-Id does not need to know what runs inside it). This is
deliberately a separate concept from the existing editor openers: agents
get no work session, no process-lifecycle tracking, and no Exit Note — see
grafid/services/coding_agent_launch.py for the launch side of that
boundary.
"""

from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from grafid.core.exceptions import ConfigError

CODING_AGENTS_KEY = "coding_agents"
BUILTIN_AGENTS_KEY = "builtin_agents"

# Namespaced so a stored opener value can be told apart from an editor token
# (cursor, vscode, ...) with a simple prefix check, without needing to
# validate against an ever-changing set of user-defined agent ids.
AGENT_OPENER_PREFIX = "agent:"

_MAX_CUSTOM_AGENTS = 50
_MAX_ARGS = 20
_MAX_FIELD_CHARS = 4000


@dataclass(frozen=True)
class CodingAgentPreset:
    """Built-in agent definition — code, not user config."""

    id: str
    display_name: str
    executable_candidates: tuple[str, ...]


# M3: PATH-only detection, no user-specific installed path is ever hardcoded
# here — only the bare command names npm-installed CLIs resolve to on PATH.
# shutil.which() already tries PATHEXT (.CMD included) for a bare name on
# Windows; the explicit ".cmd" candidate is kept anyway to match the existing
# editor-detection style (_find_editor_executable's ["code", "code.cmd"]).
BUILTIN_CODING_AGENTS: tuple[CodingAgentPreset, ...] = (
    CodingAgentPreset(
        id="claude-code",
        display_name="Claude Code",
        executable_candidates=("claude", "claude.cmd"),
    ),
    CodingAgentPreset(
        id="codex-cli",
        display_name="Codex CLI",
        executable_candidates=("codex", "codex.cmd"),
    ),
)

_BUILTIN_IDS = frozenset(preset.id for preset in BUILTIN_CODING_AGENTS)
_BUILTIN_BY_ID = {preset.id: preset for preset in BUILTIN_CODING_AGENTS}

# The launch mechanism on Windows is `cmd /C start "" <exe>`; anything that is
# not one of these would be opened by file association instead of executed.
_WINDOWS_LAUNCHABLE_SUFFIXES = frozenset({".exe", ".cmd", ".bat", ".com"})


def _is_windows() -> bool:
    return sys.platform == "win32"


@dataclass(frozen=True)
class BuiltinAgentSettings:
    """Per-user state for a built-in preset (the preset itself stays in code,
    so it keeps updating with new Graf-Id versions): hidden/removed flag plus
    an optional explicit executable override and extra arguments."""

    hidden: bool = False
    executable: str | None = None
    args: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.hidden:
            data["hidden"] = True
        if self.executable:
            data["executable"] = self.executable
        if self.args:
            data["args"] = list(self.args)
        return data


BuiltinSettingsMap = dict[str, BuiltinAgentSettings]


@dataclass(frozen=True)
class CodingAgentConfig:
    """Unified shape for both built-in and custom agents (M3: same infra)."""

    id: str
    display_name: str
    executable: str
    args: tuple[str, ...] = ()
    built_in: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "executable": self.executable,
            "args": list(self.args),
            "built_in": self.built_in,
        }


def opener_value_for_agent(agent_id: str) -> str:
    """The value stored in default_project_opener / preferred_ide for an agent."""
    return f"{AGENT_OPENER_PREFIX}{agent_id}"


def agent_id_from_opener_value(value: str | None) -> str | None:
    """Extract the agent id from an opener value, or None if it isn't one."""
    if not value or not value.startswith(AGENT_OPENER_PREFIX):
        return None
    agent_id = value[len(AGENT_OPENER_PREFIX) :]
    return agent_id or None


def is_agent_opener_value(value: str | None) -> bool:
    return agent_id_from_opener_value(value) is not None


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return slug or "agent"


def generate_agent_id(display_name: str, existing_ids: frozenset[str]) -> str:
    """Deterministic, collision-free id from a display name (M9: ids are
    system-generated, not a user-facing field)."""
    base = _slugify(display_name)
    if base not in existing_ids and base not in _BUILTIN_IDS:
        return base
    n = 2
    while f"{base}-{n}" in existing_ids or f"{base}-{n}" in _BUILTIN_IDS:
        n += 1
    return f"{base}-{n}"


def _require_text(value: Any, field: str, *, max_chars: int = _MAX_FIELD_CHARS) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Coding agent {field} must be a non-empty string.")
    text = value.strip()
    if len(text) > max_chars:
        raise ConfigError(f"Coding agent {field} is too long (max {max_chars} characters).")
    return text


def _normalize_args(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError("Coding agent args must be a list of strings.")
    if len(raw) > _MAX_ARGS:
        raise ConfigError(f"Coding agent args exceed the maximum of {_MAX_ARGS} entries.")
    args: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ConfigError("Each coding agent argument must be a string.")
        if len(item) > _MAX_FIELD_CHARS:
            raise ConfigError("A coding agent argument is too long.")
        args.append(item)
    return tuple(args)


def parse_custom_agent(raw: dict[str, Any], *, existing_ids: frozenset[str]) -> CodingAgentConfig:
    """Parse and validate one custom agent entry from stored/incoming JSON."""
    if not isinstance(raw, dict):
        raise ConfigError("Each coding agent entry must be a JSON object.")

    display_name = _require_text(raw.get("display_name"), "display_name", max_chars=200)
    executable = _require_text(raw.get("executable"), "executable", max_chars=1000)
    args = _normalize_args(raw.get("args"))

    raw_id = raw.get("id")
    if isinstance(raw_id, str) and raw_id.strip():
        agent_id = raw_id.strip()
        if agent_id in _BUILTIN_IDS:
            raise ConfigError(f"Coding agent id '{agent_id}' collides with a built-in agent.")
    else:
        agent_id = generate_agent_id(display_name, existing_ids)

    return CodingAgentConfig(
        id=agent_id,
        display_name=display_name,
        executable=executable,
        args=args,
        built_in=False,
    )


def parse_custom_agents(raw: Any) -> list[CodingAgentConfig]:
    """
    Parse the full stored custom-agent list.

    Malformed config (M9) fails closed to an empty list rather than raising
    and breaking Settings/Open Project — a corrupt coding_agents blob must
    not be able to take down the rest of the app.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    agents: list[CodingAgentConfig] = []
    seen_ids: set[str] = set()
    for entry in raw[:_MAX_CUSTOM_AGENTS]:
        try:
            agent = parse_custom_agent(entry, existing_ids=frozenset(seen_ids))
        except ConfigError:
            continue
        if agent.id in seen_ids:
            # Deterministic dedup: keep the first occurrence, drop the rest,
            # rather than raising and losing every other valid agent too.
            continue
        seen_ids.add(agent.id)
        agents.append(agent)
    return agents


def validate_custom_agents_payload(
    raw: Any, previous: list[CodingAgentConfig] | None = None
) -> list[CodingAgentConfig]:
    """
    Strict variant for the save path: raises ConfigError on the first
    problem (unlike parse_custom_agents' fail-open read path), so a bad
    save attempt is rejected with a clear message instead of silently
    dropping entries.

    An explicit executable *path* on a new or changed agent must exist, be a
    file (not a folder) and be launchable. Agents whose executable is
    unchanged from `previous` are not re-checked: a tool that was uninstalled
    later must show as "Not found", not block every unrelated Settings save.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError("coding_agents must be a list.")
    if len(raw) > _MAX_CUSTOM_AGENTS:
        raise ConfigError(f"Too many coding agents (max {_MAX_CUSTOM_AGENTS}).")
    known_executables = {a.id: a.executable for a in previous or []}
    agents: list[CodingAgentConfig] = []
    seen_ids: set[str] = set()
    for entry in raw:
        agent = parse_custom_agent(entry, existing_ids=frozenset(seen_ids))
        if agent.id in seen_ids:
            raise ConfigError(f"Duplicate coding agent id '{agent.id}'.")
        if known_executables.get(agent.id) != agent.executable:
            reason = describe_invalid_explicit_path(agent.executable, require_launchable=True)
            if reason:
                raise ConfigError(f"{agent.display_name}: {reason}")
        seen_ids.add(agent.id)
        agents.append(agent)
    return agents


def _looks_like_path(executable: str) -> bool:
    return "/" in executable or "\\" in executable or Path(executable).is_absolute()


def resolve_agent_executable(executable_candidates: tuple[str, ...]) -> str | None:
    """
    Resolve the first working candidate to an absolute path.

    Each candidate is resolved the same way regardless of whether it looks
    like a bare PATH command ("claude") or an explicit path
    ("C:\\Tools\\MyAgent\\agent.exe") — shutil.which() already handles both:
    for a path-like string it checks that exact location (and executability)
    directly rather than searching PATH, which is exactly the distinction
    M4 asks for, without needing two separate code paths.
    """
    for candidate in executable_candidates:
        if _looks_like_path(candidate):
            path = Path(candidate).expanduser()
            if path.is_dir():
                continue
            if path.is_file():
                return str(path.resolve())
            continue
        found = shutil.which(candidate)
        if found:
            return str(Path(found).resolve())
    return None


def describe_invalid_explicit_path(
    executable: str, *, require_launchable: bool = False
) -> str | None:
    """
    If `executable` looks like an explicit path, return a specific reason
    it can't be used (M4: "értelmes hibaüzenetet ad, ha hibás"), else None.

    `require_launchable` additionally rejects (on Windows) files the terminal
    launch mechanism would open by file association instead of executing.
    """
    if not _looks_like_path(executable):
        return None
    path = Path(executable).expanduser()
    if path.is_dir():
        return f"'{executable}' is a directory, not an executable file."
    if not path.exists():
        return f"'{executable}' does not exist."
    if not path.is_file():
        return f"'{executable}' is not a regular file."
    if require_launchable and not _is_launchable_file(path):
        return (
            f"'{executable}' cannot be launched: expected an "
            ".exe, .cmd, .bat or .com file."
        )
    return None


def _is_launchable_file(path: Path) -> bool:
    if not _is_windows():
        return True
    return path.suffix.lower() in _WINDOWS_LAUNCHABLE_SUFFIXES


def resolve_override_executable(executable: str) -> tuple[str | None, str | None]:
    """
    Resolve a user-defined executable override (built-in preset path override).

    Returns (resolved_path, reason). The override is the ONLY thing tried —
    a broken override never silently falls back to PATH detection or to any
    other executable. A bare command is looked up on PATH; an explicit path
    must exist, be a file (not a directory) and be launchable.
    """
    reason = describe_invalid_explicit_path(executable, require_launchable=True)
    if reason:
        return None, reason
    if _looks_like_path(executable):
        return str(Path(executable).expanduser().resolve()), None
    found = shutil.which(executable)
    if found:
        return str(Path(found).resolve()), None
    return None, f"'{executable}' was not found on PATH."


def agent_availability(agent: CodingAgentConfig, *, candidates: tuple[str, ...] | None = None) -> bool:
    """True if the agent's executable currently resolves to something runnable."""
    resolved = resolve_agent_executable(candidates or (agent.executable,))
    return resolved is not None


def _clean_optional_text(value: Any, field: str, *, max_chars: int = 1000) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"Built-in coding agent {field} must be a string.")
    text = value.strip()
    if not text:
        return None
    if len(text) > max_chars:
        raise ConfigError(f"Built-in coding agent {field} is too long (max {max_chars} characters).")
    return text


def parse_builtin_agent_settings(raw: Any) -> BuiltinSettingsMap:
    """
    Config-LOAD path (fails open): keep only well-formed entries for known
    built-in ids so a corrupt/hand-edited blob can never break Settings or
    Open Project. Unknown ids are dropped — a preset removed from a future
    Graf-Id version simply stops mattering.
    """
    if not isinstance(raw, dict):
        return {}
    result: BuiltinSettingsMap = {}
    for agent_id, entry in raw.items():
        if agent_id not in _BUILTIN_IDS or not isinstance(entry, dict):
            continue
        hidden = entry.get("hidden") is True
        try:
            executable = _clean_optional_text(entry.get("executable"), "executable")
            args = _normalize_args(entry.get("args"))
        except ConfigError:
            executable, args = None, ()
        settings = BuiltinAgentSettings(
            hidden=hidden,
            executable=None if hidden else executable,
            args=() if hidden else args,
        )
        if settings.to_dict():
            result[agent_id] = settings
    return result


def validate_builtin_agent_settings_payload(
    raw: Any, previous: BuiltinSettingsMap | None = None
) -> BuiltinSettingsMap:
    """
    Config-SAVE path (fails closed): raise ConfigError with a clear message
    on the first problem — unknown preset id, wrong types, or an explicit
    executable override that does not exist / is a directory / is not
    launchable. Removed (hidden) presets drop any override, so a stale path
    can never block saving; neither does an override that is unchanged from
    `previous` (a tool uninstalled later shows as Not found instead).
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("builtin_agents must be an object keyed by built-in agent id.")
    result: BuiltinSettingsMap = {}
    for agent_id, entry in raw.items():
        if agent_id not in _BUILTIN_IDS:
            raise ConfigError(f"Unknown built-in coding agent '{agent_id}'.")
        if not isinstance(entry, dict):
            raise ConfigError(f"Settings for built-in agent '{agent_id}' must be an object.")
        hidden = entry.get("hidden", False)
        if not isinstance(hidden, bool):
            raise ConfigError(f"Built-in agent '{agent_id}': hidden must be true or false.")
        if hidden:
            result[agent_id] = BuiltinAgentSettings(hidden=True)
            continue
        executable = _clean_optional_text(entry.get("executable"), "executable")
        args = _normalize_args(entry.get("args"))
        unchanged = (
            previous is not None
            and agent_id in previous
            and previous[agent_id].executable == executable
        )
        if executable is not None and not unchanged:
            reason = describe_invalid_explicit_path(executable, require_launchable=True)
            if reason:
                name = _BUILTIN_BY_ID[agent_id].display_name
                raise ConfigError(f"{name}: {reason}")
        settings = BuiltinAgentSettings(hidden=False, executable=executable, args=args)
        if settings.to_dict():
            result[agent_id] = settings
    return result


def builtin_settings_to_dict(settings: BuiltinSettingsMap) -> dict[str, dict[str, Any]]:
    return {agent_id: s.to_dict() for agent_id, s in settings.items() if s.to_dict()}


def _builtin_state(
    preset: CodingAgentPreset, settings: BuiltinAgentSettings | None
) -> tuple[bool, str | None]:
    """(available, unavailable_reason) for a built-in, honoring an override."""
    if settings is not None and settings.executable:
        resolved, reason = resolve_override_executable(settings.executable)
        return resolved is not None, reason
    return resolve_agent_executable(preset.executable_candidates) is not None, None


def _builtin_entry(preset: CodingAgentPreset, settings: BuiltinAgentSettings | None) -> dict[str, Any]:
    override = settings.executable if settings else None
    available, reason = _builtin_state(preset, settings)
    return {
        "id": preset.id,
        "display_name": preset.display_name,
        "executable": override or preset.executable_candidates[0],
        "default_executable": preset.executable_candidates[0],
        "executable_override": override,
        "args": list(settings.args) if settings else [],
        "built_in": True,
        "available": available,
        "unavailable_reason": None if available else reason,
    }


def merged_agent_list(
    custom_agents: list[CodingAgentConfig],
    builtin_settings: BuiltinSettingsMap | None = None,
) -> list[dict[str, Any]]:
    """Visible built-ins (not removed) + custom agents, each with computed availability."""
    settings_map = builtin_settings or {}
    result: list[dict[str, Any]] = []
    for preset in BUILTIN_CODING_AGENTS:
        settings = settings_map.get(preset.id)
        if settings is not None and settings.hidden:
            continue
        result.append(_builtin_entry(preset, settings))
    for agent in custom_agents:
        available = agent_availability(agent)
        entry = agent.to_dict()
        entry["available"] = available
        entry["unavailable_reason"] = (
            None if available else describe_invalid_explicit_path(agent.executable)
        )
        result.append(entry)
    return result


def removed_builtin_agents(builtin_settings: BuiltinSettingsMap | None = None) -> list[dict[str, Any]]:
    """Built-in presets the user removed, in the same shape as merged_agent_list
    entries (default detection state), so the UI can offer to restore them."""
    settings_map = builtin_settings or {}
    removed: list[dict[str, Any]] = []
    for preset in BUILTIN_CODING_AGENTS:
        settings = settings_map.get(preset.id)
        if settings is not None and settings.hidden:
            removed.append(_builtin_entry(preset, None))
    return removed


def find_agent(
    agent_id: str,
    custom_agents: list[CodingAgentConfig],
    builtin_settings: BuiltinSettingsMap | None = None,
) -> CodingAgentConfig | None:
    settings_map = builtin_settings or {}
    for preset in BUILTIN_CODING_AGENTS:
        if preset.id == agent_id:
            settings = settings_map.get(preset.id)
            if settings is not None and settings.hidden:
                return None  # removed preset: behaves exactly like a deleted agent
            return CodingAgentConfig(
                id=preset.id,
                display_name=preset.display_name,
                executable=(settings.executable if settings and settings.executable else None)
                or preset.executable_candidates[0],
                args=settings.args if settings else (),
                built_in=True,
            )
    for agent in custom_agents:
        if agent.id == agent_id:
            return agent
    return None


def executable_candidates_for(
    agent: CodingAgentConfig,
    builtin_settings: BuiltinSettingsMap | None = None,
) -> tuple[str, ...]:
    """Candidate list to actually resolve at launch time."""
    for preset in BUILTIN_CODING_AGENTS:
        if preset.id == agent.id:
            settings = (builtin_settings or {}).get(preset.id)
            if settings is not None and settings.executable:
                return (settings.executable,)
            return preset.executable_candidates
    return (agent.executable,)


def visible_agent_names(
    custom_agents: list[CodingAgentConfig],
    builtin_settings: BuiltinSettingsMap | None = None,
) -> dict[str, str]:
    """id -> display name for every agent currently offered to the user."""
    settings_map = builtin_settings or {}
    names: dict[str, str] = {}
    for preset in BUILTIN_CODING_AGENTS:
        settings = settings_map.get(preset.id)
        if settings is None or not settings.hidden:
            names[preset.id] = preset.display_name
    for agent in custom_agents:
        names[agent.id] = agent.display_name
    return names


def builtin_override_for(
    agent: CodingAgentConfig, builtin_settings: BuiltinSettingsMap | None
) -> str | None:
    """The user-defined executable override for a built-in agent, if any."""
    if not agent.built_in:
        return None
    settings = (builtin_settings or {}).get(agent.id)
    return settings.executable if settings and settings.executable else None
