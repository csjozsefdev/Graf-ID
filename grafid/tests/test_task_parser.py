"""Tests for TODO/FIXME task marker parsing (Milestone 2B)."""

from __future__ import annotations

from pathlib import Path


from grafid.cli.scan import format_finding_detail, _print_scan_summary
from grafid.core.constants import SCAN_MAX_FILE_SIZE_BYTES
from grafid.scanner.config import ScanConfig
from grafid.scanner.models import ScanResult, TaskFinding
from grafid.scanner.service import ProjectScannerService
from grafid.scanner.task_parser import parse_task_markers


def test_parser_handles_empty_and_malformed_content() -> None:
    assert (
        parse_task_markers("", file_path="empty.py", created_at="2026-01-01T00:00:00+00:00")
        == []
    )
    malformed = '{"broken": true,\n  "note": "TODO in string"\n' + ("x" * 5000)
    findings = parse_task_markers(
        malformed, file_path="bad.json", created_at="2026-01-01T00:00:00+00:00"
    )
    assert isinstance(findings, list)


def test_parse_is_deterministic() -> None:
    content = "# TODO: alpha\n// FIXME: beta\n"
    first = parse_task_markers(
        content, file_path="a.py", created_at="2026-01-01T00:00:00+00:00"
    )
    second = parse_task_markers(
        content, file_path="a.py", created_at="2026-01-01T00:00:00+00:00"
    )
    assert first == second


def test_parse_todo_marker_line_number() -> None:
    content = "# header\n# TODO: refactor auth module\n"
    findings = parse_task_markers(
        content, file_path="src/app.py", created_at="2026-01-01T00:00:00+00:00"
    )

    assert len(findings) == 1
    assert findings[0].marker == "TODO"
    assert findings[0].line_number == 2
    assert findings[0].severity == "low"
    assert "refactor auth" in findings[0].text


def test_parse_fixme_marker_severity() -> None:
    content = "// FIXME: memory leak in cache\n"
    findings = parse_task_markers(
        content, file_path="lib.js", created_at="2026-01-01T00:00:00+00:00"
    )

    assert findings[0].marker == "FIXME"
    assert findings[0].severity == "high"


def test_multiple_markers_on_one_line() -> None:
    content = "// TODO: alpha  FIXME: beta\n"
    findings = parse_task_markers(
        content, file_path="a.ts", created_at="2026-01-01T00:00:00+00:00"
    )
    markers = {item.marker for item in findings}
    assert markers == {"TODO", "FIXME"}


def test_same_text_on_different_lines_are_separate_findings() -> None:
    content = "# TODO: same task\n# TODO: same task\n"
    findings = parse_task_markers(
        content, file_path="a.md", created_at="2026-01-01T00:00:00+00:00"
    )
    assert len(findings) == 2
    assert findings[0].line_number == 1
    assert findings[1].line_number == 2


def test_next_marker_forms_detected() -> None:
    ts = "2026-01-01T00:00:00+00:00"
    cases = [
        ("NEXT: ship resume panel", "ship resume panel"),
        ("# NEXT: update docs", "update docs"),
        ("// NEXT refactor parser", "refactor parser"),
        ("<!-- NEXT: html note -->", "html note -->"),
        ("- NEXT: list item", "list item"),
        ("  next: lowercase marker", "lowercase marker"),
    ]
    for line, expected in cases:
        findings = parse_task_markers(line, file_path="f.txt", created_at=ts)
        assert len(findings) == 1, line
        assert findings[0].marker == "NEXT"
        assert expected in findings[0].text


def test_next_prose_not_detected() -> None:
    ts = "2026-01-01T00:00:00+00:00"
    prose = [
        "Suggested next step for the user",
        "Plan the next milestone before release",
        'typer.Option("--next", help="Suggested next step.")',
        "Continue from: next action item",
        "## Next milestone",
        "# Not NEXT because heading uses double hash",
    ]
    for line in prose:
        findings = parse_task_markers(line, file_path="f.py", created_at=ts)
        assert findings == [], line


def test_ignores_todo_fixme_inside_string_literals() -> None:
    ts = "2026-01-01T00:00:00+00:00"
    ui_lines = [
        '    return "Use Refresh context to scan the project and update TODO/FIXME data.";',
        '  return `${count} open TODO/FIXME marker${count === 1 ? "" : "s"} in the latest scan.`;',
        '    return "No open TODO/FIXME markers in the latest scan.";',
    ]
    for line in ui_lines:
        assert parse_task_markers(line, file_path="utils.ts", created_at=ts) == [], line


