"""Startup validation for development and packaged runtimes."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from grafid.config.manager import ConfigManager
from grafid.core.constants import SCHEMA_VERSION
from grafid.core.exceptions import ConfigError, DatabaseError, StartupError
from grafid.db.schema import get_schema_version
from grafid.packaging.runtime import resolve_runtime_layout
from grafid.services.db_init import DatabaseInitService
from grafid.services.startup import StartupService


@dataclass(frozen=True)
class RuntimeValidationReport:
    """Result of a packaging-oriented startup check."""

    ok: bool
    mode: str
    data_dir: str
    config_path: str
    database_path: str
    log_dir: str
    resource_root: str | None
    python_executable: str | None
    schema_version: int | None
    config_valid: bool
    database_ok: bool
    issues: tuple[str, ...]
    notes: tuple[str, ...]


def validate_runtime(
    *,
    config_dir_override: Path | None = None,
    run_full_startup: bool = False,
) -> RuntimeValidationReport:
    """
    Validate paths and optionally run full StartupService initialization.

    Set run_full_startup=True for a deeper check (creates DB if missing).
    """
    layout = resolve_runtime_layout(config_dir_override=config_dir_override)
    issues: list[str] = []
    config_valid = False
    database_ok = False
    schema_version: int | None = None

    try:
        layout.data_dir.mkdir(parents=True, exist_ok=True)
        layout.log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        issues.append(f"Cannot create data directories: {exc}")

    if layout.python_executable is not None and not layout.python_executable.is_file():
        issues.append(f"GRAFID_PYTHON missing: {layout.python_executable}")

    if layout.resource_root is not None and not layout.resource_root.is_dir():
        issues.append(f"GRAFID_RESOURCE_ROOT missing: {layout.resource_root}")

    try:
        manager = ConfigManager(config_dir=layout.data_dir)
        if manager.config_path.exists():
            json.loads(manager.config_path.read_text(encoding="utf-8"))
        manager.load()
        config_valid = True
    except (ConfigError, json.JSONDecodeError, OSError) as exc:
        issues.append(f"Config invalid or unreadable: {exc}")

    try:
        if run_full_startup:
            StartupService(config_manager=ConfigManager(config_dir=layout.data_dir)).run()
        else:
            DatabaseInitService(layout.database_path).initialize(verify=True)
        database_ok = True
        with sqlite3.connect(layout.database_path) as conn:
            schema_version = get_schema_version(conn)
    except (DatabaseError, StartupError, sqlite3.Error, OSError) as exc:
        issues.append(f"Database check failed: {exc}")

    if schema_version is not None and schema_version != SCHEMA_VERSION:
        issues.append(
            f"Schema version mismatch: db={schema_version} expected={SCHEMA_VERSION}"
        )
        database_ok = False

    ok = not issues and config_valid and database_ok
    return RuntimeValidationReport(
        ok=ok,
        mode=layout.mode,
        data_dir=str(layout.data_dir),
        config_path=str(layout.config_path),
        database_path=str(layout.database_path),
        log_dir=str(layout.log_dir),
        resource_root=str(layout.resource_root) if layout.resource_root else None,
        python_executable=(
            str(layout.python_executable) if layout.python_executable else None
        ),
        schema_version=schema_version,
        config_valid=config_valid,
        database_ok=database_ok,
        issues=tuple(issues),
        notes=layout.notes,
    )


def report_to_dict(report: RuntimeValidationReport) -> dict:
    """Serialize for IPC JSON responses."""
    return asdict(report)
