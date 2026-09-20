"""Tests for read-only Git integration (Milestone 3)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from grafid.git.detection import find_repo_root
from grafid.git.runner import git_available
from grafid.git.service import GitReadService
from grafid.git.status_parser import parse_porcelain_status

GIT_SKIP_REASON = (
    "git executable not found on PATH — environment-only skip; "
    "Graf-Id does not require git for non-git projects and this is not an app failure"
)


@pytest.fixture
def git_required() -> None:
    if not git_available():
        pytest.skip(GIT_SKIP_REASON)


def test_git_skip_reason_documents_environment_only() -> None:
    """Skip message must explain missing git is environmental, not a product defect."""
    assert "environment" in GIT_SKIP_REASON.lower()
    assert "PATH" in GIT_SKIP_REASON
    assert "not an app failure" in GIT_SKIP_REASON


def test_find_repo_root_detects_git_dir(tmp_path: Path, git_required: None) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    assert find_repo_root(repo) == repo.resolve()


def test_non_git_project_returns_safe_state(tmp_path: Path, git_required: None) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "readme.txt").write_text("hello", encoding="utf-8")

    state = GitReadService().collect(plain)

    assert state.is_git_repo is False
    assert state.current_branch is None
    assert state.modified_files == ()
    assert state.staged_files == ()


def test_parse_porcelain_modified_and_staged() -> None:
    output = "M  file1.txt\n M file2.py\nMM both.txt\n"
    staged, modified, dirty = parse_porcelain_status(output)

    assert "file1.txt" in staged
    assert "file2.py" in modified
    assert "both.txt" in staged
    assert "both.txt" in modified
    assert dirty is True


def test_dirty_state_detection(git_required: None, tmp_path: Path) -> None:
    repo = tmp_path / "dirty-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    sample = repo / "sample.txt"
    sample.write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    sample.write_text("v2\n", encoding="utf-8")
    state = GitReadService().collect(repo)

    assert state.is_git_repo is True
    assert state.is_dirty is True
    assert "sample.txt" in state.modified_files


def test_untracked_only_repo_is_not_dirty(git_required: None, tmp_path: Path) -> None:
    """End-to-end (real git status, not just the parser): a repo with a
    committed clean tree plus one untracked file/dir and zero changes to
    tracked content must report clean, not dirty."""
    repo = tmp_path / "untracked-only-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "sample.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    scratch_dir = repo / "scripts"
    scratch_dir.mkdir()
    (scratch_dir / "helper.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    state = GitReadService().collect(repo)

    assert state.is_git_repo is True
    assert state.is_dirty is False
    assert state.modified_files == ()
    assert state.staged_files == ()


def test_detached_head_is_reported(git_required: None, tmp_path: Path) -> None:
    repo = tmp_path / "detached-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    sample = repo / "file.txt"
    sample.write_text("content\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    rev = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "checkout", rev.stdout.strip()],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    state = GitReadService().collect(repo)

    assert state.is_git_repo is True
    assert state.is_detached_head is True
    assert state.current_branch is not None
    assert "detached" in state.current_branch


def test_git_snapshot_persisted_with_scan(
    config_manager,
    db_path,
    project_id,
    git_required: None,
    tmp_path: Path,
) -> None:
    from grafid.scanner.models import ScanResult
    from grafid.services.snapshot_persistence import SnapshotPersistenceService

    repo = tmp_path / "persist-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    git_state = GitReadService().collect(repo)
    persistence = SnapshotPersistenceService(db_path)
    scan = ScanResult(project_name="persist-repo", project_path=str(repo))
    snapshot = persistence.save_snapshot(project_id, scan, git_state=git_state)

    stored = persistence.get_latest_git_snapshot(project_id)
    assert stored is not None
    assert stored.snapshot_id == snapshot.id
    assert stored.is_git_repo == git_state.is_git_repo
