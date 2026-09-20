"""Milestone 4 regression tests: database integrity & atomicity.

Covers audit findings H4 (refresh atomicity), H5 (DB-level session uniqueness),
H6 (duplicate project race), M1 (session-end + exit-note-history atomicity),
M2 (retention must not delete a snapshot an active session still references),
and L4 (resume trim-then-insert atomicity).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from grafid.core.exceptions import DuplicateProjectError
from grafid.db.connection import DatabaseConnection
from grafid.db.migrations import v012_one_active_session_per_project
from grafid.db.repositories.project_repository import ProjectRepository
from grafid.db.repositories.session_repository import SessionRepository
from grafid.models.session import ExitNoteInput
from grafid.scanner.models import ScanResult
from grafid.services.context_refresh import refresh_project_scan
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.resume_service import ResumeService
from grafid.services.retention_policy import RetentionPolicy
from grafid.services.session_service import SessionService
from grafid.services.snapshot_persistence import SnapshotPersistenceService
from grafid.services.snapshot_retention import SnapshotRetentionService


def _scan(name: str = "test") -> ScanResult:
    return ScanResult(project_name=name, project_path=".", duration_seconds=0.1)


# ---------------------------------------------------------------------------
# H4 — refresh_project_scan: snapshot + retention + last_refreshed_at atomic
# ---------------------------------------------------------------------------


def test_refresh_atomicity_rolls_back_snapshot_if_last_refreshed_write_fails(
    db_path: Path, project_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    with DatabaseConnection(db_path) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM scan_snapshots WHERE project_id = ?", (project_id,)
        ).fetchone()[0]

    def boom(self, project_id: int, refreshed_at: str):  # noqa: ANN001
        raise RuntimeError("simulated crash after snapshot insert")

    monkeypatch.setattr(ProjectRepository, "set_last_refreshed", boom)

    with pytest.raises(RuntimeError):
        refresh_project_scan(db_path, project_id)

    with DatabaseConnection(db_path) as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM scan_snapshots WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
        record = ProjectRepository(conn).get_by_id(project_id)

    assert after == before, "snapshot insert must roll back with the rest of the transaction"
    assert record is not None
    assert record.last_refreshed_at is None


def test_refresh_atomicity_rolls_back_retention_pruning_too(
    db_path: Path, project_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash after retention pruning ran must undo the pruning as well, not just the insert."""
    from grafid.services import snapshot_retention

    persistence = SnapshotPersistenceService(db_path)
    for _ in range(3):
        persistence.save_snapshot(project_id, _scan())
    with DatabaseConnection(db_path) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM scan_snapshots WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
    assert before == 3

    # Force retention to actually have something to prune during this refresh.
    monkeypatch.setattr(
        snapshot_retention,
        "DEFAULT_POLICY",
        RetentionPolicy(max_snapshots_per_project=1, max_age_days=None),
    )

    def boom(self, project_id: int, refreshed_at: str):  # noqa: ANN001
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(ProjectRepository, "set_last_refreshed", boom)

    with pytest.raises(RuntimeError):
        refresh_project_scan(db_path, project_id)

    with DatabaseConnection(db_path) as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM scan_snapshots WHERE project_id = ?", (project_id,)
        ).fetchone()[0]

    # This refresh call's own scan inserted a 4th snapshot and then pruned down
    # to 1 before the crash. If either step had committed independently of the
    # failed last_refreshed_at write, the count would differ from `before`; a
    # true rollback of the whole transaction restores exactly the pre-call state.
    assert after == before, "neither the insert nor the pruning from the aborted refresh may commit"


def test_refresh_success_commits_snapshot_retention_and_last_refreshed_together(
    db_path: Path, project_id: int
) -> None:
    persistence = SnapshotPersistenceService(db_path)
    for _ in range(3):
        persistence.save_snapshot(project_id, _scan())

    result = refresh_project_scan(db_path, project_id)

    assert result.scan_ok is True
    assert result.last_refreshed_at is not None
    with DatabaseConnection(db_path) as conn:
        record = ProjectRepository(conn).get_by_id(project_id)
    assert record is not None
    assert record.last_refreshed_at == result.last_refreshed_at


