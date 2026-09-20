"""Development vs packaged runtime layout resolution."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from grafid.config.paths import resolve_app_config_dir
from grafid.core.constants import CONFIG_FILENAME, DB_FILENAME, LOG_DIR_NAME


RuntimeMode = str  # "development" | "packaged"


@dataclass(frozen=True)
class RuntimeLayout:
    """Resolved paths used by CLI, IPC, and the Tauri shell."""

    mode: RuntimeMode
    data_dir: Path
    config_path: Path
    database_path: Path
    log_dir: Path
    resource_root: Path | None
    python_executable: Path | None
    notes: tuple[str, ...]


def detect_runtime_mode() -> RuntimeMode:
    """
    Infer runtime mode from environment.

    Packaged mode is explicit via GRAFID_RUNTIME_MODE=packaged or when
    GRAFID_PYTHON is set (embedded interpreter from the desktop shell).
    """
    explicit = os.environ.get("GRAFID_RUNTIME_MODE", "").strip().lower()
    if explicit in ("development", "dev"):
        return "development"
    if explicit in ("packaged", "production", "release"):
        return "packaged"
    if os.environ.get("GRAFID_PYTHON"):
        return "packaged"
    if os.environ.get("GRAFID_RESOURCE_ROOT"):
        return "packaged"
    return "development"


def resolve_resource_root() -> Path | None:
    """Directory containing the grafid Python package for PYTHONPATH."""
    if env_root := os.environ.get("GRAFID_RESOURCE_ROOT"):
        candidate = Path(env_root).expanduser()
        if candidate.is_dir():
            return candidate.resolve()

    if env_python := os.environ.get("GRAFID_PYTHON"):
        runtime_dir = Path(env_python).expanduser().resolve().parent
        site_packages = runtime_dir / "Lib" / "site-packages"
        if site_packages.is_dir():
            return site_packages
        return runtime_dir

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    # Development: repository root (parent of grafid package)
    return Path(__file__).resolve().parents[2]


def resolve_python_executable() -> Path | None:
    """Optional explicit Python interpreter (embedded runtime or venv)."""
    if env_python := os.environ.get("GRAFID_PYTHON"):
        candidate = Path(env_python).expanduser()
        if candidate.is_file():
            return candidate.resolve()
    return None


def resolve_runtime_layout(
    *,
    config_dir_override: Path | None = None,
) -> RuntimeLayout:
    """
    Build a consistent layout for config, database, logs, and optional bundle paths.

    User data always lives under data_dir (never inside the install folder unless
    GRAFID_DATA_DIR points there). Install/bundle files use resource_root.
    """
    mode = detect_runtime_mode()
    data_dir = resolve_app_config_dir(config_dir_override)
    config_path = data_dir / CONFIG_FILENAME
    log_dir = (data_dir / LOG_DIR_NAME).resolve()
    database_path = (data_dir / DB_FILENAME).resolve()

    resource_root = resolve_resource_root()
    python_executable = resolve_python_executable()

    notes: list[str] = []
    if mode == "packaged":
        notes.append("Packaged runtime: user data separated from install directory.")
        if python_executable is None:
            notes.append("GRAFID_PYTHON not set; desktop shell must provide interpreter.")
    else:
        notes.append("Development runtime: repo venv or system Python expected.")

    return RuntimeLayout(
        mode=mode,
        data_dir=data_dir,
        config_path=config_path,
        database_path=database_path,
        log_dir=log_dir,
        resource_root=resource_root,
        python_executable=python_executable,
        notes=tuple(notes),
    )
