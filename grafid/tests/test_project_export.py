"""Project export (handoff / JSON / Markdown / TXT) through the real backend path."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from grafid.core.exceptions import ValidationError
from grafid.db.connection import DatabaseConnection
from grafid.git.models import GitCommitInfo, GitState
from grafid.handoff.schema import EXTENSION_KEY
from grafid.handoff.validate import parse_handoff_bytes
from grafid.tests.grafitalk_contract import check_grafitalk_compatibility
from grafid.models.session import ExitNoteInput
from grafid.scanner.models import ScanResult, TaskFinding
from grafid.services.project_export import (
    build_export_payload,
    export_to_path,
    render_export_content,
    suggested_filename,
)
from grafid.services.session_service import SessionService
from grafid.services.snapshot_persistence import SnapshotPersistenceService


def _snapshot(db_path, project_id: int, *, git: GitState | None, findings=()) -> None:
    scan = ScanResult(
        project_name="test-project",
        project_path=str(Path(".")),
        duration_seconds=0.1,
        findings=list(findings),
    )
    SnapshotPersistenceService(db_path).save_snapshot(project_id, scan, git_state=git)


def _end_session(db_path, project_id: int, **notes) -> None:
    service = SessionService(db_path)
    started = service.start_session(project_id)
    service.end_session(started.id, notes=ExitNoteInput(**notes))


def _commit(subject: str, n: int) -> GitCommitInfo:
    return GitCommitInfo(
        commit_hash=f"{n:040x}", subject=subject, author="dev", committed_at="2026-09-01T10:00:00+00:00"
    )


# ------------------------------------------------------------------ filenames


def test_suggested_filenames_are_safe_and_describe_the_kind() -> None:
    when = datetime(2026, 6, 7, tzinfo=UTC)
    assert suggested_filename("Mesencsi / v1", "markdown", exported_at=when) == (
        "mesencsi-v1-summary-2026-06-07.md"
    )
    assert suggested_filename("Mesencsi", "txt", exported_at=when).endswith("-summary-2026-06-07.txt")
    assert suggested_filename("Mesencsi", "json", exported_at=when) == "mesencsi-context-2026-06-07.json"
    assert suggested_filename("Mesencsi", "handoff", exported_at=when) == (
        "mesencsi-grafitalk-handoff-2026-06-07.json"
    )
    assert suggested_filename("プロジェクト", "handoff", exported_at=when).startswith("project-")


# --------------------------------------------------------------------- payloads


def test_handoff_export_is_lean_and_grafitalk_compatible(db_path, project_id: int) -> None:
    payload = build_export_payload(db_path, project_id, "handoff")
    assert payload["source"] == "graf-id" and payload["schema_version"] == "0.1"
    assert payload["project_name"] == "test-project"
    assert EXTENSION_KEY not in payload
    assert check_grafitalk_compatibility(payload) == []


def test_json_export_has_the_extension_and_round_trips(db_path, project_id: int, tmp_path: Path) -> None:
    target = tmp_path / "ctx.json"
    result = export_to_path(db_path, project_id, target, "json")
    assert result.format == "json" and result.bytes_written == target.stat().st_size
    parsed = parse_handoff_bytes(target.read_bytes())
    assert parsed.data["project_name"] == "test-project"
    assert parsed.extension is not None and parsed.extension["extension_version"] == 1
    assert parsed.extension["project"]["name"] == "test-project"
    assert check_grafitalk_compatibility(json.loads(target.read_text(encoding="utf-8"))) == []


def test_markdown_and_txt_exports_write_labelled_sections(db_path, project_id: int, tmp_path: Path) -> None:
    md = tmp_path / "e.md"
    export_to_path(db_path, project_id, md, "markdown")
    assert md.read_text(encoding="utf-8").startswith("# Project\ntest-project\n")
    txt = tmp_path / "e.txt"
    export_to_path(db_path, project_id, txt, "txt")
    assert txt.read_text(encoding="utf-8").startswith("Project:\ntest-project\n")


def test_export_invalid_format_and_directory_target(db_path, project_id: int, tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="Unsupported export format"):
        export_to_path(db_path, project_id, tmp_path / "bad.bin", "pdf")
    with pytest.raises(ValidationError, match="directory"):
        export_to_path(db_path, project_id, tmp_path, "json")


def test_unknown_project_is_a_validation_error(db_path, tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        export_to_path(db_path, 9999, tmp_path / "x.json", "json")


def test_export_write_is_atomic_and_leaves_no_temp_files(db_path, project_id: int, tmp_path: Path) -> None:
    target = tmp_path / "out" / "h.json"
    export_to_path(db_path, project_id, target, "handoff")
    assert [p.name for p in target.parent.iterdir()] == ["h.json"]


def test_long_summary_is_preserved_in_markdown(db_path, project_id: int) -> None:
    payload = build_export_payload(db_path, project_id, "markdown")
    payload["changes"] = ["Z" * 600]
    assert "Z" * 600 in render_export_content(payload, "markdown")


# ------------------------------------------- real project states through exports


def test_project_with_a_blocker_and_project_without(db_path, project_id: int) -> None:
    _end_session(db_path, project_id, exit_note="Payments half done.", blocker="Waiting for the API key",
                 next_step="Finish the receipt page")
    with_blocker = build_export_payload(db_path, project_id, "handoff")
    assert with_blocker["blockers"] == ["Waiting for the API key"]
    assert with_blocker["next_steps"] == ["Finish the receipt page"]
    assert with_blocker["changes"][0] == "Payments half done."

    _end_session(db_path, project_id, exit_note="Payments done.", blocker="None", next_step="Ship")
    without = build_export_payload(db_path, project_id, "handoff")
    assert "blockers" not in without


def test_clean_repository_reports_clean_and_lists_no_files(db_path, project_id: int) -> None:
    _snapshot(db_path, project_id, git=GitState(is_git_repo=True, current_branch="main", is_dirty=False))
    payload = build_export_payload(db_path, project_id, "handoff")
    assert "files" not in payload
    assert "Git: working tree clean on main." in payload["notes"]


def test_dirty_repository_lists_changed_files_and_state(db_path, project_id: int) -> None:
    _snapshot(
        db_path, project_id,
        git=GitState(is_git_repo=True, current_branch="dev", is_dirty=True,
                     modified_files=("src/a.py", "README.md"), staged_files=("src/b.py",)),
    )
    payload = build_export_payload(db_path, project_id, "json")
    assert payload["files"] == ["src/a.py", "README.md", "src/b.py"]
    assert payload[EXTENSION_KEY]["git"]["state"] == "dirty"
    assert payload[EXTENSION_KEY]["git"]["branch"] == "dev"


def test_untracked_only_repository_is_clean_in_the_export(db_path, project_id: int) -> None:
    from grafid.git.status_parser import parse_porcelain_status

    staged, modified, dirty = parse_porcelain_status("?? scratch/\n?? notes.txt\n")
    _snapshot(db_path, project_id, git=GitState(
        is_git_repo=True, current_branch="main", is_dirty=dirty,
        modified_files=tuple(modified), staged_files=tuple(staged)))
    payload = build_export_payload(db_path, project_id, "handoff")
    assert "files" not in payload and "working tree clean" in payload["notes"]


def test_recent_commits_feed_changes_but_only_trusted_subjects(db_path, project_id: int) -> None:
    _snapshot(db_path, project_id, git=GitState(
        is_git_repo=True, current_branch="main",
        latest_commits=(_commit("fix: pin release runtime", 1), _commit("chore: bump", 2),
                        _commit("Quick refhresh", 3), _commit("feat: add flow tracing", 4))))
    payload = build_export_payload(db_path, project_id, "json")
    assert payload["changes"] == ["Pin release runtime", "Add flow tracing"]
    subjects = [c["subject"] for c in payload[EXTENSION_KEY]["git"]["recent_commits"]]
    assert "fix: pin release runtime" in subjects


def test_scanner_markers_and_venv_findings_never_reach_any_export(db_path, project_id: int) -> None:
    findings = [
        TaskFinding(file_path="apps/x.tsx", line_number=3, marker="NEXT",
                    text='{ label: "Next", text: "text-primary" },', severity="low", created_at=""),
        TaskFinding(file_path=".venv-314-dev/Lib/site-packages/PIL/Image.py", line_number=9,
                    marker="HACK", text="to support hi-res rendering", severity="low", created_at=""),
        TaskFinding(file_path="src/app.py", line_number=1, marker="TODO",
                    text="wire the settings page to the backend", severity="low", created_at=""),
    ]
    _snapshot(db_path, project_id, git=None, findings=findings)
    for fmt in ("json", "handoff", "markdown", "txt"):
        payload = build_export_payload(db_path, project_id, fmt)
        rendered = render_export_content(payload, fmt)
        assert "label" not in rendered and "PIL" not in rendered and "hi-res" not in rendered
        assert "settings page to the backend" not in rendered  # markers are evidence, not context


def test_unicode_project_name_and_notes_export_intact(db_path, project_id: int, tmp_path: Path) -> None:
    with DatabaseConnection(db_path) as conn:
        conn.execute("UPDATE projects SET name = ?, notes = ? WHERE id = ?",
                     ("Kosár – webshop ✓", "Árvíztűrő tükörfúrógép 日本語", project_id))
        conn.commit()
    target = tmp_path / "u.json"
    export_to_path(db_path, project_id, target, "handoff")
    body = json.loads(target.read_text(encoding="utf-8"))
    assert body["project_name"] == "Kosár – webshop ✓"
    assert "Árvíztűrő tükörfúrógép 日本語" in body["notes"]


def test_very_large_project_notes_are_bounded(db_path, project_id: int, tmp_path: Path) -> None:
    with DatabaseConnection(db_path) as conn:
        conn.execute("UPDATE projects SET notes = ? WHERE id = ?", ("long note " * 30_000, project_id))
        conn.commit()
    target = tmp_path / "big.json"
    export_to_path(db_path, project_id, target, "json")
    assert target.stat().st_size < 100_000
    assert check_grafitalk_compatibility(json.loads(target.read_text(encoding="utf-8"))) == []


# --------------------------------------------------------------- export safety


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted in this environment")


def test_symlinked_workflow_document_outside_the_project_is_never_read(
    db_path, project_id: int, tmp_path: Path
) -> None:
    secret = tmp_path / "outside-secret.md"
    secret.write_text("# Secret plan\nFocus: leak the API key sk-live-123456\nNext: exfiltrate\n", encoding="utf-8")
    project_dir = tmp_path / "test-project"
    _symlink_or_skip(project_dir / "HANDOVER.md", secret)

    for fmt in ("json", "handoff", "markdown", "txt"):
        rendered = render_export_content(build_export_payload(db_path, project_id, fmt), fmt)
        assert "sk-live-123456" not in rendered and "exfiltrate" not in rendered


def test_parent_folder_documents_and_absolute_paths_stay_out_of_exports(
    db_path, project_id: int, tmp_path: Path
) -> None:
    (tmp_path / "HANDOVER.md").write_text("# Parent\nFocus: sibling project secrets\n", encoding="utf-8")
    payload = build_export_payload(db_path, project_id, "json")
    text = json.dumps(payload)
    assert "sibling project secrets" not in text
    assert str(tmp_path) not in text and str(tmp_path).replace("\\", "/") not in text
    for ref in payload.get(EXTENSION_KEY, {}).get("context", {}).get("workflow_files", []):
        assert not ref["path"].startswith(("..", "/")) and ":" not in ref["path"]


def test_secret_looking_changed_files_are_not_listed(db_path, project_id: int) -> None:
    _snapshot(db_path, project_id, git=GitState(
        is_git_repo=True, current_branch="main", is_dirty=True,
        modified_files=(".env", "config/.env.production", "keys/server.pem", "src/app.py")))
    assert build_export_payload(db_path, project_id, "handoff")["files"] == ["src/app.py"]


def test_no_database_internals_or_local_paths_in_the_full_json(db_path, project_id: int) -> None:
    text = json.dumps(build_export_payload(db_path, project_id, "json"))
    for forbidden in ('"id"', "project_id", "snapshot_id", "graf-id.db", str(db_path.parent)):
        assert forbidden not in text
