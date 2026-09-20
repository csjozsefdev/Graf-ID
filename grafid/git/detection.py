"""Git repository detection."""

from __future__ import annotations

from pathlib import Path


def find_repo_root(project_path: Path) -> Path | None:
    """
    Locate the Git repository root for a project directory.

    Returns None when the path is not inside a Git work tree.
    """
    resolved = project_path.expanduser().resolve()
    if not resolved.exists():
        return None

    candidate = resolved if resolved.is_dir() else resolved.parent
    if (candidate / ".git").exists():
        return candidate

    for parent in candidate.parents:
        if (parent / ".git").exists():
            return parent
    return None
