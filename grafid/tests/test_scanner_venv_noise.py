"""Virtualenv variants (.venv-314-dev, venv-docs, site-packages) must not pollute
markers, issues, next-step hints, snapshots or handoff exports — without a glob
so broad it hides legitimate project folders.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from grafid.models.snapshot import PersistedFindingRecord
from grafid.scanner.config import ScanConfig
from grafid.scanner.ignore import (
    DEFAULT_IGNORED_DIR_NAMES,
    build_ignore_lookup,
    is_ignored_relative_path,
    is_virtualenv_dir_name,
    should_ignore_dir,
)
from grafid.scanner.service import ProjectScannerService

LOOKUP = build_ignore_lookup(DEFAULT_IGNORED_DIR_NAMES)


@pytest.mark.parametrize(
    "name",
    [".venv", "venv", ".venv-314-dev", ".venv-3.12", "venv-docs", "venv-x", "site-packages"],
)
def test_virtualenv_names_are_ignored(name: str, tmp_path: Path) -> None:
    assert is_virtualenv_dir_name(name)
    assert should_ignore_dir(tmp_path / name, LOOKUP)


@pytest.mark.parametrize(
    "name",
    ["environment", "canvenv", "venvs", "my-venv", "venv_notes", "src", "envs", ".venvrc", "avenv-x"],
)
def test_legitimate_project_folders_are_not_ignored(name: str, tmp_path: Path) -> None:
    assert not is_virtualenv_dir_name(name)
    assert not should_ignore_dir(tmp_path / name, LOOKUP)


def test_folder_that_identifies_itself_as_a_venv_is_ignored_whatever_its_name(
    tmp_path: Path,
) -> None:
    odd = tmp_path / "py314"
    odd.mkdir()
    assert not should_ignore_dir(odd, LOOKUP)
    (odd / "pyvenv.cfg").write_text("home = C:\\Python\n", encoding="utf-8")
    assert should_ignore_dir(odd, LOOKUP)


def test_user_supplied_ignore_names_cannot_switch_the_venv_rule_off(tmp_path: Path) -> None:
    only_git = build_ignore_lookup(frozenset({".git"}))
    assert should_ignore_dir(tmp_path / ".venv-314-dev", only_git)


def test_scan_never_reads_virtualenv_variants_but_reads_real_code(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("# TODO: wire the settings page\n", encoding="utf-8")
    pil = root / ".venv-314-dev" / "Lib" / "site-packages" / "PIL"
    pil.mkdir(parents=True)
    (pil / "EpsImagePlugin.py").write_text("# HACK: to support hi-res rendering\n", encoding="utf-8")
    (root / "venv-docs" / "lib").mkdir(parents=True)
    (root / "venv-docs" / "lib" / "x.py").write_text("# FIXME: third party\n", encoding="utf-8")
    (root / "py314").mkdir()
    (root / "py314" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    (root / "py314" / "y.py").write_text("# BUG: also third party\n", encoding="utf-8")
    (root / "environment").mkdir()
    (root / "environment" / "notes.py").write_text("# TODO: real project folder\n", encoding="utf-8")

    result = ProjectScannerService(ScanConfig(max_depth=8)).scan_project(root)
    paths = {finding.file_path for finding in result.findings}

    assert paths == {"src/app.py", "environment/notes.py"}
    assert result.ignored_dirs_count >= 3


@pytest.mark.parametrize(
    ("path", "ignored"),
    [
        (".venv-314-dev/Lib/site-packages/PIL/Image.py", True),
        ("venv-docs/lib/x.py", True),
        ("src/.venv/lib/y.py", True),
        ("node_modules/pkg/index.js", True),
        ("a\\site-packages\\b.py", True),
        ("src/app.py", False),
        ("environment/notes.py", False),
        ("README.md", False),
        (".venv-notes.md", False),  # a FILE named like a venv is not a directory
    ],
)
def test_stale_stored_paths_are_classified(path: str, ignored: bool) -> None:
    assert is_ignored_relative_path(path) is ignored


def _row(path: str, marker: str, text: str, line: int = 1) -> PersistedFindingRecord:
    return PersistedFindingRecord(
        id=line,
        snapshot_id=1,
        file_path=path,
        line_number=line,
        marker=marker,
        text=text,
        severity="low",
        created_at="2026-01-01T00:00:00Z",
    )


def test_findings_from_an_older_scan_under_a_venv_never_reach_summaries(tmp_path: Path) -> None:
    """The stored scan of a project refreshed before the fix still holds venv rows."""
    from grafid.services import project_overview as dh

    rows = [
        _row(".venv-314-dev/Lib/site-packages/PIL/EpsImagePlugin.py", "HACK", "to support hi-res rendering", 1),
        _row(".venv-314-dev/Lib/site-packages/PIL/Image.py", "TODO", "take new parameters", 2),
        _row("src/app.py", "TODO", "wire the settings page to the backend", 3),
    ]

    class _Snap:
        snapshot_id = 1

    with (
        patch.object(dh, "DatabaseConnection"),
        patch.object(dh, "SnapshotRepository") as snaps,
        patch.object(dh, "ScanFindingRepository") as findings,
    ):
        snaps.return_value.list_history_for_project.return_value = [_Snap()]
        findings.return_value.list_for_snapshot.return_value = rows
        kept = dh.task_findings_from_latest_scan(tmp_path / "x.db", 1)
        marker_lines = dh.top_task_marker_lines(tmp_path / "x.db", 1)

    assert [f.file_path for f in kept] == ["src/app.py"]
    assert all(".venv" not in line and "PIL" not in line for line in marker_lines)
