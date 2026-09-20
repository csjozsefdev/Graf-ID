"""Symlink-safe path containment helpers shared by the scanner and resume pipelines.

Registered projects are not fully trusted content (a cloned third-party repo can
contain crafted symlinks or NTFS reparse points). These helpers make sure the
scanner and workflow-artifact readers never follow a link — whether it stays
inside the project root or escapes it — and never read a file whose final,
fully-resolved location falls outside the intended root.
"""

from __future__ import annotations

import os
import stat as stat_module
import sys
from pathlib import Path

_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def is_unsafe_symlink(path: Path) -> bool:
    """
    True when ``path`` itself is a symlink, Windows junction, or other
    reparse point. Uses ``lstat`` so the link is never followed to answer this.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat_module.S_ISLNK(st.st_mode):
        return True
    if sys.platform == "win32":
        attrs = getattr(st, "st_file_attributes", None)
        if attrs is not None:
            return bool(attrs & _FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def is_within_root(path: Path, root: Path) -> bool:
    """True when ``path`` fully resolves to a location inside (or equal to) ``root``."""
    try:
        resolved = path.resolve()
        resolved_root = root.resolve()
    except OSError:
        return False
    return resolved == resolved_root or resolved.is_relative_to(resolved_root)


def is_safe_project_path(path: Path, root: Path) -> bool:
    """
    True when ``path`` is safe to read/enter as part of a project rooted at ``root``:

    - ``path`` itself is not a symlink or reparse point (never followed by default)
    - its fully resolved location stays inside ``root``
    """
    if is_unsafe_symlink(path):
        return False
    return is_within_root(path, root)
