"""Tests for human dashboard context formatting."""

from __future__ import annotations

from grafid.resume.human_context import build_dashboard_summary
from grafid.resume.workflow_artifacts import WorkflowArtifact


def test_active_session_weak_prompts_exit_note() -> None:
    result = build_dashboard_summary(
        project_name="Graf-Id",
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=True,
        session_started_at="2026-05-27T10:00:00+00:00",
        artifacts=(),
        open_task_count=None,
        has_scan=False,
        git_label=None,
    )
    assert "Work in progress" in result["summary_text"] or "Session still open" in result["summary_text"]
    assert "Open the project and continue" not in result["summary_text"]
    assert "Git:" not in result["summary_text"]


def test_active_session_with_next_step() -> None:
    artifact = WorkflowArtifact(
        filename="README.md",
        relative_path="README.md",
        kind="readme",
        priority_tier="medium",
        title="Graf-Id",
        preview_lines=("Local-first workflow continuity utility.",),
        focus_area=None,
        next_step_line=None,
    )
    result = build_dashboard_summary(
        project_name="Graf-Id",
        exit_note=None,
        blocker=None,
        next_step="review summary cleanup",
        has_active_session=True,
        session_started_at="2026-05-27T10:00:00+00:00",
        artifacts=(artifact,),
        open_task_count=2,
        has_scan=True,
        git_label=None,
        task_markers=("Open markers in src/a.py — TODO: fix panel",),
    )
    text = result["summary_text"]
    assert "review summary cleanup" in text
    assert "Project readme:" not in text
    assert "Project focus:" in text or "Where you left off" in text


def test_handoff_appears_in_summary() -> None:
    artifact = WorkflowArtifact(
        filename="HANDOFF.md",
        relative_path="HANDOFF.md",
        kind="handoff",
        priority_tier="high",
        title="Mesencsi project handoff",
        preview_lines=("Deployment checklist pending.",),
        focus_area="deployment / QA",
        next_step_line="polish admin UI",
    )
    result = build_dashboard_summary(
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=False,
        artifacts=(artifact,),
        open_task_count=None,
        has_scan=False,
        git_label=None,
    )
    text = result["summary_text"]
    assert text.startswith("Where you left off:")
    assert "deployment" in text.lower()
    assert "Suggested next step: polish admin UI" in text
    assert "HANDOFF.md" in result["sources_used"]


def test_task_markers_not_primary_wall_when_alone() -> None:
    result = build_dashboard_summary(
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=False,
        artifacts=(),
        open_task_count=5,
        has_scan=True,
        git_label=None,
        task_markers=("Open markers in src/app.py — TODO: fix login flow",),
    )
    text = result["summary_text"]
    assert "Where you left off" in text or "Suggested next step" in text
    assert "scan markers" in result["sources_used"] or "next step" in result["sources_used"]


def test_no_git_repo_noise() -> None:
    result = build_dashboard_summary(
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=False,
        artifacts=(),
        open_task_count=None,
        has_scan=True,
        git_label="Not a git repository",
        git_state="not_repo",
        git_is_repo=False,
    )
    assert "Not a git" not in result["summary_text"]


def test_no_context_metadata_dump() -> None:
    result = build_dashboard_summary(
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=False,
        artifacts=(),
        open_task_count=None,
        has_scan=False,
        git_label=None,
    )
    assert "Context:" not in result["summary_text"]
    assert result["confidence"] == "weak"
    assert "Not enough context found" in result["summary_text"]


def test_mvp_has_detail_section_for_markers() -> None:
    result = build_dashboard_summary(
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=False,
        artifacts=(),
        open_task_count=1,
        has_scan=True,
        git_label=None,
        task_markers=("Open markers in x.py — TODO: one",),
    )
    titles = [s["title"] for s in result["mvp_sections"]]
    assert any("marker" in t.lower() or "Code" in t for t in titles)


def test_readme_preview_beats_dirty_git_fallback() -> None:
    artifact = WorkflowArtifact(
        filename="README.md",
        relative_path="README.md",
        kind="readme",
        priority_tier="medium",
        title="Graf-Id",
        preview_lines=("Continuing sidebar regression fix after doc update.",),
        focus_area=None,
        next_step_line=None,
    )
    result = build_dashboard_summary(
        project_name="Graf-Id",
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=True,
        session_started_at="2026-05-27T10:00:00+00:00",
        artifacts=(artifact,),
        open_task_count=None,
        has_scan=True,
        git_label="Dirty — branch main",
        git_state="dirty",
        git_branch="main",
        git_is_repo=True,
        modified_files=("app/(tabs)/_layout.tsx", "app/(tabs)/index.tsx"),
    )
    text = result["summary_text"]
    assert "recent edits in" not in text
    assert "sidebar regression fix" in text.lower()
    assert "git changes" not in result["sources_used"]


def test_git_fallback_when_no_documentation_signal() -> None:
    result = build_dashboard_summary(
        project_name="Graf-Id",
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=False,
        artifacts=(),
        open_task_count=None,
        has_scan=True,
        git_label="Dirty — branch main",
        git_state="dirty",
        git_branch="main",
        git_is_repo=True,
        modified_files=("app/(tabs)/_layout.tsx",),
    )
    text = result["summary_text"]
    assert "recent edits in app/(tabs)/_layout.tsx" in text
    assert "Suggested next step: review changes in app/(tabs)/_layout.tsx" in text
    assert "git changes" in result["sources_used"]


def test_handoff_without_labels_uses_preview_content() -> None:
    artifact = WorkflowArtifact(
        filename="HANDOVER.md",
        relative_path="HANDOVER.md",
        kind="handoff",
        priority_tier="high",
        title="Project handover",
        preview_lines=("Resume source priority fix is the current focus.",),
        focus_area=None,
        next_step_line=None,
    )
    result = build_dashboard_summary(
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=True,
        session_started_at="2026-05-27T10:00:00+00:00",
        artifacts=(artifact,),
        open_task_count=None,
        has_scan=True,
        git_label="Dirty — branch main",
        git_state="dirty",
        git_branch="main",
        git_is_repo=True,
        modified_files=("src/App.tsx",),
    )
    text = result["summary_text"]
    assert "source priority fix" in text.lower()
    assert "recent edits in" not in text
    assert "HANDOVER.md" in result["sources_used"]
