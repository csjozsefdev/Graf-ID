"""Safe read-only Git subprocess runner."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from grafid.utils.logging_setup import get_logger

logger = get_logger("git.runner")

GIT_TIMEOUT_SECONDS = 30
ALLOWED_GIT_COMMANDS = frozenset(
    {
        "rev-parse",
        "status",
        "log",
    }
)


def git_available() -> bool:
    """Return True when the git executable is on PATH."""
    return shutil.which("git") is not None


def run_git_readonly(repo_root: Path, *args: str) -> tuple[int, str, str]:
    """
    Run a whitelisted read-only git command.

    Returns (exit_code, stdout, stderr).
    """
    if not args or args[0] not in ALLOWED_GIT_COMMANDS:
        raise ValueError(f"Git command not allowed: {args[:1]}")

    command = ["git", "-C", str(repo_root), *args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Git command timed out: %s", " ".join(command))
        raise
    except OSError as exc:
        logger.warning("Git command failed to start: %s", exc)
        raise

    # Preserve leading whitespace on stdout — porcelain XY status uses column 0/1.
    stdout = completed.stdout.rstrip("\r\n")
    return completed.returncode, stdout, completed.stderr.strip()
