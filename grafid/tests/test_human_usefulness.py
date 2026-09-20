"""Tests for marker human-usefulness scoring and filtering."""

from __future__ import annotations

from grafid.resume.summary_composition import CompositionInput, compose_workflow_summary
from grafid.scanner.marker_quality import (
    assess_marker_text_usefulness,
    extract_marker_text_from_summary_line,
    format_markers_for_summary,
    workflow_marker_lines,
)
from grafid.scanner.models import TaskFinding
from grafid.scanner.task_parser import parse_task_markers


def test_parser_internal_next_comment_rejected() -> None:
    line = (
        "# NEXT patterns are already strict (not plain prose); "
        "no extra comment rule."
    )
    findings = parse_task_markers(line, file_path="task_parser.py", created_at="2026-01-01T00:00:00+00:00")
    assert findings == []
    from grafid.scanner.marker_quality import is_machine_or_internal_marker_text

    assert is_machine_or_internal_marker_text(
        "patterns are already strict (not plain prose) no extra comment rule"
    )


def test_compressed_machine_token_low_confidence() -> None:
    junk = "patternsarealreadystrict(notplainprose)noextracommentrule"
    assert assess_marker_text_usefulness(junk) == "low"


def test_readable_workflow_marker_strong() -> None:
    assert assess_marker_text_usefulness("fix refresh context duplication") == "strong"
    assert assess_marker_text_usefulness("improve scanner filtering") in ("strong", "possible")


def test_format_markers_skips_low_confidence() -> None:
    findings = [
        TaskFinding(
            "task_parser.py",
            103,
            "NEXT",
            "patterns are already strict (not plain prose) no extra comment rule",
            "low",
            "2026-01-01T00:00:00+00:00",
        ),
        TaskFinding(
            "panel.ts",
            12,
            "TODO",
            "fix refresh context duplication",
            "low",
            "2026-01-01T00:00:00+00:00",
        ),
    ]
    lines = format_markers_for_summary(findings, limit=5)
    assert len(lines) == 1
    assert "fix refresh" in lines[0]
    assert "patterns are already" not in " ".join(lines)


def test_only_noise_markers_get_honest_resume_line() -> None:
    noise_line = (
        "Open markers in grafid/scanner/task_parser.py — NEXT: "
        "patterns are already strict (not plain prose) no extra comment rule"
    )
    result = compose_workflow_summary(
        CompositionInput(
            project_name="Graf-Id",
            task_markers=(noise_line,),
            has_scan=True,
            open_task_count=1,
        )
    )
    primary = "\n".join(result.primary_lines)
    assert "patterns are already" not in primary
    assert "No strong workflow marker found yet" in primary
    assert result.suggested_next_step is None


def test_workflow_marker_lines_filters_summary_rows() -> None:
    good = "Open markers in a.py — TODO: fix login flow"
    bad = (
        "Open markers in b.py — NEXT: patternsarealreadystrict"
        "(notplainprose)noextracommentrule"
    )
    kept = workflow_marker_lines((bad, good))
    assert kept == (good,)
    assert extract_marker_text_from_summary_line(good) == "fix login flow"
