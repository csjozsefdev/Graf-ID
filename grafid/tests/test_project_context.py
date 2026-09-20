"""ProjectContext — the backend/domain source of truth for Snapshot and exports."""

from __future__ import annotations

import pytest

from grafid.resume.human_context import build_context_bundle
from grafid.resume.project_context import (
    ProjectContext,
    classify_commit_subject,
    clip,
    export_safe_relative_path,
    first_sentence,
)
from grafid.resume.workflow_artifacts import WorkflowArtifact
from grafid.resume.workflow_state import looks_like_shell_command


def artifact(**over) -> WorkflowArtifact:
    base = dict(
        filename="HANDOVER.md",
        relative_path="docs/HANDOVER.md",
        kind="handoff",
        priority_tier="high",
        title="Handover",
        preview_lines=(),
        focus_area=None,
        next_step_line=None,
    )
    base.update(over)
    return WorkflowArtifact(**base)


def context(**over) -> ProjectContext:
    kwargs = dict(
        project_name="Demo",
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=False,
        artifacts=(),
        open_task_count=None,
        has_scan=True,
        git_label="Clean",
        git_state="clean",
        git_branch="main",
        git_is_repo=True,
    )
    kwargs.update(over)
    _, ctx = build_context_bundle(**kwargs)
    return ctx


def commit(subject: str, n: int = 1) -> dict[str, str]:
    return {
        "commit_hash": f"{n:040x}",
        "subject": subject,
        "author": "x",
        "committed_at": "2026-09-01T10:00:00+00:00",
    }


# ------------------------------------------------------------------- text helpers


def test_first_sentence_never_splits_inside_a_version_number() -> None:
    text = "v1.0.0 is the first public release: security audit, Docker environment."
    assert first_sentence(text) == text
    assert first_sentence("Fixed the launcher. Then wrote docs.") == "Fixed the launcher."


def test_first_sentence_handles_unicode_sentence_boundaries() -> None:
    assert first_sentence("Konfigurálható monitor. Éles teszt következik.") == (
        "Konfigurálható monitor."
    )
    assert first_sentence("- bullet line only") == "bullet line only"
    assert first_sentence("\n\n   ") is None and first_sentence(None) is None


def test_clip_cuts_on_a_word_boundary_with_an_ellipsis() -> None:
    out = clip("alpha beta gamma delta epsilon", 18)
    assert out.endswith("…") and len(out) <= 18 and " " not in out[-2:]
    assert clip("short text", 50) == "short text"


@pytest.mark.parametrize(
    ("subject", "kind", "text"),
    [
        ("fix: three regressions found in use", "fix", "Three regressions found in use"),
        ("fix(test): two CI-only failures", "fix", "Two CI-only failures"),
        ("feat: add integration flow tracing", "improvement", "Add integration flow tracing"),
        ("feat(ui)!: redesign the header", "improvement", "Redesign the header"),
        ("Fix Windows release console window on startup.", "fix", "Fix Windows release console window on startup."),
        ("Improve project wake transition loop behavior", "improvement", "Improve project wake transition loop behavior"),
        ("chore: bump to v1.0.0 for the first public release", None, None),
        ("docs: explain how to fix the installer", None, None),
        ("test: add regression for fix", None, None),
        ("Merge branch 'main' into release", None, None),
        ("Quick refhresh", None, None),
        ("wip", None, None),
        ("", None, None),
    ],
)
def test_commit_subjects_are_classified_conservatively(subject, kind, text) -> None:
    assert classify_commit_subject(subject) == (kind, text)


