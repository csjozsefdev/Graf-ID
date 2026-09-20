"""Milestone 5B regression tests: real audit finding H3.

The original audit finding: `MARKDOWN_LINK = re.compile(r"\\[([^\\]]+)\\]\\(([^)]+)\\)")`
in workflow_artifacts.py is O(n^2) on adversarial input (many `[` characters
with no closing `]`), because a negated-character-class `+` still backtracks
character-by-character before failing, and `.search()`/`.finditer()`/`.sub()`
retry that failing match at every candidate `[` position in the line.

Milestone 5 (commit 095c6516) fixed a *different*, separately-compiled
regex (POINTER_LINE) with the same pathological shape, but did not touch
MARKDOWN_LINK itself — verified below (test_markdown_link_still_pathological_
before_fix documents the measured, reproduced timing on the original pattern)
before it was fixed by bounding the two capture groups.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from grafid.resume.workflow_artifacts import (
    LINK_CHAIN_MAX_DOCUMENTS,
    MARKDOWN_LINK,
    load_workflow_artifacts,
)

# The exact original pattern from the audit, recompiled here (not imported)
# so this test keeps working as its own independent proof even if the fixed
# MARKDOWN_LINK's definition changes shape again later.
_ORIGINAL_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def test_markdown_link_still_pathological_before_fix() -> None:
    """
    Documents the reproduced adversarial case against the ORIGINAL pattern.

    Not a regression test for the fix (it deliberately uses the unfixed
    pattern) — it is the recorded proof that the M5 POINTER_LINE-only fix
    did not already cover this finding, so fixing MARKDOWN_LINK itself was
    necessary rather than redundant.
    """
    pathological = "[" * 12_000
    started = time.perf_counter()
    _ORIGINAL_PATTERN.search(pathological)
    elapsed = time.perf_counter() - started
    # Measured ~1.0s on this machine; a generous floor that still proves
    # the original pattern is not fast/linear at a realistic file-size cap.
    assert elapsed > 0.3


# ---------------------------------------------------------------------------
# Fixed MARKDOWN_LINK: performance on adversarial input
# ---------------------------------------------------------------------------


def test_markdown_link_handles_12000_unclosed_brackets_quickly() -> None:
    pathological = "[" * 12_000
    started = time.perf_counter()
    MARKDOWN_LINK.search(pathological)
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0


def test_markdown_link_handles_100000_unclosed_brackets_quickly() -> None:
    pathological = "[" * 100_000
    started = time.perf_counter()
    MARKDOWN_LINK.search(pathological)
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# Fixed MARKDOWN_LINK: normal-case correctness is unchanged
# ---------------------------------------------------------------------------


def test_markdown_link_matches_normal_link() -> None:
    match = MARKDOWN_LINK.search("See [handoff notes](HANDOFF.md) for details")
    assert match is not None
    assert match.group(1) == "handoff notes"
    assert match.group(2) == "HANDOFF.md"


def test_markdown_link_matches_multiple_links_in_one_document() -> None:
    text = (
        "See [readme](README.md), [handover](HANDOVER.md), "
        "and [changelog](CHANGELOG.md) for context."
    )
    matches = MARKDOWN_LINK.findall(text)
    assert matches == [
        ("readme", "README.md"),
        ("handover", "HANDOVER.md"),
        ("changelog", "CHANGELOG.md"),
    ]


@pytest.mark.parametrize(
    "malformed",
    [
        "[]()",
        "[](url.md)",
        "[text]()",
        "[a[b]c](d.md)",
        "[[nested]](url.md)",
        "[text](url(with)parens)",
        "not a link [ at all",
        "](broken",
    ],
)
def test_markdown_link_does_not_crash_or_hang_on_malformed_input(malformed: str) -> None:
    """Malformed/nested-like markdown must be handled deterministically, never raise/hang."""
    started = time.perf_counter()
    MARKDOWN_LINK.findall(malformed)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5


# ---------------------------------------------------------------------------
# End-to-end: 10-document handoff chain still resolves correctly
# ---------------------------------------------------------------------------


def test_ten_document_handoff_chain_still_resolves(tmp_path: Path) -> None:
    project = tmp_path / "chain-project"
    docs = project / "docs"
    docs.mkdir(parents=True)

    links = "\n".join(f"- See [doc {i}](docs/doc_{i}.md)" for i in range(LINK_CHAIN_MAX_DOCUMENTS))
    (project / "HANDOFF.md").write_text(
        f"# Handoff\n\nFocus area: chain root\n\n{links}\n",
        encoding="utf-8",
    )
    for i in range(LINK_CHAIN_MAX_DOCUMENTS):
        (docs / f"doc_{i}.md").write_text(
            f"# Doc {i}\n\nFocus area: chained doc {i}\n",
            encoding="utf-8",
        )

    artifacts = load_workflow_artifacts(str(project))
    rel_paths = {a.relative_path.replace("\\", "/") for a in artifacts}

    assert "HANDOFF.md" in rel_paths
    for i in range(LINK_CHAIN_MAX_DOCUMENTS):
        assert f"docs/doc_{i}.md" in rel_paths
