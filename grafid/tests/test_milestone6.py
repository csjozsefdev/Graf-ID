"""Tests for Milestone 6: resume quality, startup flow, session close."""

from __future__ import annotations

import sqlite3

import pytest

from grafid.core.constants import SCHEMA_VERSION
from grafid.core.exceptions import SessionError
from grafid.db.schema import get_schema_version
from grafid.models.session import ExitNoteInput
from grafid.resume.generator import ResumeSummaryGenerator
from grafid.resume.models import ResumeBundle
from grafid.resume.quality import (
    is_meaningful_text,
    normalize_note,
    truncate_scroll_content,
)
from grafid.services.exit_note_service import ExitNoteService
from grafid.services.session_service import SessionService


def test_schema_milestone6_tables(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        version = get_schema_version(conn)
    assert "startup_summaries" in tables
    assert "exit_note_history" in tables
    assert version == SCHEMA_VERSION


def test_low_value_notes_filtered() -> None:
    assert normalize_note("none") is None
    assert normalize_note("N/A") is None
    assert normalize_note("no blocker") is None
    assert normalize_note("no next step") is None
    assert normalize_note("  Fix auth  ") == "Fix auth"
    assert is_meaningful_text("real blocker") is True


def test_priority_ordering_ignores_low_value_blocker() -> None:
    from grafid.models.session import WorkSessionRecord

    session = WorkSessionRecord(
        id=1,
        project_id=1,
        started_at="2026-01-01T10:00:00+00:00",
        ended_at="2026-01-01T12:00:00+00:00",
        exit_note="Shipped feature",
        blocker="none",
        next_step="Write tests",
        snapshot_id_at_start=None,
        snapshot_id_at_end=1,
        created_at="2026-01-01T10:00:00+00:00",
        updated_at="2026-01-01T12:00:00+00:00",
        status="completed",
        summary=None,
    )
    bundle = ResumeBundle(
        project_id=1,
        project_name="demo",
        project_path="/demo",
        session=session,
        snapshot=None,
        findings=(),
        git=None,
        using_active_session=False,
    )
    summary = ResumeSummaryGenerator().generate(bundle, mode="short")
    titles = [s.title for s in summary.sections]
    assert "Current blocker" not in titles
    assert titles.index("Last session note (done)") < titles.index("Next step")


def test_skipped_exit_notes_on_close(db_path, project_id: int) -> None:
    sessions = SessionService(db_path)
    started = sessions.start_session(project_id)
    closed = sessions.close_active_session_for_project(
        project_id, skip_notes=True
    )
    assert closed.ended_at is not None

    history = ExitNoteService(db_path).list_history(project_id, limit=5)
    assert len(history) == 1
    assert history[0].session_id == started.id
    assert history[0].skipped is True


def test_close_with_exit_notes_recorded(db_path, project_id: int) -> None:
    sessions = SessionService(db_path)
    sessions.start_session(project_id)
    closed = sessions.close_active_session_for_project(
        project_id,
        notes=ExitNoteInput(
            exit_note="Finished milestone 6",
            blocker="",
            next_step="Tauri MVP",
        ),
    )
    assert closed.exit_note == "Finished milestone 6"
    assert closed.next_step == "Tauri MVP"
    assert closed.blocker is None

    history = ExitNoteService(db_path).list_history(project_id, limit=1)
    assert history[0].skipped is False
    assert history[0].exit_note == "Finished milestone 6"


def test_long_summary_truncation() -> None:
    body = "x" * 20_000
    truncated = truncate_scroll_content(body, purpose="startup")
    assert "truncated for display" in truncated
    assert len(truncated) < len(body)


def test_close_without_active_session_raises(db_path, project_id: int) -> None:
    with pytest.raises(SessionError, match="No active session"):
        SessionService(db_path).close_active_session_for_project(project_id)


def test_resume_latest_stored(db_path, project_id: int) -> None:
    from grafid.services.resume_service import ResumeService

    service = ResumeService(db_path)
    generated = service.generate_resume(project_id, mode="short", persist=True)
    latest = service.get_latest_stored_summary(project_id, mode="short")
    assert latest is not None
    assert latest.summary_body == generated.body
