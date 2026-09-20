"""Tests for the Rust/Cargo build-cache detect/clean small improvement."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from grafid.core.exceptions import ValidationError
from grafid.ipc.build_cache_handlers import handle_clean_build_cache, handle_detect_build_caches
from grafid.services.build_cache import (
    BuildCacheError,
    clean_rust_build_cache,
    detect_rust_build_caches,
    estimate_directory_size,
)
from grafid.services.project_registry import ProjectRegistryService

CARGO_SKIP_REASON = (
    "cargo executable not found on PATH — environment-only skip; "
    "Graf-Id does not require Rust/Cargo for non-Rust projects and this is not an app failure"
)

# Newer cargo refuses `cargo clean` on a target/ dir missing this marker
# (a real `cargo build` always writes it) — _write_toy_crate() adds it to
# every fake target/ dir, so every size_bytes assertion below must account
# for its extra bytes on top of the requested target_bytes.
_CACHEDIR_TAG_CONTENT = (
    "Signature: 8a477f597d28d172789f06886806bc55\n"
    "# This file is a cache directory tag created by cargo.\n"
    "# For information about cache directory tags see https://bford.info/cachedir/\n"
)
_CACHEDIR_TAG_SIZE = len(_CACHEDIR_TAG_CONTENT.encode("utf-8"))


@pytest.fixture
def cargo_required() -> None:
    if not shutil.which("cargo"):
        pytest.skip(CARGO_SKIP_REASON)


def _require_windows_for_junctions() -> None:
    """
    Docker/Linux hardening: NTFS junctions (mklink /J) are a Windows-only
    mechanism. Before this guard, the two junction tests below called
    subprocess.run(["cmd", ...]) directly and *crashed* with
    FileNotFoundError on any platform without a `cmd` binary — an error, not
    a clean skip, which would fail a containerized Linux test run outright
    instead of just reporting it as environment-only coverage. Matches the
    same sys.platform pattern already used in test_symlink_safety.py.
    """
    if sys.platform != "win32":
        pytest.skip("Junctions are a Windows-only mechanism")


@pytest.fixture
def windows_required() -> None:
    _require_windows_for_junctions()


def test_require_windows_for_junctions_skips_on_non_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Regression for the Docker/Linux crash: on any non-Windows platform this
    must raise pytest's Skipped signal, not let a caller fall through to
    actually invoking `cmd`/`mklink` (which don't exist there).
    """
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(pytest.skip.Exception):
        _require_windows_for_junctions()


def test_require_windows_for_junctions_passes_through_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    _require_windows_for_junctions()  # must not raise/skip


