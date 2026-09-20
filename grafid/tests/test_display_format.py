"""Tests for deterministic display formatting helpers."""

from __future__ import annotations

from grafid.resume.display_format import (
    build_scan_summary_preview,
    format_display_timestamp,
    format_duration_label,
    session_duration_seconds,
)


def test_format_display_timestamp() -> None:
    assert format_display_timestamp("2026-06-07T21:14:33+00:00") == "2026-06-07 21:14:33"
    assert format_display_timestamp(None) is None


def test_format_duration_label() -> None:
    assert format_duration_label(45) is None
    assert format_duration_label(120) == "2 min"
    assert format_duration_label(9780) == "2h 43m"
    assert format_duration_label(7200) == "2h"


def test_session_duration_seconds() -> None:
    seconds = session_duration_seconds(
        "2026-06-07T18:31:00+00:00",
        "2026-06-07T21:14:00+00:00",
    )
    assert seconds == 9780.0


def test_build_scan_summary_preview() -> None:
    assert (
        build_scan_summary_preview(
            scanned_files_count=12,
            findings_count=3,
            git_branch="main",
            git_dirty=True,
        )
        == "Scanned 12 files, 3 findings, main (dirty)"
    )
