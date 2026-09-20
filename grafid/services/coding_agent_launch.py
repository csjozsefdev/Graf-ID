"""Resolve a Coding Agent launch spec (executable, args, cwd).

Deliberately separate from grafid/services/workflow_launch.py: coding
agents get no work session, no process-lifecycle tracking, and no Exit
Note (M7). This module only resolves WHAT to launch and WHERE — the
actual terminal spawn is Rust-side (desktop/src-tauri/src/shell.rs), and
Graf-Id does not track the resulting process at all once it exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from grafid.config.coding_agents import (
    BuiltinSettingsMap,
    CodingAgentConfig,
    builtin_override_for,
    describe_invalid_explicit_path,
    executable_candidates_for,
    find_agent,
    resolve_agent_executable,
    resolve_override_executable,
)
from grafid.core.exceptions import GrafIdError
from grafid.services.project_validation import normalize_project_path


class CodingAgentError(GrafIdError):
    """User-facing failure resolving or launching a coding agent."""


@dataclass(frozen=True)
class CodingAgentLaunchSpec:
    """Everything Rust needs to open a terminal and run the agent in it."""

    executable: str
    args: tuple[str, ...]
    cwd: str
    display_name: str


def resolve_coding_agent_launch(
    agent_id: str,
    project_path: str,
    *,
    custom_agents: list[CodingAgentConfig],
    builtin_settings: BuiltinSettingsMap | None = None,
) -> CodingAgentLaunchSpec:
    """
    Resolve an agent id + project path into a launch spec.

    Raises CodingAgentError with a specific, user-facing reason if the
    agent is unknown, its executable can't be resolved, or the project
    path is invalid — never silently falls back to "launch succeeded".
    """
    agent = find_agent(agent_id, custom_agents, builtin_settings)
    if agent is None:
        raise CodingAgentError(
            f"Coding agent '{agent_id}' is not configured. "
            "It may have been removed — choose another opener in Settings."
        )

    try:
        folder = normalize_project_path(project_path)
    except Exception as exc:  # noqa: BLE001 — surface as a launch failure, not a crash
        raise CodingAgentError(f"Project folder is not valid: {exc}") from exc
    if not folder.is_dir():
        raise CodingAgentError(f"Project folder does not exist: {folder}")

    override = builtin_override_for(agent, builtin_settings)
    if override is not None:
        # A user-defined override wins over PATH detection, and a broken one is
        # reported as such — never silently replaced by another executable.
        resolved, reason = resolve_override_executable(override)
        if resolved is None:
            raise CodingAgentError(
                f"{agent.display_name}: {reason} Fix or clear the executable path in Settings."
            )
    else:
        candidates = executable_candidates_for(agent, builtin_settings)
        resolved = resolve_agent_executable(candidates)
        if resolved is None:
            if not agent.built_in:
                reason = describe_invalid_explicit_path(agent.executable)
                if reason:
                    raise CodingAgentError(reason)
            raise CodingAgentError(
                f"{agent.display_name} was not found on PATH. "
                "Install it, add it to PATH, or update its command in Settings."
            )

    return CodingAgentLaunchSpec(
        executable=resolved,
        args=agent.args,
        cwd=str(folder.resolve()),
        display_name=agent.display_name,
    )
