"""Tests for scan snapshot persistence (Milestone 2C)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from grafid.core.constants import SCHEMA_VERSION
from grafid.core.exceptions import SnapshotError
from grafid.db.schema import get_schema_version
from grafid.services.snapshot_persistence import SnapshotPersistenceService
from grafid.scanner.models import ScanResult, TaskFinding


@pytest.fixture
def persistence(db_path: Path) -> SnapshotPersistenceService:
    return SnapshotPersistenceService(db_path)


def _sample_scan_result(*, findings: int = 1) -> ScanResult:
    task_findings = [
        TaskFinding(
            file_path="src/a.py",
            line_number=10,
            marker="TODO",
            text="refactor",
            severity="low",
            created_at="2026-01-01T00:00:00+00:00",
        )
    ][:findings]
    return ScanResult(
        project_name="demo",
        project_path="/demo",
        scanned_files=[],
        findings=task_findings,
        skipped_count=2,
        duration_seconds=0.5,
        warnings=["sample warning"],
    )


def test_schema_includes_snapshot_tables(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        version = get_schema_version(conn)

    assert "scan_snapshots" in tables
    assert "scan_findings" in tables
    assert version == SCHEMA_VERSION


def test_snapshot_creation_and_finding_persistence(
    persistence: SnapshotPersistenceService,
    db_path: Path,
    project_id: int,
) -> None:
    result = _sample_scan_result()
    snapshot = persistence.save_snapshot(project_id=project_id, scan_result=result)

    assert snapshot.id > 0
    assert snapshot.findings_count == 1
    assert snapshot.scanned_files_count == 0
    assert snapshot.skipped_files_count == 2
    assert snapshot.warnings_count == 1

    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM scan_findings WHERE snapshot_id = ?",
            (snapshot.id,),
        ).fetchone()[0]
    assert count == 1


def test_empty_scan_snapshot(
    persistence: SnapshotPersistenceService, project_id: int
) -> None:
    result = _sample_scan_result(findings=0)
    snapshot = persistence.save_snapshot(project_id=project_id, scan_result=result)
    assert snapshot.findings_count == 0


def test_history_retention_keeps_multiple_scans(
    persistence: SnapshotPersistenceService, project_id: int
) -> None:
    persistence.save_snapshot(project_id, _sample_scan_result())
    persistence.save_snapshot(project_id, _sample_scan_result())

    history = persistence.list_history(project_id)
    assert len(history) == 2
    assert history[0].snapshot_id != history[1].snapshot_id


def test_interrupted_write_rolls_back(
    persistence: SnapshotPersistenceService,
    db_path: Path,
    project_id: int,
) -> None:
    with patch(
        "grafid.db.repositories.scan_finding_repository.ScanFindingRepository.insert_many",
        side_effect=sqlite3.OperationalError("simulated write failure"),
    ):
        with pytest.raises(SnapshotError):
            persistence.save_snapshot(project_id, _sample_scan_result())

    with sqlite3.connect(db_path) as conn:
        snapshot_count = conn.execute(
            "SELECT COUNT(*) FROM scan_snapshots"
        ).fetchone()[0]
        finding_count = conn.execute(
            "SELECT COUNT(*) FROM scan_findings"
        ).fetchone()[0]

    assert snapshot_count == 0
    assert finding_count == 0
