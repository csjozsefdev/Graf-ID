"""Handoff chain discovery: README -> HANDOVER -> PROJECT_CONTINUATION link following.

Bounded depth and document count, cycle-safe, ignores external URLs and links that
escape the project root.
"""

from __future__ import annotations

from pathlib import Path

from grafid.resume.human_context import build_dashboard_summary
from grafid.resume.workflow_artifacts import (
    LINK_CHAIN_MAX_DOCUMENTS,
    load_workflow_artifacts,
    primary_handoff,
)


def test_scenario1_readme_links_to_docs_handover(tmp_path: Path) -> None:
    project = tmp_path / "app"
    docs = project / "docs"
    docs.mkdir(parents=True)
    (project / "README.md").write_text(
        "# App\n\nSee [handover details](docs/HANDOVER.md).\n",
        encoding="utf-8",
    )
    (docs / "HANDOVER.md").write_text(
        "# Docs handover\n\nFocus area: API polish\n\nNext step: ship admin fixes\n",
        encoding="utf-8",
    )

    artifacts = load_workflow_artifacts(str(project))
    handoff = primary_handoff(artifacts)
    rel_paths = {a.relative_path.replace("\\", "/") for a in artifacts}

    assert handoff is not None
    assert handoff.focus_area == "API polish"
    assert "docs/HANDOVER.md" in rel_paths


def test_scenario2_handover_links_to_project_continuation(tmp_path: Path) -> None:
    project = tmp_path / "mesencsi"
    project.mkdir()
    (project / "HANDOVER.md").write_text(
        "# Handover\n\nContinuing work? Read [PROJECT_CONTINUATION.md](PROJECT_CONTINUATION.md).\n",
        encoding="utf-8",
    )
    (project / "PROJECT_CONTINUATION.md").write_text(
        "# Mesencsi continuation\n\nFocus area: production QA\n\nNext step: run Barion sandbox E2E\n",
        encoding="utf-8",
    )

    artifacts = load_workflow_artifacts(str(project))
    handoff = primary_handoff(artifacts)

    assert handoff is not None
    assert handoff.filename == "PROJECT_CONTINUATION.md"
    assert handoff.focus_area == "production QA"
    assert handoff.next_step_line == "run Barion sandbox E2E"


