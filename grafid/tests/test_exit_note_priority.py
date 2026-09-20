"""MVP stabilization: Exit Note priority in resume flow."""

from __future__ import annotations

from pathlib import Path

from grafid.ipc.dashboard_handlers import handle_project_detail, handle_refresh_resume
from grafid.ipc.session_handlers import handle_close_session, handle_start_session
from grafid.resume.session_signals import resolve_summary_session_fields
from grafid.db.connection import DatabaseConnection
from grafid.models.session import ExitNoteInput
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.session_service import SessionService


def _add_project(db_path, tmp_path: Path, name: str = "demo") -> int:
    project_dir = tmp_path / name
    project_dir.mkdir()
    (project_dir / "main.py").write_text("# TODO: scanner noise should not win\n", encoding="utf-8")
    record = ProjectRegistryService(db_path).add(name, str(project_dir))
    return record.id


def test_close_session_saves_all_exit_fields(db_path, config_manager, tmp_path: Path) -> None:
    project_id = _add_project(db_path, tmp_path)
    SessionService(db_path).start_session(project_id)

    response = handle_close_session(
        project_id,
        exit_note="Shipped summary cleanup",
        unfinished="Wire exit-note tests",
        next_step="Run manual MVP check",
        blocker="None for now",
        config_manager=config_manager,
    )
    assert response.ok is True
    panel = response.data["resume_panel"]
    assert "Shipped summary cleanup" in (panel["exit_note"] or "")
    assert "Wire exit-note tests" in (panel["exit_note"] or "")
    assert panel["next_step"] == "Run manual MVP check"
    assert panel["blocker"] == "None for now"
    summary = panel["startup_summary"]["summary_text"]
    assert "Shipped summary cleanup" in summary
    assert "exit note" in panel["startup_summary"]["sources_used"]


def test_exit_note_survives_refresh(db_path, config_manager, tmp_path: Path) -> None:
    project_id = _add_project(db_path, tmp_path, "refresh-proj")
    SessionService(db_path).start_session(project_id)
    handle_close_session(
        project_id,
        exit_note="Stable after refresh",
        next_step="Continue polish",
        config_manager=config_manager,
    )

    refresh = handle_refresh_resume(project_id, config_manager)
    assert refresh.ok is True
    panel = refresh.data["resume_panel"]
    assert panel["exit_note"] == "Stable after refresh"
    assert "Stable after refresh" in panel["startup_summary"]["summary_text"]


def test_active_session_does_not_erase_last_exit_note(db_path, config_manager, tmp_path: Path) -> None:
    project_id = _add_project(db_path, tmp_path, "active-proj")
    SessionService(db_path).start_session(project_id)
    handle_close_session(
        project_id,
        exit_note="Finished milestone 11 polish",
        next_step="Manual dogfood",
        config_manager=config_manager,
    )

    handle_start_session(project_id, config_manager=config_manager)
    detail = handle_project_detail(project_id, config_manager)
    assert detail.ok is True
    panel = detail.data["resume_panel"]
    assert panel["latest_session"]["is_active"] is True
    assert panel["exit_note"] == "Finished milestone 11 polish"
    summary = panel["startup_summary"]["summary_text"]
    assert "Finished milestone 11 polish" in summary
    assert "pick up work on" not in summary.lower()


def test_exit_note_beats_scanner_in_summary(db_path, config_manager, tmp_path: Path) -> None:
    project_id = _add_project(db_path, tmp_path, "scan-proj")
    SessionService(db_path).start_session(project_id)
    handle_close_session(
        project_id,
        exit_note="Resume driven by exit note only",
        config_manager=config_manager,
    )

    refresh = handle_refresh_resume(project_id, config_manager)
    summary = refresh.data["resume_panel"]["startup_summary"]["summary_text"]
    assert "Resume driven by exit note only" in summary
    assert "scanner noise" not in summary.lower()
    assert summary.startswith("Where you left off:")


def test_resolve_summary_session_fields_prefers_last_ended(
    db_path, tmp_path: Path
) -> None:
    project_id = _add_project(db_path, tmp_path, "signals-proj")
    sessions = SessionService(db_path)
    sessions.start_session(project_id)
    sessions.end_active_session_for_project(
        project_id,
        notes=ExitNoteInput(exit_note="First exit", next_step="Step A"),
    )
    sessions.start_session(project_id)

    with DatabaseConnection(db_path) as conn:
        signals = resolve_summary_session_fields(conn, project_id)

    assert signals.has_active_session is True
    assert signals.exit_note == "First exit"
    assert signals.next_step == "Step A"
