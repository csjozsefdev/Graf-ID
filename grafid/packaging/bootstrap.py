"""Helpers for desktop shell startup (Python side)."""

from __future__ import annotations

from grafid.packaging.runtime import RuntimeLayout, resolve_runtime_layout


def describe_layout(layout: RuntimeLayout | None = None) -> dict[str, str | None]:
    """Serialize layout for health IPC payloads."""
    layout = layout or resolve_runtime_layout()
    return {
        "mode": layout.mode,
        "data_dir": str(layout.data_dir),
        "config_path": str(layout.config_path),
        "database_path": str(layout.database_path),
        "log_dir": str(layout.log_dir),
        "resource_root": str(layout.resource_root) if layout.resource_root else None,
        "python_executable": (
            str(layout.python_executable) if layout.python_executable else None
        ),
    }