# ---------------------------------------------------------------------------
# H5 — DB-level uniqueness: at most one active session per project
# ---------------------------------------------------------------------------


def test_schema_rejects_a_second_active_session_for_the_same_project(
    db_path: Path, project_id: int
) -> None:
    now = "2026-01-01T00:00:00Z"
    with DatabaseConnection(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO work_sessions
                (project_id, started_at, created_at, updated_at, status)
            VALUES (?, ?, ?, ?, 'active')
            """,
            (project_id, now, now, now),
        )
        conn.commit()

    with DatabaseConnection(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO work_sessions
                    (project_id, started_at, created_at, updated_at, status)
                VALUES (?, ?, ?, ?, 'active')
                """,
                (project_id, "2026-01-02T00:00:00Z", now, now),
            )
        conn.rollback()


def test_a_second_ended_session_for_the_same_project_is_allowed(
    db_path: Path, project_id: int
) -> None:
    """The guard is a *partial* unique index (WHERE ended_at IS NULL) — history rows are unrestricted."""
    now = "2026-01-01T00:00:00Z"
    with DatabaseConnection(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO work_sessions
                (project_id, started_at, ended_at, created_at, updated_at, status)
            VALUES (?, ?, ?, ?, ?, 'completed')
            """,
            (project_id, now, now, now, now),
        )
        conn.execute(
            """
            INSERT INTO work_sessions
                (project_id, started_at, ended_at, created_at, updated_at, status)
            VALUES (?, ?, ?, ?, ?, 'completed')
            """,
            (project_id, now, now, now, now),
        )
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) FROM work_sessions WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
    assert count == 2


def test_v012_migration_heals_preexisting_duplicate_active_sessions(tmp_path: Path) -> None:
    """
    Defensive data repair: if a database somehow already violates "one active
    session per project" before this migration runs, it must heal the data
    instead of crashing the whole app on CREATE UNIQUE INDEX.
    """
    from grafid.db.schema import apply_schema

    db = tmp_path / "healing.db"
    with DatabaseConnection(db) as conn:
        apply_schema(conn)  # brings a fresh DB to the current schema, index included

        # Simulate a pre-existing violation by dropping the guard and inserting
        # duplicate active sessions directly, bypassing the application layer.
        conn.execute("DROP INDEX IF EXISTS idx_one_active_session_per_project")
        now = "2026-01-01T00:00:00Z"
        conn.execute(
            "INSERT INTO projects (name, path, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("demo-heal", str(tmp_path), now, now),
        )
        project_id = conn.execute(
            "SELECT id FROM projects WHERE name = 'demo-heal'"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO work_sessions
                (project_id, started_at, created_at, updated_at, status)
            VALUES (?, ?, ?, ?, 'active')
            """,
            (project_id, "2026-01-01T00:00:00Z", now, now),
        )
        conn.execute(
            """
            INSERT INTO work_sessions
                (project_id, started_at, created_at, updated_at, status)
            VALUES (?, ?, ?, ?, 'active')
            """,
            (project_id, "2026-01-02T00:00:00Z", now, now),
        )
        conn.commit()

        # Re-run the migration's own apply() — must heal the duplicates and not raise.
        v012_one_active_session_per_project.apply(conn)
        conn.commit()

        active_rows = conn.execute(
            "SELECT id FROM work_sessions WHERE project_id = ? AND ended_at IS NULL",
            (project_id,),
        ).fetchall()
        all_rows = conn.execute(
            "SELECT status, ended_at FROM work_sessions WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        index_names = {
            row[1] for row in conn.execute("PRAGMA index_list(work_sessions)").fetchall()
        }

    assert len(active_rows) == 1, "exactly one session must remain active after healing"
    assert len(all_rows) == 2, "no session row may be deleted, only force-ended"
    closed = [r for r in all_rows if r["ended_at"] is not None]
    assert len(closed) == 1
    assert closed[0]["status"] == "abandoned"
    assert "idx_one_active_session_per_project" in index_names


