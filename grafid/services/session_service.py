"""Work session lifecycle (isolated from scanner and git collection)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from grafid.utils.datetime_utils import parse_iso
from grafid.core.constants import MAX_FREE_TEXT_FIELD_CHARS
from grafid.core.exceptions import SessionError
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.project_repository import ProjectRepository
from grafid.db.repositories.session_repository import SessionRepository
from grafid.models.session import (
    ExitNoteInput,
    SessionResumeContext,
    SessionStatusView,
    WorkSessionRecord,
)
from grafid.resume.quality import normalize_note
from grafid.services.exit_note_service import ExitNoteService
from grafid.services.session_resume import SessionResumeService
from grafid.utils.datetime_utils import utc_now_iso
from grafid.utils.logging_setup import get_logger

logger = get_logger("session")


class SessionService:
    """Start, end, and inspect local workflow sessions."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def start_session(self, project_id: int) -> WorkSessionRecord:
        """
        Start a new active session for one project.

        Fails when an unfinished session already exists (recovery safety).
        """
        logger.info("Starting session for project_id=%s", project_id)

        try:
            with DatabaseConnection(self._db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    if ProjectRepository(conn).get_by_id(project_id) is None:
                        raise SessionError(f"Project not found: {project_id}")

                    active = SessionRepository(conn).get_active_for_project(project_id)
                    if active is not None:
                        raise SessionError(
                            "Unfinished session exists "
                            f"(id={active.id}). End it with 'graf-id session end' before starting a new one."
                        )

                    snapshot_id = _latest_snapshot_id(conn, project_id)
                    session = SessionRepository(conn).insert_start(
                        project_id, snapshot_id_at_start=snapshot_id
                    )
                    _set_project_active(conn, project_id, active=True)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        except SessionError:
            raise
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to start session: {exc}") from exc

        logger.info("Session started id=%s project_id=%s", session.id, project_id)
        return session

    def end_session(
        self,
        session_id: int,
        *,
        notes: ExitNoteInput | None = None,
        record_history: bool = True,
        notes_skipped: bool = False,
    ) -> WorkSessionRecord:
        """End an active session and persist optional exit notes."""
        note_input = _normalize_exit_input(notes)
        ended_at = utc_now_iso()
        logger.info("Ending session id=%s", session_id)

        # M1: the session-end update and its exit-note audit-trail row are one
        # business operation — both happen inside this single transaction, so a
        # crash between them can no longer leave the session correctly closed
        # with a silently missing exit_note_history entry.
        try:
            with DatabaseConnection(self._db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    existing = SessionRepository(conn).get_by_id(session_id)
                    if existing is None:
                        raise SessionError(f"Session not found: {session_id}")
                    if not existing.is_active:
                        raise SessionError(f"Session already ended: {session_id}")

                    snapshot_id = _latest_snapshot_id(conn, existing.project_id)
                    updated = SessionRepository(conn).end_session(
                        session_id,
                        ended_at=ended_at,
                        notes=note_input,
                        snapshot_id_at_end=snapshot_id,
                    )
                    if updated is None or updated.ended_at is None:
                        raise SessionError(
                            f"Session end failed or was interrupted: {session_id}"
                        )

                    _set_project_active(conn, existing.project_id, active=False)

                    if record_history:
                        skipped = notes_skipped or _notes_are_empty(note_input)
                        ExitNoteService(self._db_path).record_for_session_in_transaction(
                            conn,
                            existing.project_id,
                            session_id,
                            note_input,
                            skipped=skipped,
                        )

                    conn.commit()
                    session = updated
                except Exception:
                    conn.rollback()
                    raise
        except SessionError:
            raise
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to end session: {exc}") from exc

        logger.info("Session ended id=%s", session_id)
        return session

    def end_active_session_for_project(
        self,
        project_id: int,
        *,
        notes: ExitNoteInput | None = None,
        record_history: bool = True,
        notes_skipped: bool = False,
    ) -> WorkSessionRecord:
        """End the current active session for a project by project id."""
        active = self.get_active_session(project_id)
        if active is None:
            raise SessionError(f"No active session for project_id={project_id}")
        return self.end_session(
            active.id,
            notes=notes,
            record_history=record_history,
            notes_skipped=notes_skipped,
        )

    def close_active_session_for_project(
        self,
        project_id: int,
        *,
        notes: ExitNoteInput | None = None,
        skip_notes: bool = False,
    ) -> WorkSessionRecord:
        """
        End the active session via the close flow (optional notes, safe skip).

        Same as end_session but intended for interactive close; always records
        exit note history when the session ends successfully.
        """
        if skip_notes:
            closed = self.end_active_session_for_project(
                project_id,
                notes=ExitNoteInput(),
                record_history=True,
                notes_skipped=True,
            )
            _observe_session_close(
                self._db_path,
                project_id=project_id,
                session=closed,
                skip_notes=True,
            )
            return closed
        closed = self.end_active_session_for_project(
            project_id,
            notes=notes,
            record_history=True,
            notes_skipped=_notes_are_empty(_normalize_exit_input(notes)),
        )
        _observe_session_close(
            self._db_path,
            project_id=project_id,
            session=closed,
            skip_notes=False,
        )
        return closed

    def get_active_session(self, project_id: int) -> WorkSessionRecord | None:
        try:
            with DatabaseConnection(self._db_path) as conn:
                return SessionRepository(conn).get_active_for_project(project_id)
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to load active session: {exc}") from exc

    def get_status(self, project_id: int, *, project_name: str) -> SessionStatusView:
        """Return active/unfinished session information for one project."""
        active = self.get_active_session(project_id)
        last_ended: WorkSessionRecord | None
        try:
            with DatabaseConnection(self._db_path) as conn:
                last_ended = SessionRepository(conn).get_last_ended_for_project(project_id)
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to load session status: {exc}") from exc

        return SessionStatusView(
            project_name=project_name,
            has_active_session=active is not None,
            active_session=active,
            has_unfinished_session=active is not None,
            last_ended_session=last_ended,
        )

    def session_duration_seconds(self, session: WorkSessionRecord) -> float:
        """Compute elapsed seconds for active or ended sessions."""
        start = parse_iso(session.started_at)
        if start is None:
            return 0.0
        end = parse_iso(session.ended_at) if session.ended_at else datetime.now(UTC)
        if end is None:
            end = datetime.now(UTC)
        return max(0.0, (end - start).total_seconds())

    def build_resume_context(self, session_id: int) -> SessionResumeContext:
        """Load resume preparation context for a stored session."""
        try:
            with DatabaseConnection(self._db_path) as conn:
                session = SessionRepository(conn).get_by_id(session_id)
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to load session: {exc}") from exc

        if session is None:
            raise SessionError(f"Session not found: {session_id}")
        return SessionResumeService(self._db_path).build_context(session)


def _latest_snapshot_id(connection: sqlite3.Connection, project_id: int) -> int | None:
    row = connection.execute(
        """
        SELECT id FROM scan_snapshots
        WHERE project_id = ?
        ORDER BY scanned_at DESC, id DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    return int(row["id"]) if row else None


def _set_project_active(
    connection: sqlite3.Connection, project_id: int, *, active: bool
) -> None:
    now = utc_now_iso()
    if active:
        connection.execute("UPDATE projects SET is_active = 0")
    connection.execute(
        """
        UPDATE projects
        SET is_active = ?, updated_at = ?
        WHERE id = ?
        """,
        (int(active), now, project_id),
    )


def _normalize_exit_input(notes: ExitNoteInput | None) -> ExitNoteInput:
    raw = notes or ExitNoteInput()
    return ExitNoteInput(
        exit_note=_validated_note(raw.exit_note, field_name="exit_note"),
        blocker=_validated_note(raw.blocker, field_name="blocker"),
        next_step=_validated_note(raw.next_step, field_name="next_step"),
    )


def _validated_note(value: str | None, *, field_name: str) -> str | None:
    """
    L1: reject an over-limit exit note/blocker/next step with a deterministic
    error instead of silently truncating it or storing it unbounded.

    Only applies here, at the write boundary (CLI and IPC both funnel
    through SessionService.end_session -> here) — normalize_note() itself is
    also used to display already-stored sessions, and must keep working
    unchanged for old data recorded before this limit existed.
    """
    cleaned = normalize_note(value)
    if cleaned is not None and len(cleaned) > MAX_FREE_TEXT_FIELD_CHARS:
        raise SessionError(
            f"{field_name} is too long ({len(cleaned)} characters; "
            f"limit is {MAX_FREE_TEXT_FIELD_CHARS})"
        )
    return cleaned


def _notes_are_empty(notes: ExitNoteInput) -> bool:
    return (
        notes.exit_note is None
        and notes.blocker is None
        and notes.next_step is None
    )


def _observe_session_close(
    db_path: Path,
    *,
    project_id: int,
    session: WorkSessionRecord,
    skip_notes: bool,
) -> None:
    """Local usage journal hook (no-op when journal disabled)."""
    from grafid.config.manager import ConfigManager
    from grafid.observability.journal import record_event

    config_dir = db_path.parent
    mgr = ConfigManager(config_dir=config_dir)
    cfg = mgr.load()
    record_event(
        "session.close",
        config_dir=config_dir,
        config=cfg,
        project_id=project_id,
        session_id=session.id,
        skip_notes=skip_notes,
        has_notes=bool(session.exit_note or session.blocker or session.next_step),
    )
    if skip_notes:
        record_event(
            "session.close_skip_notes",
            config_dir=config_dir,
            config=cfg,
            project_id=project_id,
            session_id=session.id,
        )
