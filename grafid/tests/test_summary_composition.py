"""Tests for workflow-first summary composition."""

from __future__ import annotations

from grafid.resume.summary_composition import CompositionInput, compose_workflow_summary
from grafid.resume.workflow_artifacts import WorkflowArtifact


def test_git_not_a_repo_hidden_from_primary() -> None:
    result = compose_workflow_summary(
        CompositionInput(
            project_name="demo",
            git_label="Not a git repository",
            git_state="not_repo",
            git_is_repo=False,
            has_scan=True,
        )
    )
    text = "\n".join(result.primary_lines)
    assert "Not a git" not in text
    assert "Git:" not in text


def test_readme_compressed_not_dumped() -> None:
    readme = WorkflowArtifact(
        filename="README.md",
        relative_path="README.md",
        kind="readme",
        priority_tier="medium",
        title="Graf-Id",
        preview_lines=(
            "Graf-Id Local-first workflow continuity utility for developers. More details follow.",
        ),
        focus_area=None,
        next_step_line=None,
    )
    result = compose_workflow_summary(
        CompositionInput(
            project_name="Graf-Id",
            artifacts=(readme,),
            has_scan=True,
        )
    )
    text = "\n".join(result.primary_lines)
    assert "Project focus:" in text
    assert "local-first workflow" in text.lower()
    assert "Project readme:" not in text
    assert "More details follow" not in text


def test_handoff_becomes_where_you_left_off() -> None:
    handoff = WorkflowArtifact(
        filename="HANDOFF.md",
        relative_path="HANDOFF.md",
        kind="handoff",
        priority_tier="high",
        title="Mesencsi handoff",
        preview_lines=("Deployment checklist pending.",),
        focus_area="deployment / QA",
        next_step_line="polish admin UI",
    )
    result = compose_workflow_summary(
        CompositionInput(project_name="backend", artifacts=(handoff,))
    )
    assert result.primary_lines[0].startswith("Where you left off:")
    assert "deployment" in result.primary_lines[0].lower()
    assert "Suggested next step: polish admin UI" in "\n".join(result.primary_lines)
    assert "Deployment checklist" not in "\n".join(result.primary_lines[:2])


def test_markers_only_in_technical_notes() -> None:
    markers = ("Open markers in a.py — TODO: fix login",)
    result = compose_workflow_summary(
        CompositionInput(
            project_name="app",
            task_markers=markers,
            has_scan=True,
            open_task_count=1,
        )
    )
    primary = "\n".join(result.primary_lines)
    assert "Open markers in" not in primary or "Where you left off" in primary
    assert markers[0] in result.technical_notes


def test_untracked_only_git_state_shows_clean_not_uncommitted_work() -> None:
    """Regression: an untracked-only working tree must report as clean git
    state upstream (status_parser fix) — this only re-confirms that once
    git_state is "clean" with no modified_files, the summary text says so
    honestly instead of "Uncommitted work on ...", which previously fired
    for untracked-only repos via the upstream dirty-flag bug."""
    result = compose_workflow_summary(
        CompositionInput(
            project_name="demo",
            git_label="Git: clean",
            git_state="clean",
            git_branch="main",
            git_is_repo=True,
            modified_files=(),
            has_scan=True,
        )
    )
    text = "\n".join(result.primary_lines + result.supporting_notes + result.technical_notes)
    assert "Uncommitted work" not in text
    assert "Working tree clean on main" in text


def test_genuinely_dirty_git_state_still_shows_uncommitted_work() -> None:
    result = compose_workflow_summary(
        CompositionInput(
            project_name="demo",
            git_label="Git: uncommitted changes",
            git_state="dirty",
            git_branch="main",
            git_is_repo=True,
            modified_files=("src/app.py",),
            has_scan=True,
        )
    )
    text = "\n".join(result.primary_lines + result.supporting_notes + result.technical_notes)
    assert "Uncommitted work on main" in text
