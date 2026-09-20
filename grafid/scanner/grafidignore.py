"""Load project-local .grafidignore patterns (gitignore-style, directory names only)."""

from __future__ import annotations

import sys
from pathlib import Path

GRAFIDIGNORE_FILENAME = ".grafidignore"


def load_grafidignore(project_root: Path) -> frozenset[str]:
    """
    Read .grafidignore from project root.

    Each non-empty, non-comment line is a directory name to skip anywhere in the tree.
    """
    path = project_root / GRAFIDIGNORE_FILENAME
    if not path.is_file():
        return frozenset()
    names: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return frozenset()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("/"):
            line = line.lstrip("/")
        token = line.split("/", 1)[0].strip()
        if token:
            names.add(token.lower() if sys.platform == "win32" else token)
    return frozenset(names)


def merge_ignore_names(
    defaults: frozenset[str],
    extra: frozenset[str],
) -> frozenset[str]:
    if not extra:
        return defaults
    return frozenset(set(defaults) | set(extra))
