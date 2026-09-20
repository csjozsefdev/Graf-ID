"""Tests for deterministic resume engine (Milestone 5)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from grafid.core.constants import SCHEMA_VERSION
from grafid.core.exceptions import ResumeError
from grafid.db.schema import get_schema_version
from grafid.models.session import ExitNoteInput
from grafid.models.snapshot import PersistedFindingRecord
from grafid.resume.generator import ResumeSummaryGenerator
from grafid.resume.loader import ResumeDataLoader
from grafid.resume.models import ResumeBundle
from grafid.services.resume_service import ResumeService
from grafid.services.session_service import SessionService
from grafid.services.snapshot_persistence import SnapshotPersistenceService
from grafid.scanner.models import ScanResult, TaskFinding


def _finding(path: str, line: int, marker: str, text: str) -> PersistedFindingRecord:
    return PersistedFindingRecord(
        id=1,
        snapshot_id=1,
        file_path=path,
        line_number=line,
        marker=marker,
        text=text,
        severity="low",
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_schema_includes_resume_summaries(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        version = get_schema_version(conn)
    assert "resume_summaries" in tables
    assert version == SCHEMA_VERSION


def test_priority_ordering_in_generator() -> None:
    bundle = ResumeBundle(
        project_id=1,
        project_name="demo",
        project_path="/demo",
        session=None,
        snapshot=None,
        findings=(),
        git=None,
        using_active_session=False,
    )
    from grafid.models.session import WorkSessionRecord

    session = WorkSessionRecord(
        id=1,
        project_id=1,
        started_at="2026-01-01T10:00:00+00:00",
        ended_at="2026-01-01T12:00:00+00:00",
        exit_note="Finished API layer",
        blocker="Waiting on review",
        next_step="Add tests",
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
    titles = [section.title for section in summary.sections]
    assert titles.index("Last session note (done)") < titles.index("Next step")
    assert titles.index("Next step") < titles.index("Current blocker")


def test_duplicate_suppression_in_findings() -> None:
    findings = (
        _finding("a.py", 1, "TODO", "same task"),
        _finding("a.py", 1, "TODO", "same task"),
        _finding("b.py", 2, "FIXME", "fix bug"),
    )
    bundle = ResumeBundle(
        project_id=1,
        project_name="demo",
        project_path="/demo",
        session=None,
        snapshot=None,
        findings=findings,
        git=None,
        using_active_session=False,
    )
    summary = ResumeSummaryGenerator().generate(bundle, mode="short")
    body = summary.body
    assert body.count("same task") == 1
    assert "FIXME b.py:2" in body


def test_empty_project_handling() -> None:
    bundle = ResumeBundle(
        project_id=1,
        project_name="empty",
        project_path="/empty",
        session=None,
        snapshot=None,
        findings=(),
        git=None,
        using_active_session=False,
    )
    summary = ResumeSummaryGenerator().generate(bundle, mode="short")
    assert "No work session has been recorded yet." in summary.body
    assert "No scan has been run for this project yet." in summary.body


def test_resume_persistence_and_generation(
    db_path, project_id: int
) -> None:
    persistence = SnapshotPersistenceService(db_path)
    persistence.save_snapshot(
        project_id,
        ScanResult(
            project_name="test",
            project_path="/tmp",
            findings=[
                TaskFinding("src/a.py", 10, "TODO", "refactor", "low", "2026-01-01T00:00:00+00:00")
            ],
        ),
    )
    sessions = SessionService(db_path)
    started = sessions.start_session(project_id)
    sessions.end_session(
        started.id,
        notes=ExitNoteInput(
            exit_note="Built resume engine",
            blocker="None",
            next_step="Quality pass",
        ),
    )

    service = ResumeService(db_path)
    summary = service.generate_resume(project_id, mode="short", persist=True)
    assert "Built resume engine" in summary.body
    assert "Quality pass" in summary.body
    assert "TODO src/a.py:10" in summary.body

    stored = service.get_latest_stored_summary(project_id, mode="short")
    assert stored is not None
    assert stored.summary_body == summary.body
    assert summary.resume_id == stored.id


def test_loader_missing_data_only_project(db_path, project_id: int) -> None:
    loader = ResumeDataLoader(db_path)
    bundle = loader.load(project_id)
    assert bundle.session is None
    assert bundle.snapshot is None
    assert bundle.findings == ()
    assert bundle.git is None


def test_history_unchanged_on_repeat(db_path, project_id: int) -> None:
    service = ResumeService(db_path)
    first = service.generate_resume(project_id, mode="short", persist=True)
    second = service.generate_resume(project_id, mode="short", persist=True)
    previous = service.get_previous_stored_summary(project_id, mode="short")
    assert previous is not None
    assert previous.summary_body == first.body
    assert second.body == first.body


def test_missing_project_raises(db_path) -> None:
    service = ResumeService(db_path)
    with pytest.raises(ResumeError, match="not found"):
        service.generate_resume(99999)


def test_detailed_mode_includes_more_findings() -> None:
    findings = tuple(
        _finding(f"f{i}.py", i, "TODO", f"task {i}") for i in range(10)
    )
    bundle = ResumeBundle(
        project_id=1,
        project_name="demo",
        project_path="/demo",
        session=None,
        snapshot=None,
        findings=findings,
        git=None,
        using_active_session=False,
    )
    short = ResumeSummaryGenerator().generate(bundle, mode="short")
    detailed = ResumeSummaryGenerator().generate(bundle, mode="detailed")
    assert short.body.count("TODO") <= detailed.body.count("TODO")


def test_changelog_workflow_artifact_does_not_crash_resume(
    db_path, project_id: int, tmp_path: Path
) -> None:
    project_dir = tmp_path / "test-project"
    (project_dir / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n- Fixed resume refresh\n",
        encoding="utf-8",
    )
    SnapshotPersistenceService(db_path).save_snapshot(
        project_id,
        ScanResult(project_name="test-project", project_path=str(project_dir)),
    )
    summary = ResumeService(db_path).generate_resume(
        project_id, mode="short", persist=True
    )
    assert "Changelog" in summary.body

