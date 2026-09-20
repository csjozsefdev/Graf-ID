"""IPC handlers for work session lifecycle."""



from __future__ import annotations



from typing import Any



from grafid.config.manager import ConfigManager

from grafid.core.exceptions import (

    ConfigError,

    DatabaseError,

    GrafIdError,

    GrafPermissionError,

    ProjectError,

    ResumeError,

    SessionError,

    StartupError,

    ValidationError,

)

from grafid.db.connection import DatabaseConnection

from grafid.db.repositories.session_repository import SessionRepository

from grafid.services.project_overview import item_and_resume_panel, session_to_dict

from grafid.ipc.envelope import IpcResponse, failure, success

from grafid.ipc.errors import failure_from

from grafid.models.session import ExitNoteInput

from grafid.services.resume_service import ResumeService

from grafid.services.session_service import SessionService





def handle_start_session(

    project_id: int,

    *,

    checkpoint: str | None = None,

    config_manager: ConfigManager | None = None,

) -> IpcResponse:

    """Start a new work session for one project."""

    try:

        from grafid.services.runtime import prepare_runtime



        runtime = prepare_runtime(config_manager)

        runtime.registry.get_info(str(project_id))

        service = SessionService(runtime.database_path)

        session = service.start_session(project_id)

        if checkpoint and checkpoint.strip():

            with DatabaseConnection(runtime.database_path) as conn:

                conn.execute(

                    "UPDATE work_sessions SET summary = ? WHERE id = ?",

                    (checkpoint.strip(), session.id),

                )

                conn.commit()

        with DatabaseConnection(runtime.database_path) as conn:

            record = runtime.registry.get_info(str(project_id))

            item, resume_panel = item_and_resume_panel(
                conn, runtime.database_path, record, project_id
            )

        return success(

            {

                "session": session_to_dict(session, is_active=True),

                "project": item,

                "resume_panel": resume_panel,

                "message": "Session started.",

            }

        )

    except SessionError as exc:

        return failure("session_error", str(exc))

    except ProjectError as exc:

        return failure("project_error", str(exc))

    except (StartupError, ConfigError, DatabaseError, GrafPermissionError) as exc:

        return failure_from(exc)

    except GrafIdError as exc:

        return failure_from(exc)





def handle_session_timeline(

    project_id: int,

    *,

    limit: int = 10,

    config_manager: ConfigManager | None = None,

) -> IpcResponse:

    """List recent sessions with exit note previews."""

    try:

        from grafid.services.runtime import prepare_runtime

        from grafid.resume.summary_engine import build_session_timeline



        runtime = prepare_runtime(config_manager)

        runtime.registry.get_info(str(project_id))

        with DatabaseConnection(runtime.database_path) as conn:

            sessions = SessionRepository(conn).list_for_project(project_id, limit=limit)

            rows = [session_to_dict(s, is_active=s.ended_at is None) for s in sessions]

        timeline = build_session_timeline(rows, limit=limit)

        return success(

            {

                "project_id": project_id,

                "sessions": rows,

                "timeline": [t.__dict__ for t in timeline],

            }

        )

    except ProjectError as exc:

        return failure("project_error", str(exc))

    except GrafIdError as exc:

        return failure_from(exc)





def handle_close_session(

    project_id: int,

    *,

    exit_note: str | None = None,

    blocker: str | None = None,

    next_step: str | None = None,

    skip_notes: bool = False,

    unfinished: str | None = None,

    config_manager: ConfigManager | None = None,

) -> IpcResponse:

    """End the active session and optionally save exit notes."""

    try:

        from grafid.services.runtime import prepare_runtime



        runtime = prepare_runtime(config_manager)

        runtime.registry.get_info(str(project_id))



        combined_exit = exit_note

        if exit_note and unfinished:

            combined_exit = f"{exit_note.strip()}\nStill unfinished: {unfinished.strip()}"

        elif unfinished:

            combined_exit = unfinished

        notes = ExitNoteInput(

            exit_note=combined_exit,

            blocker=blocker,

            next_step=next_step,

        )

        SessionService(runtime.database_path).close_active_session_for_project(

            project_id,

            notes=notes,

            skip_notes=skip_notes,

        )

        resume_warning: str | None = None
        try:
            ResumeService(runtime.database_path).generate_resume(
                project_id, mode="short", persist=True
            )
        except ResumeError as exc:
            resume_warning = str(exc)

        with DatabaseConnection(runtime.database_path) as conn:

            record = runtime.registry.get_info(str(project_id))

            item, resume_panel = item_and_resume_panel(
                conn, runtime.database_path, record, project_id
            )

        payload: dict[str, Any] = {

            "project": item,

            "resume_panel": resume_panel,

            "message": "Session ended.",

            "session_closed": True,

        }
        if resume_warning:
            payload["resume_warning"] = resume_warning
        return success(payload)

    except SessionError as exc:

        return failure("session_error", str(exc))

    except ProjectError as exc:

        return failure("project_error", str(exc))

    except ValidationError as exc:

        return failure("validation_error", str(exc))

    except (StartupError, ConfigError, DatabaseError, GrafPermissionError) as exc:

        return failure_from(exc)

    except GrafIdError as exc:

        return failure_from(exc)





def handle_end_session(

    project_id: int,

    **kwargs: Any,

) -> IpcResponse:

    """Alias for close-session (PRO explicit end IPC)."""

    return handle_close_session(project_id, **kwargs)


