"""IPC handlers — delegate to existing services (no duplicate business logic)."""

from __future__ import annotations

from typing import Any

from grafid.config.manager import ConfigManager
from grafid.core.constants import SCHEMA_VERSION
from grafid.core.exceptions import (
    ConfigError,
    DatabaseError,
    GrafIdError,
    GrafPermissionError,
    StartupError,
)
from grafid.ipc.envelope import IpcResponse, failure, success
from grafid.ipc.errors import error_code, failure_from
from grafid.services.project_registry import ProjectRegistryService
from grafid.observability.journal import record_event
from grafid.observability.timing import new_timing_collector, timed_block
from grafid.packaging.bootstrap import describe_layout
from grafid.packaging.validation import report_to_dict, validate_runtime
from grafid.services.startup import StartupService


def handle_health() -> IpcResponse:
    """Lightweight check that the Python runtime can load config paths."""
    try:
        manager = ConfigManager()
        config = manager.load()
        config_dir = manager.config_dir
        db_path = config.resolved_database_path(config_dir)
        layout_info = describe_layout()
        return success(
            {
                "app": "graf-id",
                "schema_version": SCHEMA_VERSION,
                "config_dir": str(config_dir),
                "database_path": str(db_path),
                "config_readable": True,
                "runtime_mode": layout_info["mode"],
                "data_dir": layout_info["data_dir"],
                "resource_root": layout_info["resource_root"],
            }
        )
    except (ConfigError, GrafPermissionError) as exc:
        return failure("config_error", str(exc))
    except GrafIdError as exc:
        return failure("runtime_error", str(exc))


def handle_runtime_check(*, run_full_startup: bool = False) -> IpcResponse:
    """Packaging-oriented validation: paths, config JSON, database integrity."""
    report = validate_runtime(run_full_startup=run_full_startup)
    payload = report_to_dict(report)
    if report.ok:
        return success(payload)
    return failure(
        "runtime_validation_failed",
        "; ".join(report.issues) if report.issues else "Runtime validation failed",
        data=payload,
    )


def handle_bootstrap(
    *,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """
    Initialize config + database, verify integrity and list projects.

    Mirrors CLI startup without Typer output.
    """
    manager = config_manager or ConfigManager()
    config = manager.bootstrap_defaults()
    timing = new_timing_collector(config)
    try:
        with timed_block("startup", timing):
            startup = StartupService(config_manager=manager).run()
        registry = ProjectRegistryService(startup.database_path)
        project_records = registry.list_projects()
        from grafid.services.project_overview import build_bootstrap_projects
        from grafid.ipc.settings_handlers import handle_get_app_settings

        with timed_block("dashboard_projects", timing, count=len(project_records)):
            projects = build_bootstrap_projects(startup.database_path, project_records)

        settings_resp = handle_get_app_settings(manager)
        app_settings = settings_resp.data if settings_resp.ok else None

        payload: dict[str, Any] = {
            "config_dir": str(startup.config_dir),
            "config_path": str(startup.config_path),
            "database_path": str(startup.database_path),
            "schema_version": SCHEMA_VERSION,
            "projects": projects,
            "app_settings": app_settings,
        }
        if timing.enabled:
            payload["debug_timings"] = timing.as_list()

        record_event(
            "ipc.bootstrap",
            config_dir=manager.config_dir,
            config=config,
            project_count=len(projects),
        )
        return success(payload)
    except (StartupError, ConfigError, DatabaseError, GrafPermissionError) as exc:
        record_event(
            "ipc.bootstrap_failed",
            config_dir=manager.config_dir,
            config=config,
            error=error_code(exc),
        )
        return failure_from(exc)
    except GrafIdError as exc:
        return failure("runtime_error", str(exc))


def handle_list_projects(
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Return registered projects after the same runtime bootstrap as CLI commands."""
    try:
        from grafid.services.project_overview import project_to_dict
        from grafid.services.runtime import prepare_runtime

        runtime = prepare_runtime(config_manager)
        projects = [
            project_to_dict(record) for record in runtime.registry.list_projects()
        ]
        return success(
            {
                "database_path": str(runtime.database_path),
                "projects": projects,
            }
        )
    except (ConfigError, DatabaseError, StartupError, GrafPermissionError) as exc:
        return failure_from(exc)
    except GrafIdError as exc:
        return failure("runtime_error", str(exc))
