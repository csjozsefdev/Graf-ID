"""Tests for structured workflow-state extraction."""

from __future__ import annotations

from pathlib import Path

from grafid.resume.summary_composition import CompositionInput, compose_workflow_summary
from grafid.resume.workflow_artifacts import load_workflow_artifacts
from grafid.resume.workflow_state import extract_workflow_state, workflow_anchor_phrase


def test_readme_milestone_becomes_recent_work(tmp_path: Path) -> None:
    project = tmp_path / "grafid"
    project.mkdir()
    (project / "README.md").write_text(
        "# Graf-Id\n\n"
        "Local-first utility.\n\n"
        "## Milestone 9\n\nOlder work.\n\n"
        "## Milestone 11 — MVP polish + stability\n\n"
        "UX pass before release.\n",
        encoding="utf-8",
    )
    artifacts = load_workflow_artifacts(str(project))
    state = extract_workflow_state(artifacts)
    assert state.recent_work == "MVP polish + stability"
    assert state.confidence in ("medium", "strong")
    phrase = workflow_anchor_phrase(state, project_name="Graf-Id")
    assert phrase is not None
    assert "MVP polish" in phrase
    assert "pick up work on" not in phrase


def test_handoff_focus_beats_readme_milestone(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / "README.md").write_text(
        "## Milestone 2 — polish widgets\n", encoding="utf-8"
    )
    (project / "HANDOFF.md").write_text(
        "# Handoff\n\nFocus area: deployment / QA\n\nNext step: ship admin UI\n",
        encoding="utf-8",
    )
    artifacts = load_workflow_artifacts(str(project))
    state = extract_workflow_state(artifacts)
    assert state.current_focus == "deployment / QA"
    assert state.next_step == "ship admin UI"


def test_compose_uses_recent_work_not_generic_project_name(tmp_path: Path) -> None:
    project = tmp_path / "grafid"
    project.mkdir()
    (project / "README.md").write_text(
        "# Graf-Id\n\n"
        "## Milestone 11 — summary cleanup and workflow signal filtering\n\n",
        encoding="utf-8",
    )
    artifacts = load_workflow_artifacts(str(project))
    result = compose_workflow_summary(
        CompositionInput(project_name="Graf-Id", artifacts=artifacts, has_scan=True)
    )
    primary = "\n".join(result.primary_lines)
    assert "pick up work on Graf-Id" not in primary
    assert "summary cleanup" in primary.lower() or "workflow signal" in primary.lower()