def test_accepts_todo_fixme_in_real_comments() -> None:
    ts = "2026-01-01T00:00:00+00:00"
    cases = [
        ("// FIXME: memory leak in cache\n", "FIXME", "memory leak"),
        ("# TODO: refactor auth module\n", "TODO", "refactor auth"),
        ("def run():\n    pass  # TODO: add validation\n", "TODO", "add validation"),
    ]
    for content, marker, snippet in cases:
        findings = parse_task_markers(content, file_path="f.py", created_at=ts)
        assert len(findings) >= 1, content
        assert findings[0].marker == marker
        assert snippet in findings[0].text


def test_skip_selected_project_card_file_in_scanner(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    utils = root / "desktop" / "src" / "utils"
    utils.mkdir(parents=True)
    (utils / "selectedProjectCard.ts").write_text(
        'return "update TODO/FIXME data";\n// FIXME: real task\n',
        encoding="utf-8",
    )
    (root / "main.py").write_text("# TODO: visible task\n", encoding="utf-8")
    result = ProjectScannerService(ScanConfig(max_depth=8)).scan_project(root)
    paths = {f.file_path for f in result.findings}
    assert "main.py" in paths
    assert not any("selectedProjectCard" in p for p in paths)


def test_next_parser_comment_not_stored_as_finding() -> None:
    line = (
        "# NEXT patterns are already strict (not plain prose); "
        "no extra comment rule."
    )
    findings = parse_task_markers(
        line, file_path="task_parser.py", created_at="2026-01-01T00:00:00+00:00"
    )
    assert findings == []


def test_todo_fixme_unaffected_by_next_rules() -> None:
    content = "# TODO: alpha\n// FIXME: beta\nSuggested next step\n"
    findings = parse_task_markers(
        content, file_path="a.py", created_at="2026-01-01T00:00:00+00:00"
    )
    markers = {f.marker for f in findings}
    assert markers == {"TODO", "FIXME"}


def test_scan_finds_todo_in_python_file(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "module.py").write_text(
        "def run():\n    pass  # TODO: add validation\n",
        encoding="utf-8",
    )

    result = ProjectScannerService(ScanConfig(max_depth=4)).scan_project(root)

    assert result.findings_count == 1
    assert result.findings[0].file_path == "module.py"
    assert result.findings[0].line_number == 2


def test_ignored_folder_not_parsed_for_findings(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("# TODO: visible\n", encoding="utf-8")
    nm = root / "node_modules"
    nm.mkdir()
    (nm / "hidden.js").write_text("// TODO: hidden\n", encoding="utf-8")

    result = ProjectScannerService(ScanConfig(max_depth=4)).scan_project(root)

    assert result.findings_count == 1
    assert result.findings[0].file_path == "main.py"


def test_large_file_skipped_without_findings(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    huge = root / "big.py"
    huge.write_bytes(b"# TODO: should not appear\n" + b"x" * (SCAN_MAX_FILE_SIZE_BYTES + 1))

    result = ProjectScannerService(
        ScanConfig(max_depth=4, max_file_size_bytes=256)
    ).scan_project(root)

    assert result.findings_count == 0
    assert any("large file" in w.lower() for w in result.warnings)


def test_details_output_format() -> None:
    finding = TaskFinding(
        file_path="src/a.py",
        line_number=10,
        marker="BUG",
        text="handle null input",
        severity="medium",
        created_at="2026-01-01T00:00:00+00:00",
    )
    line = format_finding_detail(finding)
    assert "BUG src/a.py:10" in line
    assert "medium" in line
    assert "handle null input" in line


def test_print_scan_summary_includes_findings_by_marker(capsys) -> None:
    findings = [
        TaskFinding("a.py", 1, "TODO", "one", "low", "2026-01-01T00:00:00+00:00"),
        TaskFinding("b.py", 2, "FIXME", "two", "high", "2026-01-01T00:00:00+00:00"),
        TaskFinding("c.py", 3, "TODO", "three", "low", "2026-01-01T00:00:00+00:00"),
    ]
    result = ScanResult(
        project_name="demo",
        project_path="/demo",
        findings=findings,
        duration_seconds=0.01,
    )
    _print_scan_summary(result, details=True)
    captured = capsys.readouterr().out

    assert "findings: 3" in captured
    assert "findings_by_marker:" in captured
    assert "TODO: 2" in captured
    assert "FIXME: 1" in captured
    assert "details:" in captured
    assert "TODO a.py:1" in captured
