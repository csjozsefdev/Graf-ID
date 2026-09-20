"""In-memory Git state models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GitCommitInfo:
    """One commit entry from read-only git log."""

    commit_hash: str
    subject: str
    author: str
    committed_at: str


@dataclass(frozen=True)
class GitState:
    """Read-only Git metadata collected for a project path."""

    is_git_repo: bool
    repo_root: str | None = None
    current_branch: str | None = None
    is_detached_head: bool = False
    is_dirty: bool = False
    modified_files: tuple[str, ...] = ()
    staged_files: tuple[str, ...] = ()
    latest_commits: tuple[GitCommitInfo, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_clean(self) -> bool:
        return self.is_git_repo and not self.is_dirty
