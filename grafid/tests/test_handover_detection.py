"""Tests for HANDOVER.md detection (Mesencsi-style layout)."""

from __future__ import annotations

from pathlib import Path

from grafid.resume.human_context import build_dashboard_summary
from grafid.resume.workflow_artifacts import load_workflow_artifacts, primary_handoff


def test_parent_handover_md_detected(tmp_path: Path) -> None:
    root = tmp_path / "project"
    backend = root / "backend"
    backend.mkdir(parents=True)
    (root / "HANDOVER.md").write_text(
        "# Mesencsi Handover\n\nFocus area: deployment / QA\n\nNext step: review admin polish\n",
        encoding="utf-8",
    )
    (backend / "README.md").write_text(
        "# Backend\n\nSee [HANDOVER.md](../HANDOVER.md) for details.\n",
        encoding="utf-8",
    )
    artifacts = load_workflow_artifacts(str(backend))
    handoff = primary_handoff(artifacts)
    assert handoff is not None
    assert handoff.filename == "HANDOVER.md"
    assert handoff.focus_area == "deployment / QA"


def test_dashboard_uses_handover_not_readme_pointer(tmp_path: Path) -> None:
    root = tmp_path / "project"
    backend = root / "backend"
    backend.mkdir(parents=True)
    (root / "HANDOVER.md").write_text(
        "# Mesencsi Handover\n\nFocus area: deployment / QA\n",
        encoding="utf-8",
    )
    (backend / "README.md").write_text(
        "# Backend\n\nSee [HANDOVER.md](../HANDOVER.md).\n",
        encoding="utf-8",
    )
    artifacts = load_workflow_artifacts(str(backend))
    result = build_dashboard_summary(
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=True,
        artifacts=artifacts,
        open_task_count=None,
        has_scan=False,
        git_label=None,
    )
    assert "Where you left off" in result["summary_text"]
    assert "deployment" in result["summary_text"].lower()
    assert "HANDOVER.md" in result["sources_used"]
    assert "[HANDOVER.md]" not in result["summary_text"]
    assert "Handoff found:" not in result["summary_text"]
