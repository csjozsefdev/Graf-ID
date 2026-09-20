"""The one place that maps exceptions to IPC error codes.

Handlers turn a caught exception into a wire response with ``failure_from(exc)``;
the code string is what the desktop shell and the CLI see in ``error.code``.
Order matters: the first matching entry wins, so subclasses come before their
parents (``ValidationError`` is a ``ProjectError``).
"""

from __future__ import annotations

from grafid.core.exceptions import (
    ConfigError,
    DatabaseError,
    GrafPermissionError,
    ProjectError,
    StartupError,
    ValidationError,
)
from grafid.ipc.envelope import IpcResponse, failure
from grafid.services.build_cache import BuildCacheError

_ERROR_CODES: tuple[tuple[type[Exception], str], ...] = (
    (BuildCacheError, "build_cache_error"),
    (ValidationError, "validation_error"),
    (ProjectError, "project_error"),
    (StartupError, "startup_error"),
    (ConfigError, "config_error"),
    (DatabaseError, "database_error"),
    (GrafPermissionError, "permission_error"),
)

DEFAULT_ERROR_CODE = "runtime_error"


def error_code(exc: Exception) -> str:
    """Machine-readable code for ``exc`` (``runtime_error`` when nothing more specific fits)."""
    for exc_type, code in _ERROR_CODES:
        if isinstance(exc, exc_type):
            return code
    return DEFAULT_ERROR_CODE


def failure_from(exc: Exception) -> IpcResponse:
    """Failure envelope with the mapped code and the exception's message."""
    return failure(error_code(exc), str(exc))