def _write_toy_crate(root: Path, *, target_bytes: int = 1000) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Cargo.toml").write_text(
        '[package]\nname = "toy"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    src = root / "src"
    src.mkdir(exist_ok=True)
    (src / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    target = root / "target"
    target.mkdir(exist_ok=True)
    (target / "dummy.bin").write_bytes(b"a" * target_bytes)
    # newline="" avoids Windows' \n -> \r\n text-mode translation, which
    # would otherwise make the file's actual byte count on disk diverge
    # from len(_CACHEDIR_TAG_CONTENT.encode()) and break the size_bytes
    # assertions below.
    (target / "CACHEDIR.TAG").write_text(_CACHEDIR_TAG_CONTENT, encoding="utf-8", newline="")
    return root


def _make_windows_junction(link: Path, target: Path) -> bool:
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and link.exists()


# ---------------------------------------------------------------------------
# estimate_directory_size
# ---------------------------------------------------------------------------


def test_estimate_directory_size_sums_files(tmp_path: Path) -> None:
    d = tmp_path / "dir"
    d.mkdir()
    (d / "a.bin").write_bytes(b"x" * 100)
    sub = d / "sub"
    sub.mkdir()
    (sub / "b.bin").write_bytes(b"y" * 250)

    assert estimate_directory_size(d) == 350


def test_estimate_directory_size_empty_dir_is_zero(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    assert estimate_directory_size(d) == 0


def test_estimate_directory_size_missing_dir_is_zero(tmp_path: Path) -> None:
    assert estimate_directory_size(tmp_path / "does-not-exist") == 0


def test_estimate_directory_size_does_not_traverse_junction(
    tmp_path: Path, windows_required: None
) -> None:
    """
    M9 regression: entry.is_symlink() alone misses NTFS junctions, so a
    junction nested inside the scanned tree used to have its target's bytes
    silently counted.
    """
    d = tmp_path / "dir"
    d.mkdir()
    (d / "local.bin").write_bytes(b"x" * 100)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "big.bin").write_bytes(b"y" * 5000)

    link = d / "junction-to-outside"
    if not _make_windows_junction(link, outside):
        pytest.skip("Junction creation not permitted in this environment")

    assert estimate_directory_size(d) == 100


# ---------------------------------------------------------------------------
# detect_rust_build_caches
# ---------------------------------------------------------------------------


def test_detect_finds_manifest_at_project_root(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _write_toy_crate(project, target_bytes=1234)

    caches = detect_rust_build_caches(project)

    assert len(caches) == 1
    assert caches[0].kind == "cargo"
    assert caches[0].manifest_path == "Cargo.toml"
    assert caches[0].target_path == "target"
    assert caches[0].size_bytes == 1234 + _CACHEDIR_TAG_SIZE


def test_detect_finds_nested_manifest_like_this_repo(tmp_path: Path) -> None:
    """Mirrors Graf-Id's own layout: Cargo.toml nested under desktop/src-tauri/."""
    project = tmp_path / "workspace"
    nested = project / "desktop" / "src-tauri"
    _write_toy_crate(nested, target_bytes=500)

    caches = detect_rust_build_caches(project)

    assert len(caches) == 1
    assert caches[0].manifest_path == "desktop/src-tauri/Cargo.toml"
    assert caches[0].target_path == "desktop/src-tauri/target"
    assert caches[0].size_bytes == 500 + _CACHEDIR_TAG_SIZE


def test_detect_returns_empty_for_non_rust_project(tmp_path: Path) -> None:
    project = tmp_path / "python-proj"
    project.mkdir()
    (project / "README.md").write_text("hi", encoding="utf-8")

    assert detect_rust_build_caches(project) == []


def test_detect_ignores_manifest_without_target_dir(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "Cargo.toml").write_text('[package]\nname="x"\nversion="0.1.0"\n', encoding="utf-8")

    assert detect_rust_build_caches(project) == []


def test_detect_ignores_junction_target_directory(
    tmp_path: Path, windows_required: None
) -> None:
    """M11/C1-style containment: a target/ reached only through a junction is not trusted."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "Cargo.toml").write_text('[package]\nname="x"\nversion="0.1.0"\n', encoding="utf-8")
    outside = tmp_path / "outside-real-target"
    outside.mkdir()
    (outside / "leak.bin").write_bytes(b"x" * 999)

    link = project / "target"
    if not _make_windows_junction(link, outside):
        pytest.skip("Junction creation not permitted in this environment")

    assert detect_rust_build_caches(project) == []


def test_detect_does_not_descend_past_max_depth(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    deep = project
    for i in range(10):
        deep = deep / f"level{i}"
    _write_toy_crate(deep, target_bytes=10)

    assert detect_rust_build_caches(project) == []


# ---------------------------------------------------------------------------
# clean_rust_build_cache
# ---------------------------------------------------------------------------


def test_clean_removes_target_directory(tmp_path: Path, cargo_required: None) -> None:
    project = tmp_path / "proj"
    _write_toy_crate(project, target_bytes=2048)
    target = project / "target"
    assert target.exists()

    result = clean_rust_build_cache(project, "Cargo.toml")

    assert result.size_bytes == 2048 + _CACHEDIR_TAG_SIZE
    assert not target.exists()
    assert (project / "Cargo.toml").is_file()  # source untouched
    assert (project / "src" / "main.rs").is_file()


def test_clean_ignores_cargo_target_dir_env_var(
    tmp_path: Path, cargo_required: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    M9 (Critical, found during re-audit): without pinning --target-dir,
    `cargo clean` resolves its own target directory via CARGO_TARGET_DIR
    independently of the path this function validated and reported the size
    of — verified to silently delete an unrelated directory outside the
    project root while claiming to have cleaned the (untouched) validated
    target_dir. CARGO_TARGET_DIR is a common, non-malicious developer
    setting (centralizing build caches across projects), not an attack —
    no adversarial input was needed to trigger real data loss outside the
    declared safety boundary.
    """
    project = tmp_path / "proj"
    _write_toy_crate(project, target_bytes=2048)
    target = project / "target"

    evil_target = tmp_path / "unrelated-directory-outside-project"
    evil_target.mkdir()
    (evil_target / "do-not-touch.bin").write_bytes(b"z" * 9999)
    monkeypatch.setenv("CARGO_TARGET_DIR", str(evil_target))

    result = clean_rust_build_cache(project, "Cargo.toml")

    assert result.size_bytes == 2048 + _CACHEDIR_TAG_SIZE
    assert not target.exists()  # the validated target_dir was actually cleaned
    assert (evil_target / "do-not-touch.bin").is_file()  # nothing outside touched
    assert len(list(evil_target.iterdir())) == 1


def test_clean_rejects_manifest_path_escaping_project_root(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    outside = tmp_path / "outside"
    _write_toy_crate(outside)

    with pytest.raises(ValidationError):
        clean_rust_build_cache(project, "../outside/Cargo.toml")


def test_clean_rejects_non_cargo_toml_path(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "notes.txt").write_text("x", encoding="utf-8")

    with pytest.raises(ValidationError):
        clean_rust_build_cache(project, "notes.txt")


def test_clean_rejects_missing_manifest(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()

    with pytest.raises(ValidationError):
        clean_rust_build_cache(project, "Cargo.toml")


def test_clean_raises_when_no_target_dir_exists(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "Cargo.toml").write_text('[package]\nname="x"\nversion="0.1.0"\n', encoding="utf-8")

    with pytest.raises(BuildCacheError):
        clean_rust_build_cache(project, "Cargo.toml")


def test_clean_rejects_junction_target_directory(
    tmp_path: Path, windows_required: None
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "Cargo.toml").write_text('[package]\nname="x"\nversion="0.1.0"\n', encoding="utf-8")
    outside = tmp_path / "outside-real-target"
    outside.mkdir()
    (outside / "keepme.bin").write_bytes(b"x" * 10)

    link = project / "target"
    if not _make_windows_junction(link, outside):
        pytest.skip("Junction creation not permitted in this environment")

    with pytest.raises(ValidationError):
        clean_rust_build_cache(project, "Cargo.toml")

    # The real, outside directory must be completely untouched.
    assert (outside / "keepme.bin").is_file()


# ---------------------------------------------------------------------------
# IPC handlers
# ---------------------------------------------------------------------------


def test_handle_detect_build_caches_ipc(db_path, config_manager, project_id: int) -> None:
    registry = ProjectRegistryService(db_path)
    record = registry.get_info(str(project_id))
    _write_toy_crate(Path(record.path), target_bytes=777)

    response = handle_detect_build_caches(project_id, config_manager)

    assert response.ok is True
    assert response.data is not None
    caches = response.data["caches"]
    assert len(caches) == 1
    assert caches[0]["manifest_path"] == "Cargo.toml"
    assert caches[0]["size_bytes"] == 777 + _CACHEDIR_TAG_SIZE


def test_handle_detect_build_caches_ipc_empty_for_non_rust_project(
    db_path, config_manager, project_id: int
) -> None:
    response = handle_detect_build_caches(project_id, config_manager)
    assert response.ok is True
    assert response.data["caches"] == []


def test_handle_clean_build_cache_ipc(
    db_path, config_manager, project_id: int, cargo_required: None
) -> None:
    registry = ProjectRegistryService(db_path)
    record = registry.get_info(str(project_id))
    _write_toy_crate(Path(record.path), target_bytes=333)

    response = handle_clean_build_cache(project_id, "Cargo.toml", config_manager)

    assert response.ok is True
    assert response.data["cache"]["size_bytes"] == 333 + _CACHEDIR_TAG_SIZE
    assert not (Path(record.path) / "target").exists()


def test_handle_clean_build_cache_ipc_rejects_path_traversal(
    db_path, config_manager, project_id: int
) -> None:
    response = handle_clean_build_cache(project_id, "../../evil/Cargo.toml", config_manager)
    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "validation_error"
