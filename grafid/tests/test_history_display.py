"""Tests for history display enrichment."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from grafid.git.models import GitState
from grafid.models.snapshot import SnapshotHistoryEntry
from grafid.resume.quality import normalize_note
from grafid.services.history_display import (
    build_history_display_rows,
    correlate_session_for_scan,
)
from grafid.services.snapshot_persistence import SnapshotPersistenceService
from grafid.scanner.models import ScanResult


def _insert_session(
    db_path: Path,
    *,
    project_id: int,
    started_at: str,
    ended_at: str,
    exit_note: str | None = None,
    summary: str | None = None,
) -> int:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO work_sessions (
                project_id, started_at, ended_at,
                exit_note, blocker, next_step,
                snapshot_id_at_start, snapshot_id_at_end,
                created_at, updated_at, status, summary
            )
            VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?, 'completed', ?)
            """,
            (
                project_id,
                started_at,
                ended_at,
                exit_note,
                started_at,
                ended_at,
                summary,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _sample_scan_result() -> ScanResult:
    return ScanResult(
        project_name="demo",
        project_path="/demo",
        scanned_files=[],
        findings=[],
        skipped_count=0,
        duration_seconds=0.4,
        warnings=[],
    )


def test_correlate_session_picks_latest_before_scan(db_path: Path, project_id: int) -> None:
    from grafid.db.repositories.session_repository import SessionRepository
    from grafid.db.connection import DatabaseConnection

    _insert_session(
        db_path,
        project_id=project_id,
        started_at="2026-06-07T10:00:00+00:00",
        ended_at="2026-06-07T11:00:00+00:00",
        exit_note="Older session note",
    )
    _insert_session(
        db_path,
        project_id=project_id,
        started_at="2026-06-07T18:00:00+00:00",
        ended_at="2026-06-07T20:30:00+00:00",
        exit_note="Updated deployment configuration and payment flow notes.",
    )
    with DatabaseConnection(db_path) as conn:
        sessions = SessionRepository(conn).list_for_project(project_id, limit=10)

    matched = correlate_session_for_scan(sessions, "2026-06-07T21:14:00+00:00")
    assert matched is not None
    assert normalize_note(matched.exit_note) == (
        "Updated deployment configuration and payment flow notes."
    )


def test_correlate_session_ignores_future_sessions(db_path: Path, project_id: int) -> None:
    from grafid.db.repositories.session_repository import SessionRepository
    from grafid.db.connection import DatabaseConnection

    _insert_session(
        db_path,
        project_id=project_id,
        started_at="2026-06-07T22:00:00+00:00",
        ended_at="2026-06-07T23:00:00+00:00",
        exit_note="Future session",
    )
    with DatabaseConnection(db_path) as conn:
        sessions = SessionRepository(conn).list_for_project(project_id, limit=10)

    assert correlate_session_for_scan(sessions, "2026-06-07T21:14:00+00:00") is None


def test_build_history_display_rows_session_preview(
    db_path: Path,
    project_id: int,
) -> None:
    persistence = SnapshotPersistenceService(db_path)
    snapshot = persistence.save_snapshot(project_id, _sample_scan_result())
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE scan_snapshots SET scanned_at = ? WHERE id = ?",
            ("2026-06-07T21:14:00+00:00", snapshot.id),
        )
        conn.commit()

    _insert_session(
        db_path,
        project_id=project_id,
        started_at="2026-06-07T18:31:00+00:00",
        ended_at="2026-06-07T21:14:00+00:00",
        exit_note="Updated deployment configuration and payment flow notes.",
    )

    rows = build_history_display_rows(
        project_id=project_id,
        project_name="Mesencsi",
        db_path=db_path,
        limit=5,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["project_name"] == "Mesencsi"
    assert row["scanned_at_label"] == "2026-06-07 21:14:00"
    assert "Updated deployment configuration" in row["summary_preview"]
    assert row["summary_source"] == "session_best_effort"
    assert row["session_duration_label"] == "2h 43m"


def test_build_history_display_rows_scan_fallback(
    db_path: Path,
    project_id: int,
) -> None:
    persistence = SnapshotPersistenceService(db_path)
    git_state = GitState(
        is_git_repo=True,
        current_branch="main",
        is_dirty=True,
        modified_files=("src/a.ts", "src/b.ts"),
    )
    persistence.save_snapshot(project_id, _sample_scan_result(), git_state=git_state)

    rows = build_history_display_rows(
        project_id=project_id,
        project_name="Mesencsi",
        db_path=db_path,
        limit=5,
    )
    row = rows[0]
    assert row["summary_source"] == "scan"
    assert "Scanned" in row["summary_preview"]
    assert row["changed_files_count"] == 2
    assert row["session_duration_label"] is None


def test_build_history_display_rows_from_entries_without_db_scan(
    db_path: Path,
    project_id: int,
) -> None:
    entries = [
        SnapshotHistoryEntry(
            snapshot_id=99,
            scanned_at="2026-06-07T21:14:00+00:00",
            findings_count=3,
            scanned_files_count=8,
            duration_seconds=1.2,
            is_git_repo=True,
            git_branch="main",
            git_dirty=False,
        )
    ]
    rows = build_history_display_rows(
        project_id=project_id,
        project_name="Mesencsi",
        db_path=db_path,
        entries=entries,
        limit=5,
    )
    assert rows[0]["summary_preview"] == "Scanned 8 files, 3 findings, main (clean)"
    assert rows[0]["changed_files_count"] is None
