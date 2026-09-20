"""v1.0 hardening regression tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from grafid.db.connection import DatabaseConnection
from grafid.ipc.dashboard_handlers import handle_dashboard
from grafid.ipc.handlers import handle_bootstrap
from grafid.services.project_overview import build_bootstrap_projects, project_to_dict
from grafid.handoff.schema import (
    HANDOFF_SCHEMA_VERSION as GRAFITALK_HANDOFF_SCHEMA_VERSION,
    HANDOFF_SOURCE as GRAFITALK_HANDOFF_SOURCE,
)
from grafid.services.project_export import build_export_payload, suggested_filename
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.snapshot_persistence import SnapshotPersistenceService
from grafid.scanner.models import ScanResult


def _insert_snapshot_with_git(
    db_path: Path,
    project_id: int,
    *,
    modified_files_json: str = '["a.txt"]',
) -> int:
    persistence = SnapshotPersistenceService(db_path)
    scan = ScanResult(
        project_name="test",
        project_path=str(Path(".")),
        duration_seconds=0.1,
    )
    from grafid.git.models import GitState

    git_state = GitState(is_git_repo=True, modified_files=("a.txt",))
    record = persistence.save_snapshot(project_id, scan, git_state=git_state)
    with DatabaseConnection(db_path) as conn:
        conn.execute(
            "UPDATE git_snapshots SET modified_files_json = ? WHERE snapshot_id = ?",
            (modified_files_json, record.id),
        )
        conn.commit()
    return record.id


def test_corrupt_git_json_does_not_break_dashboard(
    db_path, config_manager, project_id: int
) -> None:
    _insert_snapshot_with_git(db_path, project_id, modified_files_json="{not-json")

    response = handle_dashboard(config_manager)
    assert response.ok is True
    row = next(p for p in response.data["projects"] if p["id"] == project_id)
    assert row["name"] == "test-project"


def test_bootstrap_survives_one_bad_project(
    db_path, tmp_path: Path, monkeypatch
) -> None:
    import grafid.services.project_overview as project_overview

    good_dir = tmp_path / "good"
    good_dir.mkdir()
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    registry = ProjectRegistryService(db_path)
    good = registry.add("good-project", str(good_dir))
    bad = registry.add("bad-project", str(bad_dir))
    real_payload = project_overview.project_detail_payload

    def fake_payload(conn, db_path_arg, record):
        if record.id == bad.id:
            raise RuntimeError("simulated preload failure")
        return real_payload(conn, db_path_arg, record)

    monkeypatch.setattr(project_overview, "project_detail_payload", fake_payload)

    projects = registry.list_projects()
    rows = build_bootstrap_projects(db_path, projects)
    assert len(rows) == 2
    by_id = {row["id"]: row for row in rows}
    assert not by_id[good.id].get("load_error")
    assert by_id[good.id]["resume_panel"] is not None
    assert by_id[bad.id]["load_error"]
    assert by_id[bad.id]["history"] == []


def test_path_accessible_false_when_folder_missing(db_path, tmp_path: Path) -> None:
    project_dir = tmp_path / "vanished"
    project_dir.mkdir()
    record = ProjectRegistryService(db_path).add("vanished", str(project_dir))
    project_dir.rmdir()

    payload = project_to_dict(record)
    assert payload["path_accessible"] is False


def test_malformed_history_row_skipped(db_path, project_id: int) -> None:
    persistence = SnapshotPersistenceService(db_path)
    scan = ScanResult(
        project_name="test",
        project_path=str(Path(".")),
        duration_seconds=0.1,
    )
    persistence.save_snapshot(project_id, scan)
    with DatabaseConnection(db_path) as conn:
        conn.execute(
            "UPDATE scan_snapshots SET findings_count = -1 WHERE project_id = ?",
            (project_id,),
        )
        conn.commit()

    entries = persistence.list_history(project_id)
    assert entries == []


def test_export_survives_corrupt_git_json(db_path, project_id: int) -> None:
    _insert_snapshot_with_git(db_path, project_id, modified_files_json="broken")

    payload = build_export_payload(db_path, project_id, "handoff")
    assert payload["source"] == GRAFITALK_HANDOFF_SOURCE
    assert payload["schema_version"] == GRAFITALK_HANDOFF_SCHEMA_VERSION
    assert payload["project_name"] == "test-project"
    assert "Full export unavailable" not in json.dumps(payload)


def test_suggested_filename_non_ascii_project_name() -> None:
    when = datetime(2026, 6, 7, tzinfo=UTC)
    name = suggested_filename("プロジェクト", "json", exported_at=when)
    assert name == "project-context-2026-06-07.json"
    long_name = "A" * 120
    slugged = suggested_filename(long_name, "markdown", exported_at=when)
    assert slugged.endswith(".md")
    assert len(slugged) < 90


def test_bootstrap_ipc_with_corrupt_git(db_path, config_manager, project_id: int) -> None:
    _insert_snapshot_with_git(db_path, project_id, modified_files_json="null")

    response = handle_bootstrap(config_manager=config_manager)
    assert response.ok is True
    assert response.data is not None
    assert any(p["id"] == project_id for p in response.data["projects"])


def test_git_repository_safe_decode() -> None:
    from grafid.db.repositories import git_snapshot_repository as mod

    assert mod._loads_list("{bad") == []
    assert mod._loads_commits("not-a-list") == []
    assert mod._loads_list(json.dumps(["x"])) == ["x"]
