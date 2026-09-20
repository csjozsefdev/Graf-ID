"""Composition root: initialised config, database and project registry.

Both front doors (the Typer CLI and the desktop IPC handlers) call
``prepare_runtime`` instead of wiring services themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from grafid.config.manager import ConfigManager
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.startup import StartupService

_runtime_cache: dict[str, AppRuntime] = {}


@dataclass(frozen=True)
class AppRuntime:
    """Initialized config, database, and project registry."""

    database_path: Path
    registry: ProjectRegistryService


def prepare_runtime(config_manager: ConfigManager | None = None) -> AppRuntime:
    """
    Ensure config, logging, database schema, and return a registry service.

    Reuses StartupService for consistent initialization without extra output.
    Cached per config directory within one Python process (IPC subprocess lifetime).
    """
    manager = config_manager or ConfigManager()
    cache_key = str(manager.config_dir.resolve())
    cached = _runtime_cache.get(cache_key)
    if cached is not None:
        return cached

    result = StartupService(config_manager=manager).run()
    runtime = AppRuntime(
        database_path=result.database_path,
        registry=ProjectRegistryService(result.database_path),
    )
    _runtime_cache[cache_key] = runtime
    return runtime


def reset_runtime_cache() -> None:
    """Forget the cached runtimes (used by tests and after the data folder changes)."""
    _runtime_cache.clear()
