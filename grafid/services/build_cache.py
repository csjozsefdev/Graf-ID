"""Detect and clean Rust/Cargo build caches for registered projects.

Small improvement from the audit (docs/CLEANUP.md already documented the
manual `cargo clean` workflow for this repo's own desktop/src-tauri/target/
growing to several GB during development). Generalized to any registered
project that turns out to be (or contain) a Cargo crate — not specific to
the Graf-Id repo itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from grafid.core.exceptions import GrafIdError, ValidationError
from grafid.utils.logging_setup import get_logger
from grafid.utils.safe_path import is_safe_project_path, is_unsafe_symlink

logger = get_logger("build_cache")

if sys.platform == "win32":
    _SUBPROCESS_CREATE_FLAGS = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
else:
    _SUBPROCESS_CREATE_FLAGS = 0

# How deep under the project root to look for a Cargo.toml. Cargo crates are
# rarely nested more than a couple of levels down (e.g. this repo's own
# desktop/src-tauri/Cargo.toml is 2 levels deep); bounded to keep detection
# fast and to match the scanner's own "don't walk forever" discipline (M7).
MAX_SEARCH_DEPTH = 4
# Bounded directory-size walk (M7-style safety net) — a target/ directory
# with an unreasonable number of entries stops counting rather than hanging.
MAX_SIZE_SCAN_ENTRIES = 300_000

_SKIP_DIR_NAMES = frozenset(
    {".git", "node_modules", "target", "__pycache__", ".venv", "venv", "dist", "build"}
)


class BuildCacheError(GrafIdError):
    """Raised when build-cache detection or cleaning fails."""


@dataclass(frozen=True)
class DetectedBuildCache:
    """One Cargo.toml + adjacent target/ directory found under a project."""

    kind: str  # "cargo" — the only kind detected today
    manifest_path: str  # relative to the project root, POSIX-style
    target_path: str  # relative to the project root, POSIX-style
    size_bytes: int


def detect_rust_build_caches(project_root: Path) -> list[DetectedBuildCache]:
    """Bounded search for Cargo.toml files with an adjacent target/ directory."""
    root = project_root.resolve()
    found: list[DetectedBuildCache] = []
    _walk_for_manifests(root, root, depth=0, found=found)
    return found


def _walk_for_manifests(
    root: Path, current: Path, *, depth: int, found: list[DetectedBuildCache]
) -> None:
    if depth > MAX_SEARCH_DEPTH:
        return

    manifest = current / "Cargo.toml"
    if (
        manifest.is_file()
        and not is_unsafe_symlink(manifest)
        and is_safe_project_path(manifest, root)
    ):
        target_dir = current / "target"
        if target_dir.is_dir() and is_safe_project_path(target_dir, root):
            found.append(
                DetectedBuildCache(
                    kind="cargo",
                    manifest_path=manifest.relative_to(root).as_posix(),
                    target_path=target_dir.relative_to(root).as_posix(),
                    size_bytes=estimate_directory_size(target_dir),
                )
            )

    try:
        entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return

    for entry in entries:
        if not entry.is_dir():
            continue
        if entry.name in _SKIP_DIR_NAMES:
            continue
        if is_unsafe_symlink(entry):
            continue
        _walk_for_manifests(root, entry, depth=depth + 1, found=found)


def estimate_directory_size(path: Path, *, max_entries: int = MAX_SIZE_SCAN_ENTRIES) -> int:
    """
    Bounded recursive size sum in bytes.

    Never follows symlinks or Windows junctions/reparse points (a target/
    dir has no business containing one pointing outside itself, and this is
    only used for a size estimate, not a security boundary). Stops counting
    once max_entries is exceeded, returning the partial total rather than
    hanging on a pathological tree.

    M9 (found during re-audit): entry.is_symlink() alone does not detect an
    NTFS junction/mount point on Windows (only IO_REPARSE_TAG_SYMLINK, not
    IO_REPARSE_TAG_MOUNT_POINT) — verified empirically, a junction nested
    inside target/ was silently traversed and its target's bytes counted.
    is_unsafe_symlink() checks the reparse-point attribute bit directly (the
    same check used everywhere else in this codebase for this purpose) and
    catches both.
    """
    total = 0
    count = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    count += 1
                    if count > max_entries:
                        return total
                    try:
                        entry_path = Path(entry.path)
                        if is_unsafe_symlink(entry_path):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def clean_rust_build_cache(project_root: Path, manifest_relpath: str) -> DetectedBuildCache:
    """
    Run `cargo clean` for one detected build cache, after re-validating it.

    Never trusts a client-supplied path at face value: the resolved manifest
    and its target/ directory must both stay within the project root and
    must not be reached through a symlink/reparse point — the same
    containment discipline C1 established for reads applies here even more
    strictly, since this deletes files.
    """
    root = project_root.resolve()
    manifest = (root / manifest_relpath).resolve()

    if manifest.name != "Cargo.toml":
        raise ValidationError(f"Not a Cargo.toml path: {manifest_relpath}")
    if not is_safe_project_path(manifest, root):
        raise ValidationError("Build cache manifest path is not a safe project path")
    if not manifest.is_file():
        raise ValidationError(f"Cargo.toml not found: {manifest}")

    target_dir = manifest.parent / "target"
    if not is_safe_project_path(target_dir, root):
        raise ValidationError("Build cache target path is not a safe project path")
    if not target_dir.is_dir():
        raise BuildCacheError(f"No build cache to clean at {target_dir}")

    size_before = estimate_directory_size(target_dir)

    cargo = shutil.which("cargo")
    if not cargo:
        raise BuildCacheError(
            "cargo was not found on PATH. Install Rust/Cargo, or delete the "
            f"folder manually: {target_dir}"
        )

    # M9 (found during re-audit): cargo resolves its own target directory —
    # via CARGO_TARGET_DIR or a .cargo/config.toml build.target-dir setting —
    # independently of the target_dir validated above. Without --target-dir
    # pinning it explicitly, a CARGO_TARGET_DIR set in this process's own
    # environment (a common, non-malicious setup for centralizing build
    # caches) makes `cargo clean` delete that directory instead of the one
    # we validated and reported the size of — verified end-to-end: an
    # unrelated directory outside the project root was silently deleted
    # while the size shown to the user described the untouched target_dir.
    # --target-dir takes precedence over the env var (verified), and
    # stripping CARGO_TARGET_DIR from the child's environment closes the
    # same gap a second way.
    env = os.environ.copy()
    env.pop("CARGO_TARGET_DIR", None)
    try:
        result = subprocess.run(  # noqa: S603
            [
                cargo,
                "clean",
                "--manifest-path",
                str(manifest),
                "--target-dir",
                str(target_dir),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=_SUBPROCESS_CREATE_FLAGS,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise BuildCacheError(f"cargo clean timed out: {exc}") from exc
    except OSError as exc:
        raise BuildCacheError(f"Failed to run cargo clean: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise BuildCacheError(f"cargo clean failed (exit {result.returncode}): {detail}")

    logger.info(
        "Cleaned Rust build cache at %s (freed ~%s bytes)", target_dir, size_before
    )
    return DetectedBuildCache(
        kind="cargo",
        manifest_path=manifest_relpath,
        target_path=target_dir.relative_to(root).as_posix(),
        size_bytes=size_before,
    )
