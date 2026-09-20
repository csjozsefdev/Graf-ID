"""Tests for workflow artifact detection."""

from __future__ import annotations

from pathlib import Path

from grafid.resume.workflow_artifacts import load_workflow_artifacts, primary_handoff


def test_detects_handoff_file(tmp_path: Path) -> None:
    project = tmp_path / "backend"
    project.mkdir()
    (project / "HANDOFF.md").write_text(
        "# Mesencsi project handoff\n\nFocus area: deployment / QA\n\nNext step: polish admin UI\n",
        encoding="utf-8",
    )
    artifacts = load_workflow_artifacts(str(project))
    handoff = primary_handoff(artifacts)
    assert handoff is not None
    assert handoff.title == "Mesencsi project handoff"
    assert handoff.focus_area == "deployment / QA"
    assert handoff.next_step_line == "polish admin UI"


def test_detects_readme_when_no_handoff(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / "README.md").write_text("# App readme\n\nSetup instructions here.\n", encoding="utf-8")
    artifacts = load_workflow_artifacts(str(project))
    assert any(a.kind == "readme" for a in artifacts)
    assert primary_handoff(artifacts) is None


def test_searches_parent_directory(tmp_path: Path) -> None:
    root = tmp_path / "mesencsi"
    backend = root / "backend"
    backend.mkdir(parents=True)
    (root / "HANDOFF.md").write_text("# Parent handoff\n", encoding="utf-8")
    artifacts = load_workflow_artifacts(str(backend))
    assert primary_handoff(artifacts) is not None


def test_allowlist_ignores_unlisted_md_files(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / "RANDOM_NOTES.md").write_text("# Should not load\n", encoding="utf-8")
    (project / "docs").mkdir()
    (project / "docs" / "ARCHITECTURE.md").write_text("# Also ignored\n", encoding="utf-8")
    artifacts = load_workflow_artifacts(str(project))
    assert artifacts == ()


def test_detects_exit_note_and_changelog(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / "EXIT_NOTE.md").write_text("# Exit\n\nShipped v1.\n", encoding="utf-8")
    (project / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0\n\nInitial release.\n", encoding="utf-8")
    artifacts = load_workflow_artifacts(str(project))
    kinds = {a.kind for a in artifacts}
    assert "exit_note" in kinds
    assert "changelog" in kinds
    assert all(a.priority_tier in {"high", "medium"} for a in artifacts)


def test_high_tier_sorted_before_medium(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / "README.md").write_text("# Readme\n\nSetup.\n", encoding="utf-8")
    (project / "NEXT.md").write_text("# Next\n\nDo the thing.\n", encoding="utf-8")
    artifacts = load_workflow_artifacts(str(project))
    assert artifacts[0].kind == "next"
    assert artifacts[0].priority_tier == "high"
    assert any(a.kind == "readme" for a in artifacts)


# --- INLINE_NEXT_RE / "**Next:**" truncation regression tests ---
#
# Root cause: the regex used to stop at any case-insensitive "see", not just
# the intended capitalized "See <doc>" trailing-pointer convention — so a
# **Next:** line containing the ordinary word "see" anywhere before its first
# literal "." got silently cut off mid-sentence. Confirmed live against this
# repo's own docs/HANDOVER.md. Fixed by requiring "See" to be capitalized and
# the terminating period to be followed by whitespace/end-of-string (so it
# doesn't fire inside "CHANGELOG.md" or "1.0.0").


def _handoff_with_next_line(tmp_path: Path, next_line: str) -> str | None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "HANDOFF.md").write_text(
        f"# Handoff\n\n{next_line}\n",
        encoding="utf-8",
    )
    artifacts = load_workflow_artifacts(str(project))
    handoff = primary_handoff(artifacts)
    assert handoff is not None
    return handoff.next_step_line


def test_lowercase_natural_see_is_not_truncated(tmp_path: Path) -> None:
    # _plain_text() strips markdown-ish characters like "#" — unrelated to
    # this fix, so the expectation accounts for it rather than fighting it.
    result = _handoff_with_next_line(
        tmp_path, "**Next:** fix the bug, see issue #42 for details."
    )
    assert result == "fix the bug, see issue 42 for details"


