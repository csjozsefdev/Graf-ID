"""Read-only Git metadata collection service."""

from __future__ import annotations

from pathlib import Path

from grafid.core.constants import GIT_MAX_STATUS_ENTRIES, GIT_MAX_SUBJECT_CHARS
from grafid.git.detection import find_repo_root
from grafid.git.models import GitCommitInfo, GitState
from grafid.git.runner import git_available, run_git_readonly
from grafid.git.status_parser import parse_porcelain_status
from grafid.utils.logging_setup import get_logger

logger = get_logger("git.service")

MAX_COMMITS = 5
LOG_FORMAT = "%H%x1f%s%x1f%an%x1f%aI"


class GitReadService:
    """Collect Git repository metadata without write operations."""

    def collect(self, project_path: Path | str) -> GitState:
        """
        Inspect Git state for a project path.

        Never raises for missing Git; warnings are returned in GitState.
        """
        path = Path(project_path).expanduser().resolve()
        warnings: list[str] = []

        if not git_available():
            logger.info("Git executable not found on PATH")
            return GitState(is_git_repo=False, warnings=("Git executable not found",))

        repo_root = find_repo_root(path)
        if repo_root is None:
            logger.debug("No Git repository detected for %s", path)
            return GitState(is_git_repo=False)

        try:
            if not _is_inside_work_tree(repo_root):
                return GitState(
                    is_git_repo=False,
                    warnings=("Path is not inside a valid Git work tree",),
                )
        except Exception as exc:
            warnings.append(f"Git work tree check failed: {exc}")
            return GitState(is_git_repo=False, warnings=tuple(warnings))

        branch, detached, branch_warnings = _read_branch(repo_root)
        warnings.extend(branch_warnings)

        staged, modified, dirty, status_warnings = _read_status(repo_root)
        warnings.extend(status_warnings)

        commits, commit_warnings = _read_recent_commits(repo_root)
        warnings.extend(commit_warnings)

        logger.info(
            "Git state for %s: branch=%s dirty=%s detached=%s",
            repo_root,
            branch,
            dirty,
            detached,
        )

        return GitState(
            is_git_repo=True,
            repo_root=str(repo_root),
            current_branch=branch,
            is_detached_head=detached,
            is_dirty=dirty,
            modified_files=tuple(modified),
            staged_files=tuple(staged),
            latest_commits=tuple(commits),
            warnings=tuple(warnings),
        )


def _is_inside_work_tree(repo_root: Path) -> bool:
    code, stdout, _stderr = run_git_readonly(repo_root, "rev-parse", "--is-inside-work-tree")
    return code == 0 and stdout.lower() == "true"


def _read_branch(repo_root: Path) -> tuple[str | None, bool, list[str]]:
    warnings: list[str] = []
    code, stdout, stderr = run_git_readonly(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        warnings.append(f"Could not read branch: {stderr or 'unknown error'}")
        return None, False, warnings

    branch = stdout.strip()
    if branch == "HEAD":
        detached = True
        short_code, short_out, short_err = run_git_readonly(
            repo_root, "rev-parse", "--short", "HEAD"
        )
        if short_code == 0:
            branch = f"detached@{short_out}"
        else:
            branch = "detached"
            if short_err:
                warnings.append(f"Could not read detached HEAD: {short_err}")
        return branch, detached, warnings

    return branch, False, warnings


def _read_status(
    repo_root: Path,
) -> tuple[list[str], list[str], bool, list[str]]:
    warnings: list[str] = []
    code, stdout, stderr = run_git_readonly(repo_root, "status", "--porcelain")

    if code != 0:
        warnings.append(f"Could not read status: {stderr or 'unknown error'}")
        return [], [], False, warnings

    staged, modified, dirty = parse_porcelain_status(stdout)

    # L2: a pathological working tree (huge accidental change set) shouldn't
    # inflate collected git state without bound; dirty is computed from the
    # untruncated lists so truncation never hides that the tree is dirty.
    if len(staged) > GIT_MAX_STATUS_ENTRIES:
        warnings.append(
            f"Staged file list truncated at {GIT_MAX_STATUS_ENTRIES} "
            f"(actual: {len(staged)})"
        )
        staged = staged[:GIT_MAX_STATUS_ENTRIES]
    if len(modified) > GIT_MAX_STATUS_ENTRIES:
        warnings.append(
            f"Modified file list truncated at {GIT_MAX_STATUS_ENTRIES} "
            f"(actual: {len(modified)})"
        )
        modified = modified[:GIT_MAX_STATUS_ENTRIES]

    return staged, modified, dirty, warnings


def _read_recent_commits(repo_root: Path) -> tuple[list[GitCommitInfo], list[str]]:
    warnings: list[str] = []
    code, stdout, stderr = run_git_readonly(
        repo_root,
        "log",
        f"-n{MAX_COMMITS}",
        f"--pretty=format:{LOG_FORMAT}",
    )
    if code != 0:
        warnings.append(f"Could not read commits: {stderr or 'unknown error'}")
        return [], warnings

    commits: list[GitCommitInfo] = []
    for line in stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        commits.append(
            GitCommitInfo(
                commit_hash=parts[0],
                subject=_truncate(parts[1], GIT_MAX_SUBJECT_CHARS),
                author=_truncate(parts[2], GIT_MAX_SUBJECT_CHARS),
                committed_at=parts[3],
            )
        )
    return commits, warnings


def _truncate(text: str, max_chars: int) -> str:
    """L2: git allows an arbitrarily long single-line subject/author; cap it."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."
