"""Resolve session fields for resume summary (Exit Note is highest-trust)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from grafid.db.repositories.session_repository import SessionRepository
from grafid.resume.quality import normalize_note


@dataclass(frozen=True)
class SummarySessionSignals:
    """Session-derived inputs for SummaryEngine / resume panel."""

    exit_note: str | None
    blocker: str | None
    next_step: str | None
    has_active_session: bool
    session_started_at: str | None
    last_session_ended_at: str | None
    last_exit_session_id: int | None


def resolve_summary_session_fields(
    conn: sqlite3.Connection,
    project_id: int,
) -> SummarySessionSignals:
    """
    Pick session notes for the resume summary.

    The latest *completed* session's Exit Note (and related fields) wins over
    scanner/README context. An active session without notes does not erase a
    recent Exit Note.
    """
    repo = SessionRepository(conn)
    active = repo.get_active_for_project(project_id)
    last_ended = repo.get_last_ended_for_project(project_id)

    exit_note: str | None = None
    blocker: str | None = None
    next_step: str | None = None
    last_ended_at: str | None = None
    last_exit_session_id: int | None = None

    if last_ended is not None:
        exit_note = normalize_note(last_ended.exit_note)
        blocker = normalize_note(last_ended.blocker)
        next_step = normalize_note(last_ended.next_step)
        last_ended_at = last_ended.ended_at
        last_exit_session_id = last_ended.id

    return SummarySessionSignals(
        exit_note=exit_note,
        blocker=blocker,
        next_step=next_step,
        has_active_session=active is not None,
        session_started_at=active.started_at if active is not None else None,
        last_session_ended_at=last_ended_at,
        last_exit_session_id=last_exit_session_id,
    )
