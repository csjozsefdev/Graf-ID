"""Milestone 5 regression tests: scanner/parsing/resource hardening.

Covers audit findings H2 (bounded file read for workflow artifacts), H3
(ReDoS-unsafe pointer-line regex), M7 (scanner file-count/time budget), L1
(unbounded scan warning list), and L2 (unbounded git status/log parsing).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from grafid.git.runner import git_available
from grafid.git.service import GitReadService
from grafid.resume.workflow_artifacts import (
    MAX_READ_BYTES,
    POINTER_LINE,
    load_workflow_artifacts,
)
from grafid.scanner.config import ScanConfig
from grafid.scanner.models import ScanResult
from grafid.scanner.service import ProjectScannerService

GIT_SKIP_REASON = (
    "git executable not found on PATH — environment-only skip; "
    "Graf-Id does not require git for non-git projects and this is not an app failure"
)


@pytest.fixture
def git_required() -> None:
    if not git_available():
        pytest.skip(GIT_SKIP_REASON)


# ---------------------------------------------------------------------------
# H2 — workflow artifact reads are bounded, never a whole-file read_text()
# ---------------------------------------------------------------------------


def test_workflow_artifact_never_calls_whole_file_read_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    oversized_tail = "Focus: should never be seen\n" * 100
    content = "# Title\nFocus: only-in-first-chunk\n" + ("A" * (MAX_READ_BYTES + 5000)) + oversized_tail
    (project / "NOTES.md").write_text(content, encoding="utf-8")

    def boom(self: Path, *args: object, **kwargs: object) -> str:
        raise AssertionError(
            "Path.read_text() must not be called on project files — "
            "workflow artifact reads must go through the bounded byte read"
        )

    monkeypatch.setattr(Path, "read_text", boom)

    artifacts = load_workflow_artifacts(str(project))

    assert len(artifacts) == 1
    assert artifacts[0].focus_area == "only-in-first-chunk"


def test_workflow_artifact_read_is_capped_at_max_read_bytes(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    content = "# Title\n" + ("A" * (MAX_READ_BYTES + 5000)) + "\nFocus: past the cutoff\n"
    (project / "NOTES.md").write_text(content, encoding="utf-8")

    artifacts = load_workflow_artifacts(str(project))

    assert len(artifacts) == 1
    assert artifacts[0].focus_area is None


# ---------------------------------------------------------------------------
# H3 — POINTER_LINE regex has no catastrophic backtracking
# ---------------------------------------------------------------------------


def test_pointer_line_regex_handles_pathological_input_quickly() -> None:
    # Unmatched '[' runs force worst-case backtracking on the unbounded
    # `.+` variant of this pattern (quadratic: ~10s at 100k chars measured
    # against the unfixed regex). A generous but firm bound catches a
    # regression while staying well clear of normal-machine noise for the
    # fixed (linear) version, which handles this size in ~0.02s.
    pathological = "see " + "[" * 100_000

    started = time.perf_counter()
    POINTER_LINE.match(pathological)
    elapsed = time.perf_counter() - started

    assert elapsed < 3.0


def test_pointer_line_regex_still_matches_real_pointer_line() -> None:
    assert POINTER_LINE.match("See [handoff notes](HANDOFF.md) for details")
    assert POINTER_LINE.match("refer to [docs](docs/GUIDE.md)")
    assert not POINTER_LINE.match("This is just regular text with [a link](x.md) mid-sentence")


# ---------------------------------------------------------------------------
# M7 — scanner file-count and time-budget limits
# ---------------------------------------------------------------------------


def test_scanner_stops_after_max_files(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    for i in range(30):
        (project / f"file_{i}.txt").write_text("x", encoding="utf-8")

    config = ScanConfig(max_files=5, max_scan_seconds=60.0)
    scanner = ProjectScannerService(config)
    result = scanner.scan_project(project)

    assert result.scanned_count + result.skipped_count < 30
    assert any("resource limit" in w.lower() for w in result.warnings)


def test_scanner_stops_after_time_budget(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    for i in range(20):
        (project / f"file_{i}.txt").write_text("x", encoding="utf-8")

    config = ScanConfig(max_files=1_000_000, max_scan_seconds=0.0)
    scanner = ProjectScannerService(config)
    result = scanner.scan_project(project)

    assert result.scanned_count + result.skipped_count < 20
    assert any("resource limit" in w.lower() for w in result.warnings)


def test_scanner_normal_project_is_unaffected_by_limits(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "README.md").write_text("# Hello\n", encoding="utf-8")
    (project / "main.py").write_text("print('hi')\n", encoding="utf-8")

    result = ProjectScannerService().scan_project(project)

    assert result.scanned_count == 2
    assert not any("resource limit" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# L1 — scan warning list growth is capped
# ---------------------------------------------------------------------------


def test_scan_warnings_are_capped_with_suppression_notice() -> None:
    config = ScanConfig(max_warnings=3)
    scanner = ProjectScannerService(config)
    result = ScanResult(project_name="p", project_path="/nonexistent")

    for i in range(10):
        scanner._warn(result, f"warning {i}")

    assert len(result.warnings) == 4
    assert result.warnings[:3] == ["warning 0", "warning 1", "warning 2"]
    assert "suppressed" in result.warnings[3].lower()

    # Further calls must not keep growing the list.
    scanner._warn(result, "warning 10")
    assert len(result.warnings) == 4


# ---------------------------------------------------------------------------
# L2 — git status/log parsing is bounded
# ---------------------------------------------------------------------------


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True
    )


def test_git_status_list_is_truncated_for_huge_change_set(
    tmp_path: Path, git_required: None
) -> None:
    repo = tmp_path / "huge-repo"
    _init_repo(repo)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    for i in range(600):
        (repo / f"untracked_{i}.txt").write_text("x", encoding="utf-8")
    # Untracked files alone no longer count as "dirty" (fix: untracked !=
    # uncommitted changes to tracked content) — stage them so this exercises
    # the truncation mechanism the test is actually about, on a genuinely
    # large *tracked* change set.
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)

    state = GitReadService().collect(repo)

    assert state.is_dirty is True
    assert len(state.staged_files) <= 500
    assert any("truncated" in w.lower() for w in state.warnings)


def test_git_commit_subject_is_length_capped(tmp_path: Path, git_required: None) -> None:
    repo = tmp_path / "long-subject-repo"
    _init_repo(repo)
    (repo / "a.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)

    long_subject = "x" * 5000
    subprocess.run(
        ["git", "commit", "-m", long_subject], cwd=repo, check=True, capture_output=True
    )

    state = GitReadService().collect(repo)

    assert state.latest_commits
    assert len(state.latest_commits[0].subject) <= 300
