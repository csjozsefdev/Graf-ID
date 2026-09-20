"""Ensure IPC stdout/stderr use UTF-8 (Windows usernames with non-ASCII characters)."""

from __future__ import annotations

import sys


def configure_ipc_stdio_utf8() -> None:
    """Force UTF-8 IPC JSON on stdout so Tauri receives valid Unicode paths."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
