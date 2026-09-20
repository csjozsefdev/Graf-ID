"""Regression tests: neither the scanner nor the workflow-artifact loader may
follow a symlink/junction, whether it points inside or outside the project root.

Audit finding C1 (symlink / path-traversal): a registered project is not fully
trusted content (it can be a cloned third-party repo). A crafted symlink named
like an allowlisted workflow file, or a directory symlink anywhere in the
scanned tree, must never let Graf-Id read content from outside the project.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from grafid.resume.human_context import build_dashboard_summary
from grafid.resume.workflow_artifacts import load_workflow_artifacts
from grafid.scanner.config import ScanConfig
from grafid.scanner.service import ProjectScannerService
from grafid.utils.safe_path import is_safe_project_path, is_unsafe_symlink


def _symlinks_supported(tmp_path: Path) -> bool:
    """Best-effort probe: some CI/sandbox environments block symlink creation."""
    probe_target = tmp_path / "__symlink_probe_target__"
    probe_link = tmp_path / "__symlink_probe_link__"
    probe_target.write_text("probe", encoding="utf-8")
    try:
        probe_link.symlink_to(probe_target)
    except (OSError, NotImplementedError):
        return False
    return True


@pytest.fixture
def symlinks_ok(tmp_path: Path) -> bool:
    supported = _symlinks_supported(tmp_path)
    if not supported:
        pytest.skip("Symlink creation not permitted in this environment")
    return supported


def _make_windows_junction(link: Path, target: Path) -> bool:
    """Create a real NTFS junction (distinct from a symlink) via mklink /J."""
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and link.exists()


@pytest.fixture
def junctions_ok(tmp_path: Path) -> bool:
    if sys.platform != "win32":
        pytest.skip("Junctions are a Windows-only mechanism")
    probe_target = tmp_path / "__junction_probe_target__"
    probe_target.mkdir()
    probe_link = tmp_path / "__junction_probe_link__"
    if not _make_windows_junction(probe_link, probe_target):
        pytest.skip("Junction creation not permitted in this environment")
    return True


# ---------------------------------------------------------------------------
# grafid/utils/safe_path.py — unit-level behavior
# ---------------------------------------------------------------------------


def test_is_unsafe_symlink_false_for_regular_file(tmp_path: Path) -> None:
    regular = tmp_path / "file.txt"
    regular.write_text("hi", encoding="utf-8")
    assert is_unsafe_symlink(regular) is False


def test_is_unsafe_symlink_true_for_symlink(symlinks_ok: bool, tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("hi", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    assert is_unsafe_symlink(link) is True


def test_is_unsafe_symlink_false_for_missing_path(tmp_path: Path) -> None:
    assert is_unsafe_symlink(tmp_path / "does-not-exist.md") is False


def test_is_unsafe_symlink_false_for_broken_symlink_target(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    """A dangling symlink is still a symlink — lstat must catch it without following."""
    link = tmp_path / "broken.md"
    link.symlink_to(tmp_path / "does-not-exist-target.md")
    assert is_unsafe_symlink(link) is True


def test_is_safe_project_path_rejects_escape_via_dotdot(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("x", encoding="utf-8")
    assert is_safe_project_path(root / ".." / "outside.md", root) is False


def test_is_safe_project_path_accepts_normal_file_within_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    inside = root / "HANDOFF.md"
    inside.write_text("x", encoding="utf-8")
    assert is_safe_project_path(inside, root) is True


def test_is_unsafe_symlink_true_for_windows_junction(
    junctions_ok: bool, tmp_path: Path
) -> None:
    """
    Junctions are NTFS reparse points, not symlinks — Path.is_symlink() alone
    does not detect them (verified: it returns False), so this must go through
    the st_file_attributes/FILE_ATTRIBUTE_REPARSE_POINT check.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    junction = tmp_path / "project" / "escape"
    junction.parent.mkdir()
    assert _make_windows_junction(junction, outside)

    assert junction.is_symlink() is False  # confirms junctions bypass is_symlink()
    assert is_unsafe_symlink(junction) is True


