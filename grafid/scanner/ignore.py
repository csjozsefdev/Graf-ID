"""Directory ignore rules for filesystem scanning."""

from __future__ import annotations

import sys
from pathlib import Path

# Default folder names skipped anywhere in the project tree.
# Generated, vendor, cache, and build folders pollute workflow continuity
# signals (TODO/FIXME counts, resume summaries, startup headlines).
DEFAULT_IGNORED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "site-packages",
        "__pycache__",
        "dist",
        "build",
        "target",
        ".pytest_cache",
        ".cursor",
        "coverage",
        ".mypy_cache",
        ".tauri",
        ".next",
        "cache",
        "tmp",
        "temp",
    }
)

# Embedded/runtime paths where the directory name alone is too broad
# (e.g. keep grafid/runtime/ source but skip Tauri bundled Python trees).
DEFAULT_IGNORED_RELATIVE_PREFIXES: frozenset[str] = frozenset(
    {
        "desktop/src-tauri/runtime",
        "desktop/src-tauri/target",
        "desktop/dist",
        "desktop/node_modules",
    }
)


# Typical virtual-environment variants (".venv-314-dev", "venv-docs"): third-party
# code that must never feed markers, issues, next-step hints, snapshots or
# handoff exports. Deliberately narrow: only these exact prefixes, never a
# substring/glob like "*venv*" (which would hide "environment", "canvenv"...).
VENV_DIR_NAME_PREFIXES: tuple[str, ...] = (".venv-", "venv-")
VENV_EXACT_DIR_NAMES: frozenset[str] = frozenset({".venv", "venv", "site-packages"})


def _normalized_dir_name(name: str) -> str:
    return name.lower() if sys.platform == "win32" else name


def _normalize_relative_token(path: str) -> str:
    token = path.replace("\\", "/").strip("/")
    return token.lower() if sys.platform == "win32" else token


def build_ignore_lookup(dir_names: frozenset[str]) -> frozenset[str]:
    """Build a lookup set for fast directory name checks."""
    return frozenset(_normalized_dir_name(name) for name in dir_names)


def build_prefix_lookup(prefixes: frozenset[str]) -> frozenset[str]:
    """Normalize relative path prefixes for case-insensitive matching."""
    return frozenset(_normalize_relative_token(prefix) for prefix in prefixes)


def _relative_posix(path: Path, root: Path) -> str | None:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def is_virtualenv_dir_name(name: str) -> bool:
    """True for .venv, venv, site-packages, .venv-*, venv-* directory names."""
    normalized = _normalized_dir_name(name)
    return normalized in VENV_EXACT_DIR_NAMES or normalized.startswith(VENV_DIR_NAME_PREFIXES)


def _is_virtualenv_dir(path: Path) -> bool:
    """Name variants, plus any folder that self-identifies as a venv (pyvenv.cfg)."""
    if is_virtualenv_dir_name(path.name):
        return True
    try:
        return (path / "pyvenv.cfg").is_file()
    except OSError:
        return False


def is_ignored_relative_path(relative_path: str) -> bool:
    """
    True when a stored project-relative file path lives under an ignored or
    virtualenv directory. Used to keep third-party findings from an older scan
    out of summaries until the project is refreshed under the current rules.
    """
    segments = [seg for seg in relative_path.replace("\\", "/").split("/") if seg]
    ignored = build_ignore_lookup(DEFAULT_IGNORED_DIR_NAMES)
    for segment in segments[:-1]:
        if _normalized_dir_name(segment) in ignored or is_virtualenv_dir_name(segment):
            return True
    return False


def should_ignore_dir(
    path: Path,
    ignored_lookup: frozenset[str],
    *,
    root: Path | None = None,
    ignored_prefix_lookup: frozenset[str] | None = None,
) -> bool:
    """Return True when a directory should be skipped entirely."""
    if _normalized_dir_name(path.name) in ignored_lookup:
        return True
    if _is_virtualenv_dir(path):
        return True
    if root is None or not ignored_prefix_lookup:
        return False
    rel = _relative_posix(path, root)
    if rel is None:
        return False
    rel_norm = _normalize_relative_token(rel)
    for prefix in ignored_prefix_lookup:
        if rel_norm == prefix or rel_norm.startswith(f"{prefix}/"):
            return True
    return False
