"""The canonical IPC command table.

Every desktop command (and every ``graf-id ipc <command>`` terminal command,
which is a thin passthrough to :func:`main`) is registered once in ``COMMANDS``.
Handler modules are imported lazily so a desktop call only loads what it uses.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from grafid.ipc.envelope import emit_response
from grafid.ipc.stdio_config import configure_ipc_stdio_utf8


def _bool_flag(rest: list[str], name: str) -> bool:
    return name in rest or f"--{name}" in rest


def _opt(rest: list[str], *flags: str) -> str | None:
    for i, token in enumerate(rest):
        if token in flags and i + 1 < len(rest):
            return rest[i + 1]
    return None


def _require_int(rest: list[str], index: int = 0) -> int:
    if len(rest) <= index:
        raise SystemExit(2)
    return int(rest[index])


def _dispatch_health(_rest: list[str]) -> Any:
    from grafid.ipc.handlers import handle_health

    return handle_health()


def _dispatch_usage_insights(_rest: list[str]) -> Any:
    from grafid.ipc.usage_handlers import handle_usage_insights

    return handle_usage_insights()


def _dispatch_app_settings(_rest: list[str]) -> Any:
    from grafid.ipc.settings_handlers import handle_get_app_settings

    return handle_get_app_settings()


def _dispatch_save_app_settings(rest: list[str]) -> Any:
    from grafid.ipc.settings_handlers import handle_save_app_settings

    return handle_save_app_settings(
        _opt(rest, "--opener") or "system",
        _opt(rest, "--usage-journal") or "false",
        _opt(rest, "--debug-timing") or "false",
        _opt(rest, "--compact-mode") or "false",
        python_interpreter_mode=_opt(rest, "--python-interpreter-mode"),
        python_interpreter_custom_path=_opt(rest, "--python-interpreter-custom-path"),
        custom_opener_path=_opt(rest, "--custom-opener-path"),
        coding_agents=_opt(rest, "--coding-agents"),
        builtin_agents=_opt(rest, "--builtin-agents"),
    )


def _dispatch_resolve_coding_agent_launch(rest: list[str]) -> Any:
    from grafid.ipc.coding_agent_handlers import handle_resolve_coding_agent_launch

    if not rest:
        raise SystemExit(2)
    return handle_resolve_coding_agent_launch(rest[0], _require_int(rest, 1))


def _dispatch_reset_app_settings(_rest: list[str]) -> Any:
    from grafid.ipc.settings_handlers import handle_reset_app_settings

    return handle_reset_app_settings()


def _dispatch_set_default_project_opener(rest: list[str]) -> Any:
    from grafid.ipc.settings_handlers import handle_set_default_project_opener

    if not rest:
        raise SystemExit(2)
    return handle_set_default_project_opener(rest[0])


def _dispatch_runtime_check(rest: list[str]) -> Any:
    from grafid.ipc.handlers import handle_runtime_check

    return handle_runtime_check(run_full_startup=_bool_flag(rest, "full"))


def _dispatch_bootstrap(rest: list[str]) -> Any:
    from grafid.ipc.handlers import handle_bootstrap

    return handle_bootstrap()


def _dispatch_list_projects(_rest: list[str]) -> Any:
    from grafid.ipc.handlers import handle_list_projects

    return handle_list_projects()


def _dispatch_add_project(rest: list[str]) -> Any:
    from grafid.ipc.project_handlers import handle_add_project

    if len(rest) < 2:
        raise SystemExit(2)
    return handle_add_project(
        rest[0], rest[1], category=_opt(rest, "--category") or "Personal Projects"
    )


def _dispatch_remove_project(rest: list[str]) -> Any:
    from grafid.ipc.project_handlers import handle_remove_project

    return handle_remove_project(_require_int(rest))


def _dispatch_update_project(rest: list[str]) -> Any:
    from grafid.ipc.project_handlers import handle_update_project

    return handle_update_project(
        _require_int(rest),
        name=_opt(rest, "--name"),
        path=_opt(rest, "--path"),
        category=_opt(rest, "--category"),
        status=_opt(rest, "--status"),
        notes=_opt(rest, "--notes"),
    )


def _dispatch_reorder_projects(rest: list[str]) -> Any:
    from grafid.ipc.project_handlers import handle_reorder_projects

    if not rest:
        raise SystemExit(2)
    ordered_ids = [int(token) for token in rest[0].split(",") if token.strip()]
    return handle_reorder_projects(ordered_ids)


def _dispatch_dashboard(_rest: list[str]) -> Any:
    from grafid.ipc.dashboard_handlers import handle_dashboard

    return handle_dashboard()


def _dispatch_project_detail(rest: list[str]) -> Any:
    from grafid.ipc.dashboard_handlers import handle_project_detail

    return handle_project_detail(_require_int(rest))


def _dispatch_project_history(rest: list[str]) -> Any:
    from grafid.ipc.dashboard_handlers import handle_project_history

    limit = int(_opt(rest, "--limit") or "15")
    return handle_project_history(_require_int(rest), limit=limit)


def _dispatch_open_folder(rest: list[str]) -> Any:
    from grafid.ipc.dashboard_handlers import handle_open_folder

    return handle_open_folder(_require_int(rest))


def _dispatch_open_project(rest: list[str]) -> Any:
    from grafid.ipc.dashboard_handlers import handle_open_project

    return handle_open_project(_require_int(rest))


def _dispatch_refresh_resume(rest: list[str]) -> Any:
    from grafid.ipc.dashboard_handlers import handle_refresh_resume

    return handle_refresh_resume(
        _require_int(rest), git_only=_bool_flag(rest, "git-only")
    )


def _dispatch_start_session(rest: list[str]) -> Any:
    from grafid.ipc.session_handlers import handle_start_session

    return handle_start_session(
        _require_int(rest), checkpoint=_opt(rest, "--checkpoint")
    )


def _dispatch_session_timeline(rest: list[str]) -> Any:
    from grafid.ipc.session_handlers import handle_session_timeline

    limit = int(_opt(rest, "--limit") or "10")
    return handle_session_timeline(_require_int(rest), limit=limit)


def _session_close_args(rest: list[str]) -> dict[str, Any]:
    return {
        "project_id": _require_int(rest),
        "exit_note": _opt(rest, "--exit-note"),
        "unfinished": _opt(rest, "--unfinished"),
        "blocker": _opt(rest, "--blocker"),
        "next_step": _opt(rest, "--next-step"),
        "skip_notes": _bool_flag(rest, "skip-notes"),
    }


def _dispatch_close_session(rest: list[str]) -> Any:
    from grafid.ipc.session_handlers import handle_close_session

    return handle_close_session(**_session_close_args(rest))


def _dispatch_end_session(rest: list[str]) -> Any:
    from grafid.ipc.session_handlers import handle_end_session

    return handle_end_session(**_session_close_args(rest))


def _dispatch_export_project_summary(rest: list[str]) -> Any:
    from grafid.ipc.export_handlers import handle_export_project_summary

    export_format = _opt(rest, "--format")
    if export_format is None:
        raise SystemExit(2)
    return handle_export_project_summary(
        _require_int(rest),
        export_format=export_format,
        output_path=_opt(rest, "--path"),
    )


def _dispatch_export_grafitalk_inbox(rest: list[str]) -> Any:
    from grafid.ipc.export_handlers import handle_export_grafitalk_inbox

    if not rest:
        raise SystemExit(2)
    return handle_export_grafitalk_inbox(rest[0])


def _dispatch_create_backup(rest: list[str]) -> Any:
    from grafid.ipc.backup_handlers import handle_create_backup

    if not rest:
        raise SystemExit(2)
    return handle_create_backup(rest[0], include_settings=_bool_flag(rest, "include-settings"))


def _dispatch_restore_backup(rest: list[str]) -> Any:
    from grafid.ipc.backup_handlers import handle_restore_backup

    if not rest:
        raise SystemExit(2)
    return handle_restore_backup(rest[0], restore_settings=_bool_flag(rest, "restore-settings"))


def _dispatch_preview_context_import(rest: list[str]) -> Any:
    from grafid.ipc.import_handlers import handle_preview_context_import

    if len(rest) < 2:
        raise SystemExit(2)
    return handle_preview_context_import(_require_int(rest), rest[1])


def _dispatch_apply_context_import(rest: list[str]) -> Any:
    from grafid.ipc.import_handlers import handle_apply_context_import

    if len(rest) < 2:
        raise SystemExit(2)
    return handle_apply_context_import(
        _require_int(rest),
        rest[1],
        mode=_opt(rest, "--mode") or "append",
        fingerprint=_opt(rest, "--fingerprint") or "",
        confirmed=_bool_flag(rest, "confirm"),
    )


def _dispatch_detect_build_caches(rest: list[str]) -> Any:
    from grafid.ipc.build_cache_handlers import handle_detect_build_caches

    return handle_detect_build_caches(_require_int(rest))


def _dispatch_clean_build_cache(rest: list[str]) -> Any:
    from grafid.ipc.build_cache_handlers import handle_clean_build_cache

    manifest_path = _opt(rest, "--manifest-path")
    if manifest_path is None:
        raise SystemExit(2)
    return handle_clean_build_cache(_require_int(rest), manifest_path)


COMMANDS: dict[str, Callable[[list[str]], Any]] = {
    "health": _dispatch_health,
    "usage-insights": _dispatch_usage_insights,
    "app-settings": _dispatch_app_settings,
    "save-app-settings": _dispatch_save_app_settings,
    "reset-app-settings": _dispatch_reset_app_settings,
    "resolve-coding-agent-launch": _dispatch_resolve_coding_agent_launch,
    "set-default-project-opener": _dispatch_set_default_project_opener,
    "runtime-check": _dispatch_runtime_check,
    "bootstrap": _dispatch_bootstrap,
    "list-projects": _dispatch_list_projects,
    "add-project": _dispatch_add_project,
    "remove-project": _dispatch_remove_project,
    "update-project": _dispatch_update_project,
    "reorder-projects": _dispatch_reorder_projects,
    "dashboard": _dispatch_dashboard,
    "project-detail": _dispatch_project_detail,
    "project-history": _dispatch_project_history,
    "open-folder": _dispatch_open_folder,
    "open-project": _dispatch_open_project,
    "refresh-resume": _dispatch_refresh_resume,
    "start-session": _dispatch_start_session,
    "session-timeline": _dispatch_session_timeline,
    "close-session": _dispatch_close_session,
    "end-session": _dispatch_end_session,
    "export-project-summary": _dispatch_export_project_summary,
    "export-grafitalk-inbox": _dispatch_export_grafitalk_inbox,
    "create-backup": _dispatch_create_backup,
    "preview-context-import": _dispatch_preview_context_import,
    "apply-context-import": _dispatch_apply_context_import,
    "restore-backup": _dispatch_restore_backup,
    "detect-build-caches": _dispatch_detect_build_caches,
    "clean-build-cache": _dispatch_clean_build_cache,
}


def dispatch(command: str, rest: list[str]) -> Any:
    """Run one IPC command and return the handler payload (before envelope)."""
    handler = COMMANDS.get(command)
    if handler is None:
        raise SystemExit(2)
    return handler(rest)


def usage() -> str:
    """One-line usage plus the command list (printed for ``--help``)."""
    return "usage: graf-id ipc <command> [args]\ncommands: " + ", ".join(sorted(COMMANDS))


def main(argv: list[str] | None = None) -> int:
    configure_ipc_stdio_utf8()
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        return 2
    command, rest = args[0], args[1:]
    if command in ("--help", "-h") or (command in COMMANDS and ("--help" in rest or "-h" in rest)):
        sys.stdout.write(usage() + "\n")
        return 0
    emit_response(dispatch(command, rest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
