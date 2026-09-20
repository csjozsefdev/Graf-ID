"""Milestone 6 regression tests: remaining audit findings H1, M5, M11.

Each finding was re-verified as still reproducible against current HEAD
before being fixed here (see GATE CHECK 6 for the full re-verification
notes). H8, H9/H14, H10, M8, L5, L8, L6, L7, L15(H15) were re-checked and
confirmed already fixed by earlier milestones — no changes needed for those.
"""

from __future__ import annotations

import logging
import shutil
import stat as stat_module
import subprocess
from pathlib import Path

import pytest

from grafid.core.exceptions import DuplicateProjectError
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.git_snapshot_repository import GitSnapshotRepository
from grafid.services.context_refresh import refresh_project_scan
from grafid.services.project_registry import ProjectRegistryService

GIT_SKIP_REASON = (
    "git executable not found on PATH — environment-only skip; "
    "Graf-Id does not require git for non-git projects and this is not an app failure"
)


@pytest.fixture
def git_required() -> None:
    if not shutil.which("git"):
        pytest.skip(GIT_SKIP_REASON)


def _init_repo(repo: Path) -> None:
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


# ---------------------------------------------------------------------------
# H1 — git-only refresh must actually persist the freshly collected git state
# ---------------------------------------------------------------------------


def test_git_only_refresh_persists_updated_git_state(
    db_path, project_id: int, git_required: None
) -> None:
    registry = ProjectRegistryService(db_path)
    record = registry.get_info(str(project_id))
    repo_path = Path(record.path)
    _init_repo(repo_path)
    (repo_path / "a.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=repo_path, check=True, capture_output=True
    )

    # Full scan first, so there is an existing scan_snapshot to attach git state to.
    refresh_project_scan(db_path, project_id, git_only=False)
    with DatabaseConnection(db_path) as conn:
        before = GitSnapshotRepository(conn).get_latest_for_project(project_id)
    assert before is not None
    assert before.is_dirty is False

    # Make the tree dirty, then git-only refresh (no rescan).
    (repo_path / "a.txt").write_text("v2\n", encoding="utf-8")
    result = refresh_project_scan(db_path, project_id, git_only=True)
    assert result.mode == "git_only"

    with DatabaseConnection(db_path) as conn:
        after = GitSnapshotRepository(conn).get_latest_for_project(project_id)
    assert after is not None
    assert after.snapshot_id == before.snapshot_id, "git-only must not create a new snapshot"
    assert after.is_dirty is True
    assert "a.txt" in after.modified_files


def test_git_only_refresh_with_no_prior_snapshot_does_not_crash(
    db_path, project_id: int, git_required: None
) -> None:
    """No scan has ever run for this project — nothing to attach git state to."""
    registry = ProjectRegistryService(db_path)
    record = registry.get_info(str(project_id))
    _init_repo(Path(record.path))

    result = refresh_project_scan(db_path, project_id, git_only=True)

    assert result.scan_ok is True
    assert result.snapshot_id is None


# ---------------------------------------------------------------------------
# M5 — exceptions swallowed without logging now log a warning
# ---------------------------------------------------------------------------


def test_modified_files_from_git_logs_on_failure(
    db_path, project_id: int, caplog: pytest.LogCaptureFixture
) -> None:
    from grafid.services.project_overview import modified_files_from_git

    bad_db_path = Path(str(db_path) + "-does-not-exist")
    with caplog.at_level(logging.WARNING):
        result = modified_files_from_git(bad_db_path, project_id)

    assert result == ()
    assert any("modified files" in r.message.lower() for r in caplog.records)


