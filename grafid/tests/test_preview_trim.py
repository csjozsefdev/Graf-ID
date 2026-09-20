"""Tests for preview text truncation."""

from __future__ import annotations

from grafid.resume.quality import MAX_PREVIEW_CHARS, trim_preview_text


def test_trim_preview_text_keeps_short_text() -> None:
    text = "Short summary."
    assert trim_preview_text(text) == text


def test_trim_preview_text_uses_word_boundary() -> None:
    text = (
        "We were closing out the v0.1.0 release. The packaged app could start Python, "
        "but Refresh Context crashed on projects with a CHANGELOG.md. That is fixed in "
        "the repo; the installer on disk is still the old build. Rebuild from the repo, "
        "reinstall, and smoke-test Add Project and Refresh Context without a dev .venv. "
        "If the build fails with access denied, quit Graf-Id first."
    )
    assert len(" ".join(text.split())) > MAX_PREVIEW_CHARS
    trimmed = trim_preview_text(text, MAX_PREVIEW_CHARS)
    assert len(trimmed) <= MAX_PREVIEW_CHARS
    assert trimmed.endswith("…")
    assert not trimmed.endswith("the r…")
    assert "repo" in trimmed or "CHANGELOG.md." in trimmed


def test_trim_preview_text_does_not_cut_mid_word() -> None:
    text = "working on export validation and release verification for the next build"
    trimmed = trim_preview_text(text, 40)
    assert trimmed == "working on export validation and…"
