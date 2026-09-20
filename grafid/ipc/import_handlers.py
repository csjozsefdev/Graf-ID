"""IPC handlers for project context import (preview, then confirmed apply)."""

from __future__ import annotations

from grafid.config.manager import ConfigManager
from grafid.core.exceptions import GrafIdError, ProjectError, ValidationError
from grafid.handoff.importer import apply_context_import, preview_context_import
from grafid.ipc.envelope import IpcResponse, failure, success
from grafid.ipc.errors import failure_from


def handle_preview_context_import(
    project_id: int,
    file_path: str,
    *,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Validate a handoff file and show what importing it would store. Writes nothing."""
    try:
        from grafid.services.runtime import prepare_runtime

        runtime = prepare_runtime(config_manager)
        preview = preview_context_import(runtime.database_path, project_id, file_path)
        return success(preview.to_dict())
    except ValidationError as exc:
        return failure("validation_error", str(exc))
    except ProjectError as exc:
        return failure("project_error", str(exc))
    except GrafIdError as exc:
        return failure_from(exc)


def handle_apply_context_import(
    project_id: int,
    file_path: str,
    *,
    mode: str,
    fingerprint: str,
    confirmed: bool,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Apply a previewed import into the project's notes. Requires explicit confirmation."""
    try:
        from grafid.services.runtime import prepare_runtime

        runtime = prepare_runtime(config_manager)
        notes = apply_context_import(
            runtime.database_path,
            project_id,
            file_path,
            mode=mode,
            expected_fingerprint=fingerprint,
            confirmed=confirmed,
        )
        return success(
            {
                "project_id": project_id,
                "notes": notes,
                "message": "Imported into the project notes.",
            }
        )
    except ValidationError as exc:
        return failure("validation_error", str(exc))
    except ProjectError as exc:
        return failure("project_error", str(exc))
    except GrafIdError as exc:
        return failure_from(exc)