@pytest.mark.parametrize(
    ("path", "safe"),
    [
        ("src/app.py", "src/app.py"),
        ("src\\app.py", "src/app.py"),
        ("/etc/passwd", None),
        ("C:\\Users\\me\\x.txt", None),
        ("../outside.txt", None),
        ("a/../../b", None),
        (".env", None),
        ("config/.env.production", None),
        ("keys/server.pem", None),
        ("id_rsa", None),
        (".venv-314-dev/Lib/x.py", None),
        ("node_modules/pkg/i.js", None),
        ("README.md", "README.md"),
    ],
)
def test_only_safe_relative_paths_are_exportable(path: str, safe: str | None) -> None:
    assert export_safe_relative_path(path) == safe


def test_shell_command_lines_are_recognised() -> None:
    assert looks_like_shell_command("cd backend")
    assert not looks_like_shell_command("Python is required.")


# --------------------------------------------------------------- domain building


def test_exit_note_drives_focus_last_completed_and_next_step() -> None:
    ctx = context(
        exit_note="Finished the checkout flow. Started on the receipt page.",
        next_step="Wire the receipt page to the API",
        has_active_session=False,
    )
    assert ctx.continuity.current_focus == "Finished the checkout flow."
    assert ctx.continuity.last_completed == "Finished the checkout flow."
    assert ctx.continuity.suggested_next_step == "Wire the receipt page to the API"


def test_project_with_blocker_reports_it_as_blocker_and_open_issue() -> None:
    ctx = context(exit_note="Payments half done.", blocker="Waiting for production API key")
    assert ctx.continuity.blockers == ("Waiting for production API key",)
    assert "Waiting for production API key" in ctx.continuity.open_issues


def test_project_without_blocker_has_no_blocker_entries() -> None:
    ctx = context(exit_note="All good.", next_step="Ship it")
    assert ctx.continuity.blockers == ()
    assert ctx.continuity.open_issues == ()


def test_recent_fixes_and_improvements_come_only_from_trusted_commit_subjects() -> None:
    ctx = context(
        git_commits=(
            commit("fix: pin release runtime to Python 3.12.10", 1),
            commit("feat: add integration flow tracing", 2),
            commit("chore: bump version", 3),
            commit("docs: update readme", 4),
            commit("fix: pin release runtime to Python 3.12.10", 5),  # duplicate
            commit("Quick refhresh", 6),
        )
    )
    assert ctx.continuity.recent_fixes == ("Pin release runtime to Python 3.12.10",)
    assert ctx.continuity.recent_improvements == ("Add integration flow tracing",)
    assert [c.subject for c in ctx.git.recent_commits][:2] == [
        "fix: pin release runtime to Python 3.12.10",
        "feat: add integration flow tracing",
    ]
    assert all(len(c.short_hash or "") == 8 for c in ctx.git.recent_commits)


def test_scanner_markers_never_become_focus_issues_or_next_steps() -> None:
    markers = (
        'Open markers in apps/x.tsx — NEXT: { label: "Next", text: "text-primary" },',
        "Open markers in ci.yml — BUG: the audit found",
    )
    ctx = context(task_markers=markers, open_task_count=2)
    payload = ctx.snapshot_payload()
    flat = repr(payload) + repr(ctx.continuity)
    assert "label" not in flat and "audit found" not in flat
    assert ctx.continuity.suggested_next_step is None
    assert ctx.continuity.open_issues == ()


def test_shell_command_preview_lines_are_not_used_as_focus_or_anchor() -> None:
    notes_doc = artifact(
        filename="desktop-frontend.md",
        relative_path="docs/desktop-frontend.md",
        kind="notes",
        priority_tier="medium",
        title="Desktop frontend",
        preview_lines=("cd backend",),
    )
    composed, ctx = build_context_bundle(
        project_name="Demo", exit_note=None, blocker=None, next_step=None,
        has_active_session=False, artifacts=(notes_doc,), open_task_count=None,
        has_scan=True, git_label="Clean",
    )
    assert ctx.continuity.current_focus is None
    assert "cd backend" not in " ".join(composed.primary_lines)