# ---------------------------------------------------------------------------
# H6 — concurrent add/update never leaks a raw sqlite3.IntegrityError
# ---------------------------------------------------------------------------


def test_add_project_race_raises_duplicate_project_error_not_raw_integrity_error(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = ProjectRegistryService(db_path)
    project_dir = tmp_path / "race-project"
    project_dir.mkdir()
    registry.add("race-project", str(project_dir))

    # Simulate two callers racing past the application-level check at the same
    # instant: force the pre-insert duplicate checks to both report "no match",
    # so the raw UNIQUE constraint is what actually stops the second insert.
    monkeypatch.setattr(ProjectRepository, "get_by_name", lambda self, name: None)
    monkeypatch.setattr(ProjectRepository, "get_by_path", lambda self, path: None)

    with pytest.raises(DuplicateProjectError):
        registry.add("race-project", str(project_dir))


def test_update_project_race_raises_duplicate_project_error_not_raw_integrity_error(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = ProjectRegistryService(db_path)
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    dir_b = tmp_path / "b"
    dir_b.mkdir()
    registry.add("project-a", str(dir_a))
    project_b = registry.add("project-b", str(dir_b))

    monkeypatch.setattr(ProjectRepository, "get_by_name", lambda self, name: None)
    monkeypatch.setattr(ProjectRepository, "get_by_path", lambda self, path: None)

    with pytest.raises(DuplicateProjectError):
        registry.update(project_b.id, name="project-a")


# ---------------------------------------------------------------------------
# M1 — session-end + exit-note-history insert are one atomic operation
# ---------------------------------------------------------------------------


def test_session_end_rolls_back_entirely_if_exit_note_history_insert_fails(
    db_path: Path, project_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = SessionService(db_path)
    session = service.start_session(project_id)

    def boom(self, *args, **kwargs):  # noqa: ANN001
        raise RuntimeError("simulated crash during exit-note-history insert")

    monkeypatch.setattr(
        "grafid.db.repositories.exit_note_repository.ExitNoteRepository.insert", boom
    )

    with pytest.raises(RuntimeError):
        service.end_session(session.id, notes=ExitNoteInput(exit_note="done"))

    with DatabaseConnection(db_path) as conn:
        row = SessionRepository(conn).get_by_id(session.id)
        history_count = conn.execute(
            "SELECT COUNT(*) FROM exit_note_history WHERE session_id = ?", (session.id,)
        ).fetchone()[0]

    assert row is not None
    assert row.ended_at is None, "session must still be active — the whole write rolled back"
    assert row.is_active
    assert history_count == 0


def test_session_end_succeeds_and_writes_both_rows_together(
    db_path: Path, project_id: int
) -> None:
    service = SessionService(db_path)
    session = service.start_session(project_id)
    service.end_session(session.id, notes=ExitNoteInput(exit_note="shipped it"))

    with DatabaseConnection(db_path) as conn:
        row = SessionRepository(conn).get_by_id(session.id)
        history = conn.execute(
            "SELECT exit_note FROM exit_note_history WHERE session_id = ?", (session.id,)
        ).fetchall()

    assert row is not None
    assert row.ended_at is not None
    assert len(history) == 1
    assert history[0]["exit_note"] == "shipped it"


# ---------------------------------------------------------------------------
# M2 — retention must not delete a snapshot an active session still references
# ---------------------------------------------------------------------------


def test_retention_does_not_delete_snapshot_referenced_by_active_session(
    db_path: Path, project_id: int
) -> None:
    persistence = SnapshotPersistenceService(db_path)
    first_snapshot = persistence.save_snapshot(project_id, _scan())

    session_service = SessionService(db_path)
    session = session_service.start_session(project_id)
    with DatabaseConnection(db_path) as conn:
        stored = SessionRepository(conn).get_by_id(session.id)
    assert stored is not None
    assert stored.snapshot_id_at_start == first_snapshot.id

    # Enough additional snapshots that the first one would normally be pruned.
    for _ in range(5):
        persistence.save_snapshot(project_id, _scan())

    retention = SnapshotRetentionService(
        db_path, policy=RetentionPolicy(max_snapshots_per_project=1, max_age_days=None)
    )
    with DatabaseConnection(db_path) as conn:
        removed = retention.apply_for_project(project_id, connection=conn)
        conn.commit()

    with DatabaseConnection(db_path) as conn:
        survivor_ids = {
            row["id"]
            for row in conn.execute(
                "SELECT id FROM scan_snapshots WHERE project_id = ?", (project_id,)
            ).fetchall()
        }

    assert first_snapshot.id in survivor_ids, (
        "snapshot referenced by an active session's snapshot_id_at_start must survive"
    )
    assert removed == 4, "the other 4 unprotected snapshots beyond the limit-of-1 should still be pruned"


def test_retention_still_prunes_snapshots_once_the_referencing_session_ends(
    db_path: Path, project_id: int
) -> None:
    persistence = SnapshotPersistenceService(db_path)
    first_snapshot = persistence.save_snapshot(project_id, _scan())

    session_service = SessionService(db_path)
    session = session_service.start_session(project_id)
    session_service.end_session(session.id)  # no longer active — no longer protected

    for _ in range(5):
        persistence.save_snapshot(project_id, _scan())

    retention = SnapshotRetentionService(
        db_path, policy=RetentionPolicy(max_snapshots_per_project=1, max_age_days=None)
    )
    with DatabaseConnection(db_path) as conn:
        retention.apply_for_project(project_id, connection=conn)
        conn.commit()

    with DatabaseConnection(db_path) as conn:
        survivor_ids = {
            row["id"]
            for row in conn.execute(
                "SELECT id FROM scan_snapshots WHERE project_id = ?", (project_id,)
            ).fetchall()
        }

    assert first_snapshot.id not in survivor_ids


# ---------------------------------------------------------------------------
# L4 — resume trim-then-insert is one atomic operation
# ---------------------------------------------------------------------------


def test_resume_trim_and_insert_roll_back_together_on_crash(
    db_path: Path, project_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ResumeService(db_path)
    for _ in range(6):
        service.generate_resume(project_id, mode="short", persist=True, replace_latest_short=False)

    with DatabaseConnection(db_path) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM resume_summaries WHERE project_id = ? AND mode = 'short'",
            (project_id,),
        ).fetchone()[0]
    assert before == 6

    def boom(self, *args, **kwargs):  # noqa: ANN001
        raise RuntimeError("simulated crash after trim")

    monkeypatch.setattr(
        "grafid.db.repositories.resume_repository.ResumeRepository.insert", boom
    )

    with pytest.raises(RuntimeError):
        service.generate_resume(project_id, mode="short", persist=True, replace_latest_short=True)

    with DatabaseConnection(db_path) as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM resume_summaries WHERE project_id = ? AND mode = 'short'",
            (project_id,),
        ).fetchone()[0]

    assert after == before, "trim must roll back too — no row may be lost when the insert fails"


def test_resume_trim_and_insert_succeed_together(db_path: Path, project_id: int) -> None:
    """Trim runs before insert each call, so the steady state is `keep + 1`, not `keep`
    (trim only fires once the count *exceeds* keep=5; unchanged pre-existing behavior)."""
    service = ResumeService(db_path)
    for _ in range(8):
        service.generate_resume(project_id, mode="short", persist=True, replace_latest_short=True)

    with DatabaseConnection(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM resume_summaries WHERE project_id = ? AND mode = 'short'",
            (project_id,),
        ).fetchone()[0]

    assert count == 6