def test_scanner_does_not_follow_windows_junction(
    junctions_ok: bool, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("# TODO: leaked via junction", encoding="utf-8")

    project = tmp_path / "project"
    project.mkdir()
    junction = project / "escape"
    assert _make_windows_junction(junction, outside)

    result = ProjectScannerService(ScanConfig(max_depth=8)).scan_project(project)

    assert not any(f.path.startswith("escape") for f in result.scanned_files)
    assert not any("leaked via junction" in f.text for f in result.findings)


# ---------------------------------------------------------------------------
# Scanner — directory walk must not follow symlinks
# ---------------------------------------------------------------------------


def test_scanner_does_not_follow_file_symlink_pointing_outside_root(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.py"
    secret.write_text("# TODO: leaked secret content", encoding="utf-8")

    project = tmp_path / "project"
    project.mkdir()
    (project / "escape.py").symlink_to(secret)

    result = ProjectScannerService(ScanConfig(max_depth=8)).scan_project(project)

    assert "escape.py" not in {f.path for f in result.scanned_files}
    assert not any("leaked secret" in f.text for f in result.findings)


def test_scanner_does_not_follow_directory_symlink_pointing_outside_root(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("# TODO: leaked secret content", encoding="utf-8")

    project = tmp_path / "project"
    project.mkdir()
    (project / "escape").symlink_to(outside, target_is_directory=True)

    result = ProjectScannerService(ScanConfig(max_depth=8)).scan_project(project)

    assert not any(f.path.startswith("escape") for f in result.scanned_files)
    assert not any("leaked secret" in f.text for f in result.findings)


def test_scanner_does_not_follow_directory_symlink_pointing_inside_root(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    """Symlinks are rejected outright (not just escape checked) — internal too."""
    project = tmp_path / "project"
    real = project / "real"
    real.mkdir(parents=True)
    (real / "notes.txt").write_text("notes file", encoding="utf-8")
    (project / "alias").symlink_to(real, target_is_directory=True)

    result = ProjectScannerService(ScanConfig(max_depth=8)).scan_project(project)

    paths = {f.path for f in result.scanned_files}
    assert "real/notes.txt" in paths
    assert not any(p.startswith("alias") for p in paths)


def test_scanner_symlink_chain_and_cycle_does_not_hang_or_escape(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    """A self-referential symlink must not cause runaway recursion or escape."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "loop").symlink_to(project, target_is_directory=True)

    result = ProjectScannerService(ScanConfig(max_depth=8)).scan_project(project)

    assert not any(f.path.startswith("loop") for f in result.scanned_files)


def test_scanner_broken_symlink_is_skipped_without_error(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "dangling.md").symlink_to(project / "does-not-exist.md")

    result = ProjectScannerService(ScanConfig(max_depth=8)).scan_project(project)

    assert "dangling.md" not in {f.path for f in result.scanned_files}


def test_scanner_normal_files_still_scanned(tmp_path: Path) -> None:
    """No-symlink baseline: fixing symlink handling must not regress normal scans."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Hello\n\n- [ ] ship the release\n", encoding="utf-8")

    result = ProjectScannerService(ScanConfig(max_depth=8)).scan_project(project)

    assert "README.md" in {f.path for f in result.scanned_files}


# ---------------------------------------------------------------------------
# Workflow-artifact loader — allowlisted-file discovery, glob discovery,
# and markdown-link following must all reject symlinks
# ---------------------------------------------------------------------------


def test_workflow_artifacts_ignores_allowlisted_file_symlink_outside_root(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("TOP SECRET CONTENT", encoding="utf-8")

    project = tmp_path / "project"
    project.mkdir()
    (project / "HANDOFF.md").symlink_to(secret)

    artifacts = load_workflow_artifacts(str(project))

    assert artifacts == ()


def test_workflow_artifacts_ignores_allowlisted_file_symlink_inside_root(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    """Even a symlink pointing at another in-root file is not followed by default.

    The target filename deliberately avoids any allowlist/glob pattern of its
    own, so the only way its content could surface is by following the link.
    """
    project = tmp_path / "project"
    project.mkdir()
    real = project / "content.md"
    real.write_text("# Real content\n\nFocus area: real work\n", encoding="utf-8")
    (project / "HANDOFF.md").symlink_to(real)

    artifacts = load_workflow_artifacts(str(project))

    assert artifacts == ()


def test_workflow_artifacts_ignores_glob_discovered_symlink(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("TOP SECRET CONTENT", encoding="utf-8")

    project = tmp_path / "project"
    project.mkdir()
    # matches the *HANDOFF*.md root-pattern discovery, not the exact allowlist name
    (project / "MY_HANDOFF_NOTES.md").symlink_to(secret)

    artifacts = load_workflow_artifacts(str(project))

    assert artifacts == ()


def test_workflow_artifacts_ignores_markdown_linked_symlink(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.md"
    secret.write_text("# Secret\n\nFocus area: exfiltrated\n", encoding="utf-8")

    project = tmp_path / "project"
    project.mkdir()
    (project / "linked.md").symlink_to(secret)
    (project / "HANDOVER.md").write_text(
        "# Handover\n\nSee [linked notes](linked.md).\n",
        encoding="utf-8",
    )

    artifacts = load_workflow_artifacts(str(project))

    assert all(a.filename != "linked.md" for a in artifacts)
    assert all("exfiltrated" not in (a.focus_area or "") for a in artifacts)


def test_workflow_artifacts_broken_symlink_is_skipped_without_error(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "HANDOFF.md").symlink_to(project / "does-not-exist.md")

    artifacts = load_workflow_artifacts(str(project))

    assert artifacts == ()


def test_workflow_artifacts_normal_files_still_load(tmp_path: Path) -> None:
    """No-symlink baseline: fixing symlink handling must not regress normal loads."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "HANDOFF.md").write_text(
        "# Handoff\n\nFocus area: ship it\n", encoding="utf-8"
    )

    artifacts = load_workflow_artifacts(str(project))

    assert len(artifacts) == 1
    assert artifacts[0].filename == "HANDOFF.md"
    assert artifacts[0].focus_area == "ship it"


# ---------------------------------------------------------------------------
# End-to-end: exfiltrated content must never reach the composed summary
# (which is what export/GrafiTalk handoff payloads are built from)
# ---------------------------------------------------------------------------


def test_symlinked_content_never_reaches_composed_summary_or_export(
    symlinks_ok: bool, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret_marker = "EXFILTRATED-SECRET-MARKER"
    secret.write_text(f"# Secret\n\nFocus area: {secret_marker}\n", encoding="utf-8")

    project = tmp_path / "project"
    project.mkdir()
    (project / "HANDOFF.md").symlink_to(secret)
    (project / "escape").symlink_to(outside, target_is_directory=True)

    artifacts = load_workflow_artifacts(str(project))
    scan_result = ProjectScannerService(ScanConfig(max_depth=8)).scan_project(project)

    summary = build_dashboard_summary(
        project_name="demo",
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=False,
        artifacts=artifacts,
        open_task_count=None,
        has_scan=True,
        git_label=None,
        task_markers=(),
    )

    serialized = str(summary)
    assert secret_marker not in serialized
    assert not any(secret_marker in f.text for f in scan_result.findings)
