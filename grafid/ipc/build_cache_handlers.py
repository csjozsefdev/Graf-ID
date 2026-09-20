"""IPC handlers for the Rust/Cargo build-cache detect/clean small improvement."""

from __future__ import annotations

from pathlib import Path

from grafid.config.manager import ConfigManager
from grafid.core.exceptions import GrafIdError
from grafid.ipc.envelope import IpcResponse, success
from grafid.ipc.errors import failure_from
from grafid.services.build_cache import (
    DetectedBuildCache,
    clean_rust_build_cache,
    detect_rust_build_caches,
)


def _cache_to_dict(cache: DetectedBuildCache) -> dict[str, object]:
    return {
        "kind": cache.kind,
        "manifest_path": cache.manifest_path,
        "target_path": cache.target_path,
        "size_bytes": cache.size_bytes,
    }


def handle_detect_build_caches(
    project_id: int,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """List Cargo build caches found under one registered project."""
    try:
        from grafid.services.runtime import prepare_runtime

        runtime = prepare_runtime(config_manager)
        record = runtime.registry.get_info(str(project_id))
        caches = detect_rust_build_caches(Path(record.path))
        return success({"caches": [_cache_to_dict(c) for c in caches]})
    except GrafIdError as exc:
        return failure_from(exc)


def handle_clean_build_cache(
    project_id: int,
    manifest_path: str,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """
    Run `cargo clean` for one build cache under a registered project.

    manifest_path is caller-supplied (echoed back from a prior detect call)
    but never trusted at face value — clean_rust_build_cache re-validates
    containment and symlink-safety against the project's own registered
    root before touching anything.
    """
    try:
        from grafid.services.runtime import prepare_runtime

        runtime = prepare_runtime(config_manager)
        record = runtime.registry.get_info(str(project_id))
        cleaned = clean_rust_build_cache(Path(record.path), manifest_path)
        return success({"cache": _cache_to_dict(cleaned)})
    except GrafIdError as exc:
        return failure_from(exc)
