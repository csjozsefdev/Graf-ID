"""The single exception -> IPC error-code mapping."""

from __future__ import annotations

import pytest

from grafid.core.exceptions import (
    ConfigError,
    DatabaseError,
    DuplicateProjectError,
    GrafIdError,
    GrafPermissionError,
    ProjectError,
    ScanError,
    StartupError,
    ValidationError,
)
from grafid.handoff.validate import HandoffValidationError
from grafid.ipc.errors import DEFAULT_ERROR_CODE, error_code, failure_from
from grafid.services.build_cache import BuildCacheError
from grafid.services.workflow_launch import WorkflowLaunchError


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (BuildCacheError("x"), "build_cache_error"),
        (ValidationError("x"), "validation_error"),
        (HandoffValidationError("x"), "validation_error"),
        (ProjectError("x"), "project_error"),
        (DuplicateProjectError("x"), "project_error"),
        (WorkflowLaunchError("x"), "project_error"),
        (StartupError("x"), "startup_error"),
        (ConfigError("x"), "config_error"),
        (DatabaseError("x"), "database_error"),
        (GrafPermissionError("x"), "permission_error"),
        (ScanError("x"), DEFAULT_ERROR_CODE),
        (GrafIdError("x"), DEFAULT_ERROR_CODE),
        (RuntimeError("x"), DEFAULT_ERROR_CODE),
    ],
)
def test_error_code_mapping(exc: Exception, code: str) -> None:
    assert error_code(exc) == code


def test_validation_error_wins_over_its_project_error_parent() -> None:
    assert isinstance(ValidationError("x"), ProjectError)
    assert error_code(ValidationError("x")) == "validation_error"


def test_failure_from_builds_the_envelope() -> None:
    response = failure_from(ConfigError("bad config"))
    assert response.ok is False
    assert response.error is not None
    assert (response.error.code, response.error.message) == ("config_error", "bad config")


def test_builtin_permission_error_is_not_the_domain_one() -> None:
    assert error_code(PermissionError("os says no")) == DEFAULT_ERROR_CODE
