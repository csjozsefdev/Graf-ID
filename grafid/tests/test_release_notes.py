"""Release notes come straight from CHANGELOG.md; the release workflow depends on this."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import grafid

REPO_ROOT = Path(__file__).resolve().parents[2]


def _module():
    spec = importlib.util.spec_from_file_location("release_notes", REPO_ROOT / "packaging" / "release_notes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SAMPLE = "# Changelog\n\n## [1.1.0] - 2026-10-01\n\n### Added\n\n- New\n\n## [1.0.0] - 2026-09-20\n\nFirst.\n\n## [0.9.0]\n\nOld.\n"


def test_extracts_only_the_requested_section() -> None:
    notes = _module().extract(SAMPLE, "1.0.0")
    assert notes == "First.\n"
    assert "New" in _module().extract(SAMPLE, "1.1.0")


def test_unknown_version_is_an_error() -> None:
    with pytest.raises(LookupError):
        _module().extract(SAMPLE, "9.9.9")


def test_the_current_version_has_a_changelog_section() -> None:
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = _module().extract(changelog, grafid.__version__)
    assert notes.strip(), "the released version needs release notes in CHANGELOG.md"
    assert "## [" not in notes
