"""Tests for refresh context with workflow artifacts."""

from __future__ import annotations

from pathlib import Path

from grafid.ipc.dashboard_handlers import handle_refresh_resume


def test_refresh_context_uses_handoff_file(
    db_path, config_manager, tmp_path: Path
) -> None:
    project_dir = tmp_path / "mesencsi-backend"
    project_dir.mkdir()
    (project_dir / "HANDOFF.md").write_text(
        "# Mesencsi project handoff\n\nFocus area: deployment / QA\n\nNext step: polish admin UI\n",
        encoding="utf-8",
    )

    from grafid.ipc.project_handlers import handle_add_project

    added = handle_add_project(
        "mesencsi-backend",
        str(project_dir),
        config_manager=config_manager,
    )
    assert added.ok is True
    project_id = added.data["project"]["id"]

    response = handle_refresh_resume(project_id, config_manager)
    assert response.ok is True
    panel = response.data["resume_panel"]
    summary = panel["startup_summary"]
    assert summary["source"] == "summary_engine"
    assert "Where you left off" in summary["summary_text"] or "deployment" in summary["summary_text"].lower()
    assert "Context:" not in summary["summary_text"]
    assert "id=" not in summary["summary_text"]
    assert "HANDOFF.md" in panel.get("workflow_files", [])