def test_build_export_json_fallback_logs_on_failure(
    db_path, project_id: int, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from grafid.services import project_export

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated payload build failure")

    monkeypatch.setattr(project_export, "project_context_for_item", boom)

    with caplog.at_level(logging.WARNING):
        payload = project_export.build_export_payload(db_path, project_id, "handoff")

    # Falls back to an identity-only handoff: doesn't raise, and never leaks the
    # exception text into the exported file.
    assert payload["project_name"] == "test-project"
    assert "simulated payload build failure" not in str(payload)
    assert any("full export" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# M11 — same physical folder registered under a different path string
# ---------------------------------------------------------------------------


class _FakeIdentity:
    """
    Stand-in for os.stat_result used to mock two paths into reporting the
    same (st_dev, st_ino) physical identity.

    Docker/CPython-version portability note: must also carry a directory
    st_mode. CPython 3.12's Path.is_dir() calls self.stat() internally (so
    it hits this mock too, not just find_duplicate_physical_path()'s own
    stat() calls) and needs S_ISDIR(st_mode) to hold; CPython 3.13+
    reimplemented is_dir() to not go through stat() for this, which is why
    this was invisible when this test was first written and run only on a
    3.14 host — it broke immediately running the same test under the
    Python 3.12 Docker image (the version pyproject.toml actually targets).
    """

    def __init__(self, st_dev: int, st_ino: int) -> None:
        self.st_dev = st_dev
        self.st_ino = st_ino
        self.st_mode = stat_module.S_IFDIR | 0o755


def test_add_project_rejects_folder_with_same_physical_identity_as_existing(
    tmp_path: Path, db_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Simulates a UNC-path-vs-mapped-drive-letter (or similar) aliasing case:
    two different, genuinely distinct directories that the OS reports as the
    same physical folder (same volume + file id). Path.stat is patched only
    for these two specific resolved paths — everything else behaves for real.
    """
    registry = ProjectRegistryService(db_path)
    dir_a = tmp_path / "dir-a"
    dir_b = tmp_path / "dir-b"
    dir_a.mkdir()
    dir_b.mkdir()
    registry.add("project-a", str(dir_a))

    real_stat = Path.stat
    resolved_a = dir_a.resolve()
    resolved_b = dir_b.resolve()

    def patched_stat(self: Path, *args: object, **kwargs: object):
        if self in (resolved_a, resolved_b):
            return _FakeIdentity(st_dev=42, st_ino=4242)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", patched_stat)

    with pytest.raises(DuplicateProjectError, match="already registered under a different"):
        registry.add("project-b", str(dir_b))


def test_update_project_rejects_path_with_same_physical_identity_as_other_project(
    tmp_path: Path, db_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = ProjectRegistryService(db_path)
    dir_a = tmp_path / "dir-a"
    dir_b = tmp_path / "dir-b"
    dir_c = tmp_path / "dir-c"
    dir_a.mkdir()
    dir_b.mkdir()
    dir_c.mkdir()
    registry.add("project-a", str(dir_a))
    project_b = registry.add("project-b", str(dir_b))

    real_stat = Path.stat
    resolved_a = dir_a.resolve()
    resolved_c = dir_c.resolve()

    def patched_stat(self: Path, *args: object, **kwargs: object):
        if self in (resolved_a, resolved_c):
            return _FakeIdentity(st_dev=42, st_ino=4242)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", patched_stat)

    # project-b tries to move to dir_c, which (per the mocked identity) is
    # physically the same folder as project-a's already-registered dir_a.
    with pytest.raises(DuplicateProjectError, match="already registered under a different"):
        registry.update(project_b.id, raw_path=str(dir_c))


def test_add_project_with_genuinely_distinct_folder_still_succeeds(
    tmp_path: Path, db_path
) -> None:
    """Sanity: the physical-identity check must not false-positive on real, distinct folders."""
    registry = ProjectRegistryService(db_path)
    dir_a = tmp_path / "dir-a"
    dir_b = tmp_path / "dir-b"
    dir_a.mkdir()
    dir_b.mkdir()
    registry.add("project-a", str(dir_a))
    added = registry.add("project-b", str(dir_b))
    assert added.name == "project-b"