def test_uppercase_sentence_start_see_still_strips_doc_pointer(tmp_path: Path) -> None:
    result = _handoff_with_next_line(tmp_path, "**Next:** ship it. See ROADMAP.md.")
    assert result == "ship it"


def test_markdown_link_does_not_break_on_internal_period(tmp_path: Path) -> None:
    # _plain_text() also reduces a markdown link to its label — unrelated
    # to this fix — so the expectation reflects that, not the raw markdown.
    result = _handoff_with_next_line(
        tmp_path,
        "**Next:** see [CHANGELOG.md](../CHANGELOG.md) for the full list.",
    )
    assert result == "see CHANGELOG.md for the full list"


def test_plain_filename_does_not_break_on_internal_period(tmp_path: Path) -> None:
    result = _handoff_with_next_line(tmp_path, "**Next:** check config.yaml for settings.")
    assert result == "check config.yaml for settings"


def test_multiple_sentences_extracts_only_the_first(tmp_path: Path) -> None:
    result = _handoff_with_next_line(
        tmp_path,
        "**Next:** do the first thing. Then do the second thing. Finally the third.",
    )
    assert result == "do the first thing"


def test_no_pointer_extracts_the_whole_sentence(tmp_path: Path) -> None:
    result = _handoff_with_next_line(tmp_path, "**Next:** nothing else needed here.")
    assert result == "nothing else needed here"


def test_multiple_see_words_none_of_them_truncate(tmp_path: Path) -> None:
    result = _handoff_with_next_line(
        tmp_path,
        "**Next:** see the docs, then see the examples, then ship it.",
    )
    assert result == "see the docs, then see the examples, then ship it"


def test_current_handover_example_sentence_not_truncated(tmp_path: Path) -> None:
    """The exact sentence from this repo's own docs/HANDOVER.md that first
    surfaced the bug in real, live use."""
    result = _handoff_with_next_line(
        tmp_path,
        "**Next:** post-launch — see [CHANGELOG.md](../CHANGELOG.md) for what "
        "shipped in 1.0.0 vs what stayed unreleased. Sprint detail: "
        "[PROJECT_CONTINUATION.md](PROJECT_CONTINUATION.md).",
    )
    assert result is not None
    assert result.startswith("post-launch")
    assert "see CHANGELOG.md" in result
    assert "shipped in 1.0.0" in result
    assert not result.endswith("—")


def test_handover_example_under_where_we_left_off_heading_not_truncated(
    tmp_path: Path,
) -> None:
    """Same sentence, but under a real '## Where we left off' heading — the
    actual structure of this repo's own docs/HANDOVER.md. This routes
    through a different code path (_extract_where_left_off_section ->
    _extract_inline_next) that had its own, second contributing bug:
    _sanitize_workflow_text's doc-index-line handling misclassified the
    already-correctly-extracted next-step text as "just a doc pointer"
    (because it mentions a .md file) and discarded everything before the
    dash — silently re-truncating text INLINE_NEXT_RE itself extracted
    correctly. Fixed by not applying that doc-index stripping to inline-
    next text (strip_doc_index_prefix=False)."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "HANDOVER.md").write_text(
        "# Graf-Id handover\n\n"
        "## Where we left off (September 2026)\n\n"
        "**v1.0.0** is the first public release: security/reliability audit "
        "(Milestones 1-9), a Dockerized reproducible test environment, and "
        "this version bump.\n\n"
        "**Next:** post-launch — see [CHANGELOG.md](../CHANGELOG.md) for what "
        "shipped in 1.0.0 vs what stayed unreleased. Sprint detail: "
        "[PROJECT_CONTINUATION.md](PROJECT_CONTINUATION.md).\n",
        encoding="utf-8",
    )
    artifacts = load_workflow_artifacts(str(project))
    handoff = primary_handoff(artifacts)
    assert handoff is not None
    result = handoff.next_step_line
    assert result is not None
    assert result.startswith("post-launch")
    assert "see CHANGELOG.md" in result
    assert "shipped in 1.0.0" in result
    assert not result.endswith("—")
