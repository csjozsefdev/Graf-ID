"""Exit note history persistence on session close."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from grafid.core.exceptions import SessionError
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.exit_note_repository import ExitNoteRepository
from grafid.models.exit_note import ExitNoteHistoryRecord
from grafid.models.session import ExitNoteInput
from grafid.resume.quality import normalize_note


class ExitNoteService:
    """Record and list exit-note history (deterministic audit trail)."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def record_for_session_in_transaction(
        self,
        conn: sqlite3.Connection,
        project_id: int,
        session_id: int,
        notes: ExitNoteInput | None,
        *,
        skipped: bool,
    ) -> ExitNoteHistoryRecord:
        """
        Insert on an already-open transaction; the caller owns commit/rollback.

        Used by SessionService.end_session (M1) so the session-end update and its
        exit-note audit-trail row commit or roll back together — previously these
        were two separate transactions, so a crash between them could leave the
        session correctly closed but silently missing its own audit-trail entry.
        """
        return self._insert_in_transaction(conn, project_id, session_id, notes, skipped=skipped)

    def _insert_in_transaction(
        self,
        conn: sqlite3.Connection,
        project_id: int,
        session_id: int,
        notes: ExitNoteInput | None,
        *,
        skipped: bool,
    ) -> ExitNoteHistoryRecord:
        note_input = notes or ExitNoteInput()
        exit_note = normalize_note(note_input.exit_note)
        blocker = normalize_note(note_input.blocker)
        next_step = normalize_note(note_input.next_step)
        all_empty = exit_note is None and blocker is None and next_step is None
        effective_skipped = skipped or all_empty

        return ExitNoteRepository(conn).insert(
            project_id,
            session_id,
            exit_note=exit_note,
            blocker=blocker,
            next_step=next_step,
            skipped=effective_skipped,
        )

    def list_history(
        self, project_id: int, *, limit: int = 20
    ) -> list[ExitNoteHistoryRecord]:
        try:
            with DatabaseConnection(self._db_path) as conn:
                return ExitNoteRepository(conn).list_for_project(
                    project_id, limit=limit
                )
        except sqlite3.Error as exc:
            raise SessionError(f"Failed to load exit note history: {exc}") from exc
