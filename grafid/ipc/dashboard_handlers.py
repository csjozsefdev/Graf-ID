"""Dashboard IPC - aggregate existing DB/services for the desktop UI."""

from __future__ import annotations

from typing import Any
from grafid.config.manager import ConfigManager
from grafid.core.exceptions import GrafIdError, ProjectError, ValidationError
from grafid.db.connection import DatabaseConnection
from grafid.ipc.envelope import IpcResponse, failure, success
from grafid.ipc.errors import failure_from
from grafid.services.history_display import build_history_display_rows
from grafid.services.project_overview import (
    HISTORY_LIMIT_DEFAULT,
    build_dashboard_item,
    build_resume_panel,
    public_dashboard_item,
    resolve_project,
)
from grafid.services.refresh_result import RefreshResult
from grafid.services.resume_service import ResumeService
from grafid.services.workflow_launch import WorkflowLaunchError, WorkflowLaunchService
from grafid.utils.logging_setup import get_logger

logger = get_logger("ipc.dashboard")


def handle_dashboard(config_manager: ConfigManager | None = None) -> IpcResponse:
    """Project list with session, summary, and git status for the dashboard."""
    try:
        from grafid.services.runtime import prepare_runtime

        runtime = prepare_runtime(config_manager)
        with DatabaseConnection(runtime.database_path) as conn:
            items = [
                public_dashboard_item(
                    build_dashboard_item(conn, runtime.database_path, record)
                )
                for record in runtime.registry.list_projects()
            ]
        return success(
            {
                "database_path": str(runtime.database_path),
                "projects": items,
            }
        )
    except GrafIdError as exc:
        return failure_from(exc)


def handle_project_detail(
    project_id: int,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Resume panel and detail view for one selected project."""
    try:
        from grafid.services.runtime import prepare_runtime

        runtime = prepare_runtime(config_manager)
        record = resolve_project(runtime.registry, project_id)

        with DatabaseConnection(runtime.database_path) as conn:
            item = build_dashboard_item(conn, runtime.database_path, record)
            summary_block = item.pop("_summary_block", None)
            resume_panel = build_resume_panel(
                runtime.database_path,
                project_id,
                item,
                startup_block=summary_block,
            )

        return success(
            {
                "project": item,
                "resume_panel": resume_panel,
            }
        )
    except ProjectError as exc:
        return failure("project_error", str(exc))
    except GrafIdError as exc:
        return failure_from(exc)


def handle_refresh_resume(
    project_id: int,
    config_manager: ConfigManager | None = None,
    *,
    git_only: bool = False,
) -> IpcResponse:
    """Re-scan project sources, regenerate resume, return fresh detail."""
    try:
        from grafid.services.runtime import prepare_runtime
        from grafid.observability.timing import new_timing_collector, timed_block
        from grafid.services.context_refresh import refresh_project_scan

        manager = config_manager or ConfigManager()
        timing = new_timing_collector(manager.bootstrap_defaults())
        runtime = prepare_runtime(manager)
        record = resolve_project(runtime.registry, project_id)

        with timed_block(
            "ipc.refresh_resume",
            timing,
            project_id=project_id,
            git_only=git_only,
        ):
            # H4: last_refreshed_at is now set atomically inside refresh_project_scan
            # itself (same transaction as the snapshot/retention writes) — no
            # separate write here.
            refresh_result = refresh_project_scan(
                runtime.database_path, project_id, git_only=git_only
            )
            refreshed_at = refresh_result.last_refreshed_at

            ResumeService(runtime.database_path).generate_resume(
                project_id, mode="short", persist=True, replace_latest_short=True
            )
            record = resolve_project(runtime.registry, project_id)
            with DatabaseConnection(runtime.database_path) as conn:
                item = build_dashboard_item(conn, runtime.database_path, record)
                summary_block = item.pop("_summary_block", None)
                resume_panel = build_resume_panel(
                    runtime.database_path,
                    project_id,
                    item,
                    startup_block=summary_block,
                )

            changed_files = tuple(resume_panel.get("modified_files") or ())
            top_sources = tuple(summary_block.get("sources_used") or []) if summary_block else ()
            refresh_result = RefreshResult(
                **{
                    **refresh_result.to_dict(),
                    "top_summary_sources": top_sources,
                    "changed_files_seen": changed_files,
                    "cache_used": False,
                }
            )

            payload: dict[str, Any] = {
                "project": item,
                "resume_panel": resume_panel,
                "last_refreshed_at": refreshed_at,
                "refresh": refresh_result.to_dict(),
            }
            if timing.enabled:
                payload["debug_timings"] = timing.as_list()
            return success(payload)
    except ProjectError as exc:
        return failure("project_error", str(exc))
    except GrafIdError as exc:
        return failure_from(exc)


def handle_project_history(
    project_id: int,
    *,
    limit: int = HISTORY_LIMIT_DEFAULT,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Scan history rows for the history section."""
    try:
        from grafid.services.runtime import prepare_runtime

        runtime = prepare_runtime(config_manager)
        project = resolve_project(runtime.registry, project_id)
        history = build_history_display_rows(
            project_id=project_id,
            project_name=str(project.name),
            db_path=runtime.database_path,
            limit=limit,
        )
        return success(
            {
                "project_id": project_id,
                "history": history,
            }
        )
    except ProjectError as exc:
        return failure("project_error", str(exc))
    except GrafIdError as exc:
        return failure_from(exc)


def handle_open_folder(
    project_id: int,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Open the registered project directory in the file manager (CLI/IPC)."""
    try:
        from grafid.services.runtime import prepare_runtime

        runtime = prepare_runtime(config_manager)
        record = resolve_project(runtime.registry, project_id)
        launcher = WorkflowLaunchService(runtime.database_path, runtime.registry)
        payload = launcher.open_folder(record.path)
        return success({"project_id": project_id, **payload})
    except WorkflowLaunchError as exc:
        return failure("launch_failed", str(exc))
    except ValidationError as exc:
        return failure("launch_failed", str(exc))
    except ProjectError as exc:
        return failure("project_error", str(exc))
    except GrafIdError as exc:
        return failure_from(exc)


def handle_open_project(
    project_id: int,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Resume workflow: session, editor launch, or Explorer fallback."""
    try:
        from grafid.services.runtime import prepare_runtime

        runtime = prepare_runtime(config_manager)
        manager = config_manager or ConfigManager()
        config = manager.load()
        launcher = WorkflowLaunchService(runtime.database_path, runtime.registry)
        # Desktop opens Explorer via Rust; avoid duplicate Explorer from Python.
        updated, outcome = launcher.open_project(
            project_id, config=config, launch_explorer=False
        )
        with DatabaseConnection(runtime.database_path) as conn:
            project_item = public_dashboard_item(
                build_dashboard_item(conn, runtime.database_path, updated)
            )
        return success(
            {
                "project": project_item,
                "launch": outcome.to_dict(),
            }
        )
    except WorkflowLaunchError as exc:
        return failure("launch_failed", str(exc))
    except ValidationError as exc:
        return failure("launch_failed", str(exc))
    except ProjectError as exc:
        return failure("project_error", str(exc))
    except GrafIdError as exc:
        return failure_from(exc)