def test_scenario3_depth_two_chain_readme_handover_next_steps(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    docs = project / "docs"
    docs.mkdir(parents=True)
    (project / "README.md").write_text(
        "# Repo\n\nStart with [HANDOVER.md](docs/HANDOVER.md).\n",
        encoding="utf-8",
    )
    (docs / "HANDOVER.md").write_text(
        "# Handover\n\nSee [NEXT_STEPS.md](NEXT_STEPS.md) for remaining work.\n",
        encoding="utf-8",
    )
    (docs / "NEXT_STEPS.md").write_text(
        "# Next steps\n\nNext step: finish release checklist\n",
        encoding="utf-8",
    )

    artifacts = load_workflow_artifacts(str(project))
    rel_paths = {a.relative_path.replace("\\", "/") for a in artifacts}

    assert "docs/HANDOVER.md" in rel_paths
    assert "docs/NEXT_STEPS.md" in rel_paths
    next_doc = next(
        a for a in artifacts if a.relative_path.replace("\\", "/") == "docs/NEXT_STEPS.md"
    )
    assert next_doc.next_step_line == "finish release checklist"


def test_scenario4_external_url_ignored(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / "HANDOVER.md").write_text(
        "# Handover\n\nSee [External docs](https://external-site.com/guide.html).\n",
        encoding="utf-8",
    )

    artifacts = load_workflow_artifacts(str(project))

    assert len(artifacts) == 1
    assert artifacts[0].filename == "HANDOVER.md"


def test_scenario5_circular_reference_does_not_loop(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / "README.md").write_text(
        "# Readme\n\nSee [HANDOVER.md](HANDOVER.md).\n",
        encoding="utf-8",
    )
    (project / "HANDOVER.md").write_text(
        "# Handover\n\nBack to [README.md](README.md).\n",
        encoding="utf-8",
    )

    artifacts = load_workflow_artifacts(str(project))

    assert len(artifacts) == 2
    assert {a.filename for a in artifacts} == {"README.md", "HANDOVER.md"}


def test_simple_colon_reference_resolves_relative_path(tmp_path: Path) -> None:
    project = tmp_path / "app"
    handover_dir = project / "docs" / "handover"
    handover_dir.mkdir(parents=True)
    (project / "HANDOVER.md").write_text(
        "# Handover\n\nRemaining work:\ndocs/handover/final_notes.md\n",
        encoding="utf-8",
    )
    (handover_dir / "final_notes.md").write_text(
        "# Final notes\n\nFocus area: deploy sign-off\n",
        encoding="utf-8",
    )

    artifacts = load_workflow_artifacts(str(project))
    rel_paths = {a.relative_path.replace("\\", "/") for a in artifacts}

    assert "docs/handover/final_notes.md" in rel_paths
    linked = next(
        a for a in artifacts if a.relative_path.replace("\\", "/") == "docs/handover/final_notes.md"
    )
    assert linked.focus_area == "deploy sign-off"


def test_project_continuation_direct_discovery(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / "PROJECT_CONTINUATION.md").write_text(
        "# Continuation\n\nFocus area: release prep\n",
        encoding="utf-8",
    )
    (project / "HANDOVER.md").write_text(
        "# Handover\n\nFocus area: reviewer guide\n",
        encoding="utf-8",
    )

    handoff = primary_handoff(load_workflow_artifacts(str(project)))

    assert handoff is not None
    assert handoff.filename == "PROJECT_CONTINUATION.md"
    assert handoff.focus_area == "release prep"


def test_resume_summary_uses_continuation_chain(tmp_path: Path) -> None:
    project = tmp_path / "mesencsi"
    project.mkdir()
    (project / "HANDOVER.md").write_text(
        "# Handover\n\nSee [PROJECT_CONTINUATION.md](PROJECT_CONTINUATION.md).\n",
        encoding="utf-8",
    )
    (project / "PROJECT_CONTINUATION.md").write_text(
        "# Continuation\n\nFocus area: manual QA\n\nNext step: run E2E gate\n",
        encoding="utf-8",
    )

    artifacts = load_workflow_artifacts(str(project))
    result = build_dashboard_summary(
        project_name="Mesencsi",
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=False,
        artifacts=artifacts,
        open_task_count=None,
        has_scan=True,
        git_label="Clean — branch main",
        git_state="clean",
        git_branch="main",
        git_is_repo=True,
    )

    assert "manual qa" in result["summary_text"].lower()
    assert "PROJECT_CONTINUATION.md" in result["sources_used"]


def test_link_chain_respects_max_document_limit(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    links = []
    for index in range(1, LINK_CHAIN_MAX_DOCUMENTS + 5):
        name = f"doc{index:02d}.md"
        (project / name).write_text(
            f"# Doc {index}\n\nFocus area: step {index}\n",
            encoding="utf-8",
        )
        links.append(f"[{name}]({name})")
    (project / "README.md").write_text(
        "# Readme\n\n" + "\n".join(links) + "\n",
        encoding="utf-8",
    )

    artifacts = load_workflow_artifacts(str(project))
    linked = [a for a in artifacts if a.filename != "README.md"]

    assert len(linked) <= LINK_CHAIN_MAX_DOCUMENTS


def test_symlink_outside_project_root_is_ignored(tmp_path: Path) -> None:
    project = tmp_path / "app"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (outside / "SECRET.md").write_text(
        "# Secret\n\nFocus area: outside project\n",
        encoding="utf-8",
    )
    (project / "HANDOVER.md").write_text(
        "# Handover\n\nSee [outside](../outside/SECRET.md).\n",
        encoding="utf-8",
    )

    artifacts = load_workflow_artifacts(str(project))

    assert all("SECRET.md" not in a.filename for a in artifacts)