def test_generic_fallback_next_steps_are_not_exported_as_reliable() -> None:
    composed, ctx = build_context_bundle(
        project_name="Demo", exit_note=None, blocker=None, next_step=None,
        has_active_session=False, artifacts=(), open_task_count=None, has_scan=True,
        git_label="Dirty", git_state="dirty", git_is_repo=True, git_branch="main",
        modified_files=("src/a.py",),
    )
    assert composed.suggested_next_step == "review changes in src/a.py"
    assert composed.suggested_next_step_source == "fallback"
    assert ctx.continuity.suggested_next_step is None


def test_handoff_document_supplies_focus_next_step_and_open_issues() -> None:
    doc = artifact(
        focus_area="Payment provider integration",
        next_step_line="Deploy once credentials arrive",
        unfinished_items=("Barion production key", "Refund flow"),
        blocker_items=("Merchant approval pending",),
    )
    ctx = context(artifacts=(doc,))
    assert ctx.continuity.current_focus == "Payment provider integration"
    assert ctx.continuity.suggested_next_step == "Deploy once credentials arrive"
    assert ctx.continuity.blockers == ("Merchant approval pending",)
    assert ctx.continuity.open_issues == (
        "Merchant approval pending", "Barion production key", "Refund flow",
    )
    assert [f.path for f in ctx.context.workflow_files] == ["docs/HANDOVER.md"]


@pytest.mark.parametrize(("state", "expected"), [("clean", "clean"), ("dirty", "dirty"), ("not_repo", "unknown"), (None, "unknown")])
def test_git_state_is_normalised(state, expected) -> None:
    ctx = context(git_state=state)
    assert ctx.git.state == expected


def test_untracked_only_repository_is_clean_and_lists_no_changed_files() -> None:
    from grafid.git.status_parser import parse_porcelain_status

    staged, modified, dirty = parse_porcelain_status("?? scratch/\n?? notes.txt\n")
    ctx = context(git_state="dirty" if dirty else "clean", git_modified_files=tuple(modified),
                  git_staged_files=tuple(staged))
    assert ctx.git.state == "clean" and ctx.git.modified_files == ()


def test_changed_files_are_relative_safe_and_capped() -> None:
    many = tuple(f"src/file{i}.py" for i in range(40))
    ctx = context(
        git_state="dirty",
        git_modified_files=(".env", "C:\\abs\\x.py", ".venv-314-dev/a.py", *many),
    )
    assert ctx.git.modified_files == many[:20]


def test_unicode_and_very_large_notes_are_preserved_and_bounded() -> None:
    long_notes = "Árvíztűrő tükörfúrógép — jegyzet. " * 400
    ctx = context(project_notes=long_notes, exit_note="Elkészült a főoldal. Következik a kosár.")
    assert ctx.continuity.current_focus == "Elkészült a főoldal."
    assert ctx.context.notes is not None
    assert ctx.context.notes.startswith("Árvíztűrő") and len(ctx.context.notes) <= 1200


def test_context_is_deterministic() -> None:
    kwargs = dict(
        exit_note="Did a thing. Next.", blocker="Blocked", next_step="Do more",
        git_commits=(commit("fix: a thing here", 1), commit("feat: another thing", 2)),
    )
    assert context(**kwargs) == context(**kwargs)


def test_snapshot_payload_is_none_when_nothing_reliable_is_known() -> None:
    ctx = context(has_scan=False, git_state=None, git_is_repo=False)
    assert ctx.snapshot_payload() is None


def test_snapshot_payload_carries_the_five_ui_sections() -> None:
    ctx = context(
        exit_note="Did the thing.", blocker="Stuck", next_step="Next thing",
        git_commits=(commit("fix: one bug fixed", 1), commit("feat: one feature added", 2)),
    )
    payload = ctx.snapshot_payload()
    assert payload == {
        "current_focus": ["Did the thing."],
        "open_issues": ["Stuck"],
        "recent_fixes": ["One bug fixed"],
        "recent_improvements": ["One feature added"],
        "suggested_next_step": "Next thing",
    }
