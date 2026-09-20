"""Tests for filesystem scanner (Milestone 2A)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from grafid.core.constants import SCAN_MAX_FILE_SIZE_BYTES
from grafid.core.exceptions import ScanError, ValidationError
from grafid.scanner.config import ScanConfig
from grafid.scanner.ignore import (
    build_ignore_lookup,
    build_prefix_lookup,
    should_ignore_dir,
)
from grafid.scanner.reader import read_file_text
from grafid.scanner.service import ProjectScannerService


def _make_project_tree(root: Path) -> None:
    (root / "README.md").write_text("# Root readme", encoding="utf-8")
    (root / "notes.txt").write_text("notes file", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "TODO.md").write_text("- [ ] item", encoding="utf-8")
    (root / "src" / "ignore.py").write_text("print('skip')", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "pkg.md").write_text("hidden", encoding="utf-8")
    (root / "deep").mkdir()
    current = root / "deep"
    for index in range(12):
        current = current / f"level{index}"
        current.mkdir()
    (current / "bottom.md").write_text("deep file", encoding="utf-8")


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "demo-project"
    root.mkdir()
    _make_project_tree(root)
    return root


@pytest.fixture
def scanner() -> ProjectScannerService:
    return ProjectScannerService(
        ScanConfig(max_depth=4, max_file_size_bytes=1024, preview_max_chars=50)
    )


def test_ignored_folders_are_not_scanned(
    scanner: ProjectScannerService, project_root: Path
) -> None:
    result = scanner.scan_project(project_root)

    scanned_paths = {item.path for item in result.scanned_files}
    assert "node_modules/pkg.md" not in scanned_paths
    assert "README.md" in scanned_paths


def test_max_depth_limits_recursion(
    scanner: ProjectScannerService, project_root: Path
) -> None:
    result = scanner.scan_project(project_root)

    assert all("bottom.md" not in item.path for item in result.scanned_files)
    assert result.skipped_count > 0


def test_large_file_is_skipped_with_warning(project_root: Path) -> None:
    large = project_root / "BIG.txt"
    large.write_bytes(b"x" * (SCAN_MAX_FILE_SIZE_BYTES + 1))

    service = ProjectScannerService(
        ScanConfig(max_file_size_bytes=128, max_depth=8, preview_max_chars=20)
    )
    result = service.scan_project(project_root)

    assert "BIG.txt" not in {item.path for item in result.scanned_files}
    assert any("large file" in warning.lower() for warning in result.warnings)


def test_encoding_fallback_reads_non_utf8(project_root: Path) -> None:
    latin = project_root / "latin.txt"
    latin.write_bytes("caf\xe9".encode("latin-1"))

    service = ProjectScannerService(ScanConfig(max_depth=8, preview_max_chars=20))
    result = service.scan_project(project_root)

    match = next(item for item in result.scanned_files if item.path == "latin.txt")
    assert match.preview is not None
    assert "caf" in match.preview


def test_invalid_encoding_returns_warning(project_root: Path) -> None:
    binary = project_root / "binary.txt"
    binary.write_bytes(b"\xff\xfe\xfd")

    with patch("grafid.scanner.reader.ENCODING_CANDIDATES", ("utf-8", "ascii")):
        text, warning = read_file_text(binary, max_file_size_bytes=4096)
    assert text is None
    assert warning is not None
    assert "decode" in warning.lower()


def test_inaccessible_subdirectory_adds_warning(
    scanner: ProjectScannerService, project_root: Path
) -> None:
    blocked = project_root / "blocked"
    blocked.mkdir()
    (blocked / "secret.md").write_text("hidden", encoding="utf-8")

    original_iterdir = Path.iterdir

    def patched_iterdir(self: Path):
        if self.resolve() == blocked.resolve():
            raise PermissionError("denied")
        return original_iterdir(self)

    with patch.object(Path, "iterdir", patched_iterdir):
        result = scanner.scan_project(project_root)

    assert any("Permission denied" in warning for warning in result.warnings)


def test_inaccessible_project_path_raises() -> None:
    service = ProjectScannerService()
    missing = Path("/nonexistent/graf-id-scan-test")

    with pytest.raises((ScanError, ValidationError)):
        service.scan_project(missing)


def test_should_ignore_dir_matches_defaults() -> None:
    lookup = build_ignore_lookup(frozenset({".git", "node_modules", "target"}))
    prefix = build_prefix_lookup(frozenset({"desktop/src-tauri/runtime"}))
    root = Path("/proj")
    assert should_ignore_dir(Path("/proj/node_modules"), lookup)
    assert should_ignore_dir(Path("/proj/desktop/src-tauri/target"), lookup)
    assert should_ignore_dir(
        Path("/proj/desktop/src-tauri/runtime"),
        lookup,
        root=root,
        ignored_prefix_lookup=prefix,
    )
    assert not should_ignore_dir(Path("/proj/src"), lookup)
    assert not should_ignore_dir(
        Path("/proj/grafid/runtime"),
        lookup,
        root=root,
        ignored_prefix_lookup=prefix,
    )


def test_target_and_runtime_trees_are_ignored(project_root: Path) -> None:
    tauri = project_root / "desktop" / "src-tauri"
    tauri.mkdir(parents=True)
    runtime = tauri / "runtime" / "Lib"
    runtime.mkdir(parents=True)
    (runtime / "fake.py").write_text("# TODO: embedded noise\n", encoding="utf-8")
    target = tauri / "target" / "debug"
    target.mkdir(parents=True)
    (target / "artifact.rs").write_text("// FIXME: build noise\n", encoding="utf-8")
    pkg_runtime = project_root / "grafid" / "runtime"
    pkg_runtime.mkdir(parents=True)
    (pkg_runtime / "passive.py").write_text("# TODO: real source\n", encoding="utf-8")

    result = ProjectScannerService(ScanConfig(max_depth=12)).scan_project(project_root)
    paths = {item.path for item in result.scanned_files}
    findings_paths = {f.file_path for f in result.findings}

    assert any(f.file_path == "grafid/runtime/passive.py" for f in result.findings)
    assert not any("src-tauri/runtime" in p for p in paths)
    assert not any("src-tauri/target" in p for p in paths)
    assert not any("src-tauri/runtime" in p for p in findings_paths)
    assert result.ignored_dirs_count >= 2


def test_should_ignore_dir_case_insensitive_on_windows() -> None:
    if sys.platform != "win32":
        pytest.skip("Windows-specific case behavior")
    lookup = build_ignore_lookup(frozenset({"TARGET", "Node_Modules"}))
    assert should_ignore_dir(Path("/proj/TARGET"), lookup)
    assert should_ignore_dir(Path("/proj/node_modules"), lookup)


def test_scanned_file_metadata(scanner: ProjectScannerService, project_root: Path) -> None:
    result = scanner.scan_project(project_root)
    readme = next(item for item in result.scanned_files if item.path == "README.md")

    assert readme.file_type == "readme"
    assert readme.size_bytes > 0
    assert readme.modified_at.endswith("+00:00")
    assert readme.preview is not None
