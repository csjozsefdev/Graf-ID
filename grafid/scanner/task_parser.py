"""Deterministic TODO/FIXME-style marker detection in file content."""

from __future__ import annotations

import re

from grafid.scanner.marker_quality import (
    in_string_at,
    is_machine_or_internal_marker_text,
    is_noise_finding_text,
    is_noise_marker_line,
)
from grafid.scanner.models import TaskFinding

# TODO/FIXME/BUG/HACK — word-boundary markers (unchanged behavior).
STANDARD_MARKER_RE = re.compile(
    r"\b(TODO|FIXME|BUG|HACK)\b\s*:?\s*"
    r"(.*?)(?=\s+\b(?:TODO|FIXME|NEXT|BUG|HACK)\b|$)",
    re.IGNORECASE,
)

# Explicit next-marker forms only — excludes normal prose ("next step", "next milestone").
NEXT_MARKER_RE = re.compile(
    r"(?:"
    r"^\s*NEXT\s*:"
    r"|(?:^|\s)#(?!#)\s*NEXT\s*:?"
    r"|//\s*NEXT\s*:?"
    r"|<!--\s*NEXT\s*:?"
    r"|-\s+NEXT\s*:?"
    r"|\*\s+NEXT\s*:?"
    r")"
    r"\s*"
    r"(.*)$",
    re.IGNORECASE,
)

MARKERS = ("TODO", "FIXME", "NEXT", "BUG", "HACK")

SEVERITY_BY_MARKER: dict[str, str] = {
    "TODO": "low",
    "NEXT": "low",
    "HACK": "medium",
    "BUG": "medium",
    "FIXME": "high",
}

MAX_FINDING_TEXT_CHARS = 200


def parse_task_markers(
    content: str,
    *,
    file_path: str,
    created_at: str,
) -> list[TaskFinding]:
    """
    Extract task markers line by line from decoded file text.

    Returns deduplicated findings in stable line order.
    """
    findings: list[TaskFinding] = []
    seen: set[tuple[str, int, str, str]] = set()

    for line_number, line in enumerate(content.splitlines(), start=1):
        if is_noise_marker_line(line):
            continue
        for marker, text in _findings_on_line(line):
            normalized = _normalize_finding_text(text)
            if is_noise_finding_text(normalized):
                continue
            if is_machine_or_internal_marker_text(normalized):
                continue
            key = (file_path, line_number, marker, normalized)
            if key in seen:
                continue
            seen.add(key)

            findings.append(
                TaskFinding(
                    file_path=file_path,
                    line_number=line_number,
                    marker=marker,
                    text=normalized,
                    severity=SEVERITY_BY_MARKER[marker],
                    created_at=created_at,
                )
            )

    return findings


def _findings_on_line(line: str) -> list[tuple[str, str]]:
    """Collect marker/text pairs from one line in stable order."""
    matches: list[tuple[int, str, str]] = []

    for match in STANDARD_MARKER_RE.finditer(line):
        start = match.start()
        if in_string_at(line, start):
            continue
        if not _marker_in_comment_context(line, start):
            continue
        matches.append((start, match.group(1).upper(), match.group(2)))

    next_match = NEXT_MARKER_RE.search(line)
    if next_match and not in_string_at(line, next_match.start()):
        # NEXT patterns are already strict (not plain prose); no extra comment rule.
        matches.append((next_match.start(), "NEXT", next_match.group(1)))

    matches.sort(key=lambda item: item[0])
    return [(marker, text) for _, marker, text in matches]


def _marker_in_comment_context(line: str, pos: int) -> bool:
    """
    Accept markers in comments (#, //, /* */) or markdown task lines.

  Reject matches inside normal source code / string literals (handled separately).
    """
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return True
    if stripped.startswith(("- [ ]", "- [x]", "* [ ]")):
        return True
    prefix = line[:pos]
    if "//" in prefix:
        return prefix.rfind("//") >= prefix.rfind('"') and prefix.rfind("//") >= prefix.rfind(
            "'"
        )
    if "/*" in prefix:
        return True
    if "#" in prefix:
        hash_pos = prefix.rfind("#")
        if hash_pos >= 0 and not in_string_at(line, hash_pos):
            return True
    return False


def count_findings_by_marker(findings: list[TaskFinding]) -> dict[str, int]:
    """Group finding counts by marker in deterministic marker order."""
    counts = {marker: 0 for marker in MARKERS}
    for finding in findings:
        counts[finding.marker] = counts.get(finding.marker, 0) + 1
    return {marker: counts[marker] for marker in MARKERS if counts[marker] > 0}


def _normalize_finding_text(raw: str) -> str:
    """Collapse whitespace and cap length for compact CLI output."""
    collapsed = " ".join(raw.strip().split())
    if len(collapsed) <= MAX_FINDING_TEXT_CHARS:
        return collapsed
    return collapsed[: MAX_FINDING_TEXT_CHARS - 3] + "..."
