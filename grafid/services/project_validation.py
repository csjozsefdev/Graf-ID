"""Filesystem validation for project registration."""

from __future__ import annotations

import os
from pathlib import Path

from grafid.core.constants import MAX_FREE_TEXT_FIELD_CHARS
from grafid.core.exceptions import ValidationError
from grafid.core.project_categories import (
    DEFAULT_PROJECT_CATEGORY,
    PROJECT_CATEGORIES,
)
from grafid.core.project_status import DEFAULT_PROJECT_STATUS, PROJECT_STATUSES
from grafid.utils.logging_setup import get_logger

logger = get_logger("project_validation")


def normalize_name(name: str) -> str:
    """Strip whitespace and reject empty project names."""
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("Project name cannot be empty")
    return cleaned


def normalize_project_path(raw_path: str) -> Path:
    """
    Resolve and validate a project directory path.

    Ensures the path exists, is a directory, and is readable.
    """
    if not raw_path or not raw_path.strip():
        raise ValidationError("Project path cannot be empty")

    try:
        resolved = Path(raw_path).expanduser().resolve()
    except OSError as exc:
        logger.warning("Path resolution failed for %s: %s", raw_path, exc)
        raise ValidationError(f"Cannot resolve path: {raw_path}") from exc

    if not resolved.exists():
        logger.warning("Path does not exist: %s", resolved)
        raise ValidationError(f"Path does not exist: {resolved}")

    if not resolved.is_dir():
        logger.warning("Path is not a directory: %s", resolved)
        raise ValidationError(f"Path is not a directory: {resolved}")

    try:
        os.listdir(resolved)
    except PermissionError as exc:
        logger.warning("Permission denied for path: %s", resolved)
        raise ValidationError(f"Cannot access directory: {resolved}") from exc
    except OSError as exc:
        logger.warning("Cannot access path %s: %s", resolved, exc)
        raise ValidationError(f"Cannot access directory: {resolved}") from exc

    return resolved


def path_storage_value(resolved: Path) -> str:
    """Canonical string form for storing and comparing paths."""
    return str(resolved)


def normalize_category(category: str | None) -> str:
    """Validate and normalize a project category label."""
    if category is None or not category.strip():
        return DEFAULT_PROJECT_CATEGORY
    cleaned = " ".join(category.strip().split())
    if cleaned not in PROJECT_CATEGORIES:
        allowed = ", ".join(PROJECT_CATEGORIES)
        raise ValidationError(f"Invalid category '{cleaned}'. Choose one of: {allowed}")
    return cleaned


def find_duplicate_physical_path(
    resolved: Path, others: list[tuple[int, str]]
) -> int | None:
    """
    M11: catch the same physical folder registered under a different path
    string — a mapped network drive letter vs its UNC form, or an NTFS
    junction/symlink whose target is already registered directly. Exact
    string comparison (get_by_path) misses these since the path text
    differs even though the folder is identical on disk.

    Best-effort and fail-open by design: a path that can't be stat'd, or
    where the OS reports an unreliable identity (st_dev/st_ino both 0 —
    seen on some virtual/removable filesystems), is silently skipped rather
    than treated as a match. Missing a rare duplicate here is far safer
    than a false positive blocking a legitimate, genuinely distinct project.
    """
    try:
        target = resolved.stat()
    except OSError:
        return None
    target_key = (target.st_dev, target.st_ino)
    if target_key == (0, 0):
        return None
    for project_id, stored_path in others:
        try:
            other = Path(stored_path).stat()
        except OSError:
            continue
        if (other.st_dev, other.st_ino) == target_key:
            return project_id
    return None


def normalize_notes(notes: str | None) -> str | None:
    """
    Validate and normalize free-text project notes.

    L1: rejects input over MAX_FREE_TEXT_FIELD_CHARS with a deterministic
    ValidationError instead of silently truncating it. Only applies at this
    write boundary — reading back a project whose notes predate this limit
    (stored before it existed) is unaffected.
    """
    if notes is None:
        return None
    cleaned = notes.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_FREE_TEXT_FIELD_CHARS:
        raise ValidationError(
            f"Notes are too long ({len(cleaned)} characters; "
            f"limit is {MAX_FREE_TEXT_FIELD_CHARS})"
        )
    return cleaned


def normalize_status(status: str | None) -> str:
    """Validate project lifecycle status."""
    if status is None or not status.strip():
        return DEFAULT_PROJECT_STATUS
    cleaned = status.strip().lower()
    if cleaned not in PROJECT_STATUSES:
        allowed = ", ".join(PROJECT_STATUSES)
        raise ValidationError(f"Invalid status '{status}'. Choose one of: {allowed}")
    return cleaned
