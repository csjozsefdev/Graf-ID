"""Human-readable wording for resume summaries (deterministic, no invented context)."""

from __future__ import annotations

import re

TECHNICAL_HEADER_PATTERNS = (
    re.compile(r"^Resume summary for .+$", re.IGNORECASE),
    re.compile(r"^Startup summary for .+$", re.IGNORECASE),
    re.compile(r"^Where you left off \(deterministic.+$", re.IGNORECASE),
    re.compile(r"^Continuity from your last stored session.+$", re.IGNORECASE),
)

TECHNICAL_LINE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"^Session: active \(unfinished\), id=\d+$", re.IGNORECASE),
        "You have an active session for this project.",
    ),
    (
        re.compile(r"^Session: last ended, id=\d+$", re.IGNORECASE),
        "Your last session has ended.",
    ),
    (
        re.compile(r"^Session: none recorded$", re.IGNORECASE),
        "No work session has been recorded yet.",
    ),
    (
        re.compile(r"^Scan snapshot: none \(run graf-id scan\)$", re.IGNORECASE),
        "No scan has been run for this project yet.",
    ),
    (
        re.compile(
            r"^Scan snapshot: id=\d+, scanned_at=.+$",
            re.IGNORECASE,
        ),
        "A project scan is on file.",
    ),
    (
        re.compile(r"^Project path: .+$", re.IGNORECASE),
        "",
    ),
    (
        re.compile(
            r"^Note: session is still open\. Close it with graf-id session close when done\.$",
            re.IGNORECASE,
        ),
        "Active session in progress. End the session with an Exit Note when you finish.",
    ),
    (
        re.compile(
            r"^No session notes, scan snapshot, or findings stored yet\.$",
            re.IGNORECASE,
        ),
        "No session notes or scan data stored yet.",
    ),
    (
        re.compile(
            r"^Run: graf-id scan <project>, then graf-id session start/end\.$",
            re.IGNORECASE,
        ),
        "Add a project scan and work session to capture where you stopped.",
    ),
)


def humanize_line(line: str) -> str | None:
    """Rewrite one stored summary line for display; return None to drop it."""
    stripped = line.strip()
    if not stripped:
        return ""
    for pattern, replacement in TECHNICAL_LINE_REPLACEMENTS:
        if pattern.match(stripped):
            return replacement or None
    return stripped


def humanize_stored_body(body: str) -> str:
    """Rephrase legacy or technical resume bodies for the dashboard."""
    if not body or not body.strip():
        return body

    out: list[str] = []
    skip_headers = True
    for raw in body.splitlines():
        stripped = raw.strip()
        if skip_headers and stripped:
            if any(p.match(stripped) for p in TECHNICAL_HEADER_PATTERNS):
                if not out:
                    out.append("Where you left off")
                continue
            skip_headers = False

        rewritten = humanize_line(raw)
        if rewritten is None:
            continue
        if rewritten == "" and (not out or out[-1] == ""):
            continue
        out.append(rewritten)

    cleaned = "\n".join(out).strip()
    return (cleaned + "\n") if cleaned else body
