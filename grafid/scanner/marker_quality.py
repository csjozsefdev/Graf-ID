"""Filter and format scan task markers for user-facing summaries."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Literal

from grafid.scanner.models import TaskFinding

MarkerUsefulness = Literal["strong", "possible", "low"]

# Files that only describe TODO/FIXME UI behavior — not real project tasks.
SKIP_MARKER_SCAN_BASENAMES: frozenset[str] = frozenset(
    {
        "selectedProjectCard.ts",
        "taskMarkerLabel.ts",
    }
)

# Substrings that indicate UI/meta copy, not actionable tasks.
_NOISE_TEXT_RE = re.compile(
    r"(?i)"
    r"(todo/fixme\s+data"
    r"|markers?\s+in\s+the\s+latest\s+scan"
    r"|marker\$\{"
    r"|use\s+refresh\s+context\s+to\s+scan"
    r"|open\s+todo/f(?:IXME)?\s+marker)"
)

# Edge / trailing junk from string literals / template fragments (not interior spaces).
_EDGE_JUNK_RE = re.compile(r'''^['"`;]+|['"`;]+$''')
_TRAILING_COMMENT_JUNK_RE = re.compile(r"/\s*(?:FIXME|TODO)\b.*$", re.IGNORECASE)

# Parser/config/validation copy — not developer workflow notes.
_INTERNAL_TECHNICAL_RE = re.compile(
    r"(?i)"
    r"(patterns?\s+are\s+already\s+strict"
    r"|not\s+plain\s+prose"
    r"|no\s+extra\s+comment\s+rule"
    r"|word[- ]?boundary"
    r"|\bregex\b"
    r"|task[_-]?parser"
    r"|marker[_-]?quality"
    r"|validation\s+schema"
    r"|is_noise_"
    r"|parse_task_markers?"
    r"|marker_in_comment"
    r"|low_confidence"
    r"|format_markers_for_summary)"
)

def should_skip_marker_scan_file(relative_path: str) -> bool:
    """Skip files that only mention TODO/FIXME in UI helper copy."""
    name = Path(relative_path.replace("\\", "/")).name
    return name in SKIP_MARKER_SCAN_BASENAMES


def in_string_at(line: str, pos: int) -> bool:
    """True when pos is inside a single-, double-, or backtick-quoted span."""
    in_single = in_double = in_backtick = False
    escape = False
    for ch in line[:pos]:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == "'" and not in_double and not in_backtick:
            in_single = not in_single
        elif ch == '"' and not in_single and not in_backtick:
            in_double = not in_double
        elif ch == "`" and not in_single and not in_double:
            in_backtick = not in_backtick
    return in_single or in_double or in_backtick


def is_noise_marker_line(line: str) -> bool:
    """Reject whole lines that are clearly UI/template/meta, not comments."""
    if "${" in line:
        return True
    return bool(_NOISE_TEXT_RE.search(line))


def is_noise_finding_text(text: str) -> bool:
    """Reject captured marker text that is not a real task description."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) < 3:
        return True
    if _NOISE_TEXT_RE.search(cleaned):
        return True
    if cleaned.startswith("/") and "FIXME" in cleaned.upper():
        return True
    if re.search(r'''^['"`;]+|['"`;]+$''', cleaned):
        return True
    return False


def is_machine_or_internal_marker_text(text: str) -> bool:
    """Reject parser/config/machine fragments at scan time (keep short real TODOs)."""
    cleaned = clean_finding_text(text) if text else ""
    if not cleaned:
        return True
    if _INTERNAL_TECHNICAL_RE.search(cleaned):
        return True
    compressed = re.sub(r"\s+", "", cleaned)
    spaces = cleaned.count(" ")
    if spaces == 0 and len(compressed) > 32:
        return True
    symbols = sum(1 for c in cleaned if not c.isalnum() and not c.isspace())
    if cleaned and symbols / len(cleaned) > 0.32:
        return True
    tokens = re.findall(r"\S+", cleaned)
    if sum(1 for t in tokens if _camel_case_heavy(t)) >= 2:
        return True
    return False


