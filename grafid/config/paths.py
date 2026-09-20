"""Filesystem paths for local Graf-Id data."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from grafid.core.constants import CONFIG_DIR_NAME


def resolve_app_config_dir(override: Path | None = None) -> Path:
    """
    Resolve the application config directory.

    Priority: explicit override (tests), GRAFID_DATA_DIR (packaged/desktop),
    then a stable per-user location (LOCALAPPDATA on Windows, XDG elsewhere).
    """
    if override is not None:
        return override.expanduser().resolve()

    if env_data := os.environ.get("GRAFID_DATA_DIR"):
        return Path(env_data).expanduser().resolve()

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return (Path(base) / CONFIG_DIR_NAME).resolve()
        return (Path.home() / CONFIG_DIR_NAME).resolve()

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return (Path(xdg_config) / "graf-id").resolve()
    return (Path.home() / ".config" / "graf-id").resolve()
