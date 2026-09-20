"""Hardening tests after Milestone 6 (normalization, commits, git skips)."""

from __future__ import annotations

import sqlite3

import pytest

from grafid.db.transactions import commit_write
from grafid.models.session import ExitNoteInput
from grafid.resume.quality import PLACEHOLDER_PHRASES, normalize_note
from grafid.services.exit_note_service import ExitNoteService
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.session_service import SessionService
from grafid.tests.test_git import GIT_SKIP_REASON


@pytest.mark.parametrize(
    "raw",
    [
        "none",
        "N/A",
        "-",
        "nothing",
        "no blocker",
        "no next step",
        "no note",
        "No Blocker.",
    ],
)
def test_placeholder_phrases_normalize_to_empty(raw: str) -> None:
    assert normalize_note(raw) is None


@pytest.mark.parametrize(
    "raw",
    [
        "Waiting on API review",
        "Shipped resume engine",
        "Fix auth middleware",
    ],
)
def test_meaningful_notes_are_kept(raw: str) -> None:
    assert normalize_note(raw) == raw


def test_placeholder_set_includes_required_phrases() -> None:
    required = {
        "no blocker",
        "no next step",
        "no note",
        "nothing",
        "none",
        "n/a",
        "-",
    }
    assert required.issubset(PLACEHOLDER_PHRASES)


def test_exit_note_history_visible_after_connection_closed(
    db_path, project_id: int
) -> None:
    """Regression: writes must commit so a new connection sees persisted rows."""
    sessions = SessionService(db_path)
    started = sessions.start_session(project_id)
    sessions.end_session(started.id, notes=ExitNoteInput(exit_note="Saved note"))

    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM exit_note_history WHERE session_id = ?",
            (started.id,),
        ).fetchone()[0]
    assert count == 1

    history = ExitNoteService(db_path).list_history(project_id)
    assert history[0].exit_note == "Saved note"


def test_project_add_visible_after_connection_closed(db_path, tmp_path) -> None:
    """Regression: registry add must commit through the service layer."""
    project_dir = tmp_path / "commit-check"
    project_dir.mkdir()
    registry = ProjectRegistryService(db_path)
    record = registry.add("commit-check", str(project_dir))

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM projects WHERE id = ?", (record.id,)
        ).fetchone()
    assert row is not None
    assert row[0] == "commit-check"


def test_commit_write_helper_persists(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO settings (key, value, created_at, updated_at) "
            "VALUES ('hardening-test', '1', 't', 't')"
        )
        commit_write(conn)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'hardening-test'"
        ).fetchone()
    assert row is not None
    assert row[0] == "1"


def test_session_close_filters_placeholder_blocker(db_path, project_id: int) -> None:
    sessions = SessionService(db_path)
    sessions.start_session(project_id)
    closed = sessions.close_active_session_for_project(
        project_id,
        notes=ExitNoteInput(
            exit_note="Finished task",
            blocker="no blocker",
            next_step="no next step",
        ),
    )
    assert closed.exit_note == "Finished task"
    assert closed.blocker is None
    assert closed.next_step is None


def test_git_skip_reason_documents_environment_only() -> None:
    assert "environment" in GIT_SKIP_REASON.lower()
    assert "not an app failure" in GIT_SKIP_REASON