def assess_marker_text_usefulness(text: str) -> MarkerUsefulness:
    """
    Deterministic human-usefulness score for marker body text.

    strong — readable workflow note
    possible — short but plausible task text
    low — machine-like / parser noise (suppress from resume)
    """
    cleaned = clean_finding_text(text) if text else ""
    if not cleaned or len(cleaned) < 3:
        return "low"
    if _NOISE_TEXT_RE.search(cleaned) or _INTERNAL_TECHNICAL_RE.search(cleaned):
        return "low"

    score = 0
    words = re.findall(r"[A-Za-z]{2,}", cleaned)
    word_count = len(words)
    spaces = cleaned.count(" ")
    letters = [c for c in cleaned if c.isalpha()]
    compressed = re.sub(r"\s+", "", cleaned)

    if spaces >= 2:
        score += 2
    elif spaces == 1:
        score += 1
    elif spaces == 0 and len(compressed) > 32:
        return "low"

    if word_count >= 4:
        score += 2
    elif word_count >= 2:
        score += 1
    elif word_count == 0:
        return "low"

    if len(compressed) > 55 and spaces == 0:
        return "low"

    symbols = sum(1 for c in cleaned if not c.isalnum() and not c.isspace())
    if cleaned:
        sym_ratio = symbols / len(cleaned)
        if sym_ratio > 0.28:
            score -= 3
        elif sym_ratio > 0.18:
            score -= 1

    if cleaned.count("(") + cleaned.count(")") >= 4 and word_count < 5:
        score -= 2

    tokens = re.findall(r"\S+", cleaned)
    long_tokens = [t for t in tokens if len(t) > 18]
    if long_tokens and spaces == 0:
        score -= 2
    camel_heavy = sum(1 for t in tokens if _camel_case_heavy(t))
    if camel_heavy >= 2:
        score -= 2
    elif camel_heavy == 1 and word_count <= 2:
        score -= 1

    if letters:
        vowel_ratio = sum(1 for c in letters if c.lower() in "aeiou") / len(letters)
        if vowel_ratio < 0.17:
            score -= 2
        elif vowel_ratio < 0.22:
            score -= 1

    if re.search(
        r"(?i)\b(fix|improve|review|add|remove|update|clean|refactor|wire|implement|"
        r"continue|polish|address|resolve|duplicate|noisy|filter)\b",
        cleaned,
    ):
        score += 1

    if score >= 3:
        return "strong"
    if score >= 1:
        return "possible"
    return "low"


def _camel_case_heavy(token: str) -> bool:
    """True when a token looks like compressed camelCase / identifiers."""
    if len(token) < 14:
        return False
    transitions = sum(
        1 for i in range(1, len(token)) if token[i].isupper() and token[i - 1].islower()
    )
    if transitions >= 2:
        return True
    if token.islower() and len(token) > 22 and " " not in token:
        return True
    return False


def is_workflow_useful_marker_text(text: str) -> bool:
    """True when marker text is strong or possible workflow language."""
    return assess_marker_text_usefulness(text) != "low"


def extract_marker_text_from_summary_line(line: str) -> str | None:
    """Pull marker body text from a grouped summary line, if present."""
    if " — " not in line:
        return None
    _, tail = line.split(" — ", 1)
    tail = tail.strip()
    for prefix in ("TODO:", "FIXME:", "NEXT:", "BUG:", "HACK:"):
        if prefix in tail.upper():
            idx = tail.upper().find(prefix)
            return tail[idx + len(prefix) :].split(";", 1)[0].strip()
    return tail.split(";", 1)[0].strip() or None


def workflow_marker_lines(lines: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Keep only summary lines whose marker bodies pass usefulness checks."""
    kept: list[str] = []
    for line in lines:
        body = extract_marker_text_from_summary_line(line)
        if body is None:
            if is_workflow_useful_marker_text(line):
                kept.append(line)
            continue
        if is_workflow_useful_marker_text(body):
            kept.append(line)
    return tuple(kept)


def clean_finding_text(raw: str) -> str:
    """Strip quotes, semicolons, and trailing template junk."""
    text = " ".join(raw.strip().split())
    text = _EDGE_JUNK_RE.sub("", text).strip()
    text = _TRAILING_COMMENT_JUNK_RE.sub("", text).strip()
    return text[:160]


def format_markers_for_summary(
    findings: list[TaskFinding],
    *,
    limit: int = 5,
    low_confidence: bool = False,
) -> tuple[str, ...]:
    """Grouped, readable lines for resume/dashboard (not raw scan dumps)."""
    by_file: dict[str, list[tuple[str, str, MarkerUsefulness]]] = defaultdict(list)
    for finding in findings:
        if is_noise_finding_text(finding.text):
            continue
        text = clean_finding_text(finding.text)
        if not text:
            continue
        usefulness = assess_marker_text_usefulness(text)
        if usefulness == "low":
            continue
        if low_confidence and usefulness == "strong":
            continue
        by_file[finding.file_path].append((finding.marker, text, usefulness))

    if not by_file:
        return ()

    prefix = "Potential markers" if low_confidence else "Open markers"
    lines: list[str] = []
    for file_path in sorted(by_file.keys()):
        items = sorted(
            by_file[file_path],
            key=lambda item: (0 if item[2] == "strong" else 1, item[1].lower()),
        )[:3]
        parts = [f"{marker}: {text}" for marker, text, _ in items]
        lines.append(f"{prefix} in {file_path} — " + "; ".join(parts))
        if len(lines) >= limit:
            break
    return tuple(lines)

