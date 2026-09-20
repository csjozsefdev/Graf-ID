"""Tests for human-readable resume display formatting."""

from __future__ import annotations

from grafid.resume.human_display import humanize_stored_body


def test_humanize_legacy_session_line() -> None:
    body = "Resume summary for 'backend' (short)\nSession: active (unfinished), id=3\n"
    human = humanize_stored_body(body)
    assert "You have an active session for this project." in human
    assert "id=3" not in human


def test_humanize_legacy_scan_none() -> None:
    body = "Scan snapshot: none (run graf-id scan)\n"
    human = humanize_stored_body(body)
    assert "No scan has been run for this project yet." in human
    assert "graf-id" not in human


def test_humanize_active_session_note() -> None:
    body = (
        "Note: session is still open. Close it with graf-id session close when done.\n"
    )
    human = humanize_stored_body(body)
    assert "Active session in progress" in human
    assert "graf-id" not in human
