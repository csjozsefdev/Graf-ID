"""IPC handlers for project summary export."""

from __future__ import annotations

import json
from pathlib import Path

from grafid.config.manager import ConfigManager
from grafid.core.exceptions import GrafIdError, ProjectError, ValidationError
from grafid.services.project_overview import resolve_project
from grafid.ipc.envelope import IpcResponse, failure, success
from grafid.ipc.errors import failure_from
from grafid.services.grafitalk_export import export_grafitalk_inbox
from grafid.services.project_export import export_to_path, suggested_filename


def handle_export_project_summary(
    project_id: int,
    *,
    export_format: str,
    output_path: str | None = None,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """
    Export one project summary.

    When ``output_path`` is omitted, returns a suggested filename for the save dialog.
    """
    try:
        from grafid.services.runtime import prepare_runtime

        runtime = prepare_runtime(config_manager)
        project = resolve_project(runtime.registry, project_id)
        if not output_path:
            return success(
                {
                    "project_id": project_id,
                    "format": export_format,
                    "suggested_filename": suggested_filename(
                        str(project.name),
                        export_format,
                    ),
                }
            )

        result = export_to_path(
            runtime.database_path,
            project_id,
            Path(output_path),
            export_format,
        )
        return success(
            {
                "project_id": project_id,
                **result.to_dict(),
            }
        )
    except ValidationError as exc:
        return failure("validation_error", str(exc))
    except ProjectError as exc:
        return failure("project_error", str(exc))
    except GrafIdError as exc:
        return failure_from(exc)


def handle_export_grafitalk_inbox(
    output_dir: str,
    *,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Export every project's GrafiTalk handoff into a user-chosen folder."""
    try:
        from grafid.services.runtime import prepare_runtime

        if not output_dir or not output_dir.strip():
            raise ValidationError("Choose a folder to export to.")
        runtime = prepare_runtime(config_manager)
        inbox = export_grafitalk_inbox(
            db_path=runtime.database_path,
            output_dir=Path(output_dir),
            config_dir=runtime.database_path.parent,
        )
        manifest = json.loads((inbox / "manifest.json").read_text(encoding="utf-8"))
        project_count = int(manifest["project_count"])
        return success(
            {
                "folder": str(inbox),
                "project_count": project_count,
                "message": f"Exported {project_count} project handoff file(s).",
            }
        )
    except ValidationError as exc:
        return failure("validation_error", str(exc))
    except OSError as exc:
        return failure("validation_error", f"Could not write to the export folder: {exc}")
    except GrafIdError as exc:
        return failure_from(exc)
