"""IPC handler for resolving a Coding Agent launch (M7: no session, no lifecycle)."""

from __future__ import annotations

from grafid.services.runtime import prepare_runtime
from grafid.config.manager import ConfigManager
from grafid.core.exceptions import GrafIdError
from grafid.ipc.envelope import IpcResponse, failure, success
from grafid.ipc.errors import failure_from
from grafid.services.coding_agent_launch import (
    CodingAgentError,
    resolve_coding_agent_launch,
)


def handle_resolve_coding_agent_launch(
    agent_id: str,
    project_id: int,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """
    Resolve an agent + registered project into a launch spec for the desktop
    shell to spawn a terminal with (Rust-side — this handler never launches
    anything itself). Deliberately does not touch sessions, history, or any
    editor-lifecycle state.
    """
    try:
        manager = config_manager or ConfigManager()
        config = manager.load()
        runtime = prepare_runtime(manager)
        record = runtime.registry.get_info(str(project_id))
        spec = resolve_coding_agent_launch(
            agent_id,
            record.path,
            custom_agents=config.coding_agents,
            builtin_settings=config.builtin_agents,
        )
        return success(
            {
                "executable": spec.executable,
                "args": list(spec.args),
                "cwd": spec.cwd,
                "display_name": spec.display_name,
            }
        )
    except CodingAgentError as exc:
        return failure("coding_agent_error", str(exc))
    except GrafIdError as exc:
        return failure_from(exc)
