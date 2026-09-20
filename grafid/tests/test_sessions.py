"""Tests for work session system (Milestone 4)."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from grafid.core.constants import SCHEMA_VERSION
from grafid.core.exceptions import SessionError
from grafid.db.schema import get_schema_version
from grafid.models.session import ExitNoteInput
from grafid.services.session_service import SessionService
from grafid.services.snapshot_persistence import SnapshotPersistenceService
from grafid.scanner.models import ScanResult


@pytest.fixture
def session_service(db_path) -> SessionService:
    return SessionService(db_path)


def test_schema_includes_work_sessions(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        version = get_schema_version(conn)
    assert "work_sessions" in tables
    assert version == SCHEMA_VERSION


def test_session_start_and_end(session_service: SessionService, project_id: int) -> None:
    started = session_service.start_session(project_id)
    assert started.is_active is True
    assert started.ended_at is None

    ended = session_service.end_session(
        started.id,
        notes=ExitNoteInput(
            exit_note="Implemented sessions",
            blocker="None",
            next_step="Resume engine",
        ),
    )
    assert ended.ended_at is not None
    assert ended.exit_note == "Implemented sessions"
    assert ended.blocker is None
    assert ended.next_step == "Resume engine"
    assert session_service.session_duration_seconds(ended) >= 0


def test_unfinished_session_blocks_new_start(
    session_service: SessionService, project_id: int
) -> None:
    session_service.start_session(project_id)
    with pytest.raises(SessionError, match="Unfinished session"):
        session_service.start_session(project_id)


def test_unfinished_session_detected_in_status(
    session_service: SessionService, project_id: int
) -> None:
    session_service.start_session(project_id)
    status = session_service.get_status(project_id, project_name="test-project")
    assert status.has_unfinished_session is True
    assert status.active_session is not None


def test_exit_note_persistence(session_service: SessionService, project_id: int) -> None:
    started = session_service.start_session(project_id)
    session_service.end_session(
        started.id, notes=ExitNoteInput(exit_note="done", blocker="b", next_step="n")
    )
    status = session_service.get_status(project_id, project_name="test-project")
    assert status.last_ended_session is not None
    assert status.last_ended_session.exit_note == "done"
    assert status.last_ended_session.blocker == "b"
    assert status.last_ended_session.next_step == "n"


def test_interrupted_end_rolls_back(
    session_service: SessionService, project_id: int, db_path
) -> None:
    started = session_service.start_session(project_id)
    with patch(
        "grafid.db.repositories.session_repository.SessionRepository.end_session",
        return_value=None,
    ):
        with pytest.raises(SessionError, match="failed or was interrupted"):
            session_service.end_session(started.id)

    active = session_service.get_active_session(project_id)
    assert active is not None
    assert active.id == started.id


def test_resume_context_links_snapshot_findings(
    session_service: SessionService,
    project_id: int,
    db_path,
) -> None:
    persistence = SnapshotPersistenceService(db_path)
    snapshot = persistence.save_snapshot(
        project_id,
        ScanResult(project_name="test", project_path="/tmp", findings=[]),
    )

    started = session_service.start_session(project_id)
    assert started.snapshot_id_at_start == snapshot.id

    ended = session_service.end_session(started.id)
    context = session_service.build_resume_context(ended.id)
    assert context.project_name == "test-project"
    assert context.snapshot_at_start == snapshot.id
    assert context.findings_at_start == 0


def test_empty_scan_session_start_allowed(
    session_service: SessionService, project_id: int
) -> None:
    session = session_service.start_session(project_id)
    assert session.snapshot_id_at_start is None
