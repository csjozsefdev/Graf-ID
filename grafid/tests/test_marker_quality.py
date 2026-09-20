"""Tests for scan marker filtering and summary formatting."""

from __future__ import annotations

from grafid.scanner.marker_quality import (
    format_markers_for_summary,
    is_noise_finding_text,
)
from grafid.scanner.models import TaskFinding


def test_noise_ui_fragments_rejected() -> None:
    assert is_noise_finding_text("/FIXME data.")
    assert is_noise_finding_text("markers in the latest scan.")


def test_format_markers_groups_by_file() -> None:
    findings = [
        TaskFinding("a.py", 1, "TODO", "fix login", "low", "2026-01-01T00:00:00+00:00"),
        TaskFinding("a.py", 9, "FIXME", "cache bug", "high", "2026-01-01T00:00:00+00:00"),
        TaskFinding("b.ts", 2, "TODO", "wire panel", "low", "2026-01-01T00:00:00+00:00"),
    ]
    lines = format_markers_for_summary(findings, limit=5)
    assert len(lines) == 2
    assert "a.py" in lines[0]
    assert "/FIXME data" not in " ".join(lines)
