"""Deterministic workflow artifact detection — MVP allowlist only."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from grafid.resume.quality import MAX_PREVIEW_CHARS, trim_preview_text
from grafid.utils.safe_path import is_safe_project_path, is_unsafe_symlink

# kind -> sort order within tier (lower = higher priority)
KIND_ORDER: dict[str, int] = {
    "handoff": 0,
    "next": 1,
    "session": 2,
    "exit_note": 3,
    "todo": 4,
    "notes": 5,
    "readme": 6,
    "changelog": 7,
}

# Continuation document priority (lower = higher priority).
FILENAME_PRIORITY: dict[str, int] = {
    "project_continuation.md": 0,
    "handoff.md": 1,
    "project_handoff.md": 1,
    "handover.md": 2,
    "next.md": 3,
    "next_steps.md": 3,
    "session.md": 4,
    "session_notes.md": 4,
    "exit_note.md": 5,
    "todo.md": 6,
    "notes.md": 7,
    "readme.md": 10,
    "review_checklist.md": 11,
    "changelog.md": 12,
}

# MVP allowlist: (filename, kind, tier). No other files are read.
ALLOWED_WORKFLOW_FILES: tuple[tuple[str, str, str], ...] = (
    # Highest priority
    ("PROJECT_CONTINUATION.md", "handoff", "high"),
    ("HANDOFF.md", "handoff", "high"),
    ("handoff.md", "handoff", "high"),
    ("PROJECT_HANDOFF.md", "handoff", "high"),
    ("HANDOVER.md", "handoff", "high"),
    ("handover.md", "handoff", "high"),
    ("NEXT.md", "next", "high"),
    ("NEXT_STEPS.md", "next", "high"),
    ("SESSION.md", "session", "high"),
    ("SESSION_NOTES.md", "session", "high"),
    ("EXIT_NOTE.md", "exit_note", "high"),
    # Medium priority
    ("TODO.md", "todo", "medium"),
    ("NOTES.md", "notes", "medium"),
    ("README.md", "readme", "medium"),
    ("REVIEW_CHECKLIST.md", "notes", "medium"),
    ("CHANGELOG.md", "changelog", "medium"),
)

CONTINUATION_LINK_SOURCE_NAMES = frozenset(
    name.lower()
    for name, _kind, _tier in ALLOWED_WORKFLOW_FILES
    if _kind in {"handoff", "next", "session", "exit_note", "readme", "changelog"}
)

LINK_CHAIN_MAX_DEPTH = 2
LINK_CHAIN_MAX_DOCUMENTS = 10

MAX_READ_BYTES = 12_000
MAX_PREVIEW_LINES = 4
MAX_LINE_CHARS = MAX_PREVIEW_CHARS

_EXTERNAL_LINK_PREFIXES = ("http://", "https://", "//", "mailto:", "ftp://", "file:")

_ROOT_NOTE_PATTERNS = (
    "NOTE.md",
    "NOTES.md",
    "*HANDOFF*.md",
    "*HANDOVER*.md",
    "*CONTINUATION*.md",
    "*TODO*.md",
    "PROJECT_NOTES.md",
)


def _clip_line(text: str) -> str:
    return trim_preview_text(text, MAX_LINE_CHARS)


def _read_bounded_text(path: Path) -> str | None:
    """
    Read at most MAX_READ_BYTES from disk.

    H2: previously `path.read_text(...)[:MAX_READ_BYTES]` fully decoded the
    entire file into memory before truncating — an arbitrarily large file
    dropped in the project root/parent (e.g. a mislabeled multi-GB TODO.md)
    would be read whole. A bounded byte read caps memory use regardless of
    on-disk file size.
    """
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_READ_BYTES)
    except OSError:
        return None
    return raw.decode("utf-8", errors="replace")


_BOILERPLATE_PREVIEW_PHRASES = (
    "read this first",
    "read this if you",
    "see [",
    "see docs/",
    "refer to ",
    "simple guide for",
    "this document",
    "this file",
    "start with ",
    "continuing work?",
    "for acceptance checks",
    "last updated:",
    "opening the repo",
    "onboarding cold",
    "onboarding",
    "tick each item",
    "short pass/fail",
    "time to read:",
    "new here?",
    "plain list of what",
    "full walkthrough",
    "six months from now",
)


def _is_meta_intro_line(text: str) -> bool:
    lower = text.lower().strip()
    if lower.startswith("time to read:") or lower.startswith("new here?"):
        return True
    if lower.startswith("read docs/") or "docs/sources.md" in lower or "docs/guide.md" in lower:
        return True
    return False


def _is_boilerplate_line(text: str) -> bool:
    lower = text.lower().strip()
    if not lower:
        return True
    if re.match(r"^\d+\.?\s*$", lower):
        return True
    if lower.startswith("**") and lower.endswith("**") and len(lower) < 24:
        return True
    if _is_meta_intro_line(text):
        return True
    return any(phrase in lower for phrase in _BOILERPLATE_PREVIEW_PHRASES)


def _is_doc_index_line(text: str) -> bool:
    """Lines that only point at another markdown file are not workflow content."""
    stripped = text.strip()
    if not stripped:
        return True
    lower = stripped.lower()
    if ".md" not in lower:
        return False
    if MARKDOWN_LINK.search(stripped):
        suffix = re.split(r"\s[—\-–]\s+", _plain_text(stripped), maxsplit=1)
        tail = suffix[-1].strip() if suffix else ""
        if not tail or len(tail) < 24 or ".md" in tail.lower():
            return True
    if lower.startswith("[") and ".md" in lower:
        return True
    return False


def _sanitize_workflow_text(text: str | None, *, strip_doc_index_prefix: bool = True) -> str | None:
    """
    strip_doc_index_prefix=False skips the doc-index-line em-dash stripping
    below (used for already-extracted **Next:** text via INLINE_NEXT_RE).
    That stripping is meant for raw scanned lines
    that are *only* a pointer to another doc (e.g. "See [Architecture]
    (ARCHITECTURE.md) — full system design"), where keeping just the tail
    after the dash is the real content. Applied to inline-next text it
    over-fires: a genuine next-step sentence that merely *mentions* a .md
    file — "post-launch — see [CHANGELOG.md](../CHANGELOG.md) for what
    shipped..." — was misclassified as doc-index-only (its post-dash tail
    still contains ".md") and had everything before the dash silently
    discarded, compounding the INLINE_NEXT_RE truncation bug this was
    found alongside.
    """
    if not text:
        return None
    cleaned = _plain_text(text)
    if not cleaned or _is_boilerplate_line(cleaned):
        return None
    if strip_doc_index_prefix and _is_doc_index_line(text):
        parts = re.split(r"\s[—\-–]\s+", cleaned, maxsplit=1)
        if len(parts) == 2 and len(parts[1]) >= 24 and not _is_boilerplate_line(parts[1]):
            cleaned = parts[1]
        else:
            return None
    return _clip_line(cleaned)


NEXT_STEP_PATTERNS = (
    re.compile(r"^next step\s*:\s*(.+)$", re.I),
    re.compile(r"^next\s*:\s*(.+)$", re.I),
)
FOCUS_PATTERNS = (
    re.compile(r"^focus area\s*:\s*(.+)$", re.I),
    re.compile(r"^focus\s*:\s*(.+)$", re.I),
    re.compile(r"^current focus\s*:\s*(.+)$", re.I),
    re.compile(r"^current work\s*:\s*(.+)$", re.I),
    re.compile(r"^in progress\s*:\s*(.+)$", re.I),
    re.compile(r"^working on\s*:\s*(.+)$", re.I),
)

BLOCKER_PATTERNS = (
    re.compile(r"^blockers?\s*:\s*(.+)$", re.I),
    re.compile(r"^blocked on\s*:\s*(.+)$", re.I),
    re.compile(r"^open issue\s*:\s*(.+)$", re.I),
)

MILESTONE_HEADING_RE = re.compile(
    r"^##\s+Milestone\s+(\d+)\s*[—\-:]\s*(.+?)\s*$",
    re.I,
)
WHERE_LEFT_OFF_HEADING_RE = re.compile(r"^##\s+(?:\d+\.\s*)?where we left off\b", re.I)
# Stops at: a sentence-ending period (one followed by whitespace/end-of-string,
# so it doesn't fire on "CHANGELOG.md" or "1.0.0" inside the captured text —
# found truncating "**Next:** post-launch — see [CHANGELOG.md](../CHANGELOG.md)
# for what shipped..." down to just "post-launch —"), or an explicit trailing
# "See <doc>" pointer clause. "See" is deliberately case-SENSITIVE (capital
# only): the doc-pointer convention this is meant to strip is a new sentence
# ("... . See ROADMAP.md."), not the ordinary word "see" occurring naturally
# mid-sentence ("... see issue #42 for details") — case-insensitive matching
# here truncated any "Next:" text containing that common word.
INLINE_NEXT_RE = re.compile(r"(?i:\*\*Next:\*\*)\s*(.+?)(?:\.(?=\s|$)|\s+See\s)")

WORKFLOW_SECTION_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$")
WORKFLOW_SECTION_KEYWORDS = (
    "current focus",
    "current work",
    "in progress",
    "remaining",
    "unfinished",
    "blocker",
    "next step",
    "open issue",
    "polish",
    "refactor",
    "milestone",
)

# H3: the original `\[([^\]]+)\]\(([^)]+)\)` is O(n^2) on adversarial input —
# a line of many `[` with no closing `]` forces `.search()`/`.finditer()`/
# `.sub()` to retry the greedy-then-fail inner match at every one of the ~n
# candidate `[` positions, each costing O(remaining length) since the
# negated-class quantifier has nothing to stop it short of end-of-string.
# Measured (this exact pattern via `.search()`): ~1.0s at 12k chars,
# unusably slow beyond ~100k. Bounding the inner spans (real link labels/
# targets are never anywhere near this long) caps each position's cost to a
# constant, making the whole scan O(n): ~0.07s at 12k, ~5.3s at 1M chars,
# with identical matches on real markdown links.
MARKDOWN_LINK = re.compile(r"\[([^\]]{1,300})\]\(([^)]{1,2000})\)")
# NEW-M5-A (previously mislabeled H3 in commit 095c6516 — see GATE CHECK 5B):
# same quadratic shape as above, in the pointer-line-detection line pattern.
POINTER_LINE = re.compile(
    r"^\s*(see|refer to|read)\b.*\[[^\]]{1,300}\]\([^)]{1,2000}\)", re.I
)
SIMPLE_REF_LINE = re.compile(
    r"^(?:see|refer to|read|remaining work|project continuation)\s*:\s*(\S+\.md)\s*$",
    re.I,
)


@dataclass(frozen=True)
class WorkflowArtifact:
    """A workflow context file found on disk."""

    filename: str
    relative_path: str
    kind: str
    priority_tier: str
    title: str | None
    preview_lines: tuple[str, ...]
    focus_area: str | None
    next_step_line: str | None
    recent_work: str | None = None
    project_state: str | None = None
    handoff_summary: str | None = None
    unfinished_items: tuple[str, ...] = ()
    blocker_items: tuple[str, ...] = ()
    # False for documents found in the parent folder: useful for the local UI, but
    # never exported (an export must not carry content from outside the project).
    in_project_root: bool = True


def workflow_filename_priority(filename: str) -> int:
    """Return continuation priority rank for a workflow filename (lower = higher)."""
    return FILENAME_PRIORITY.get(filename.lower(), 50)


def load_workflow_artifacts(project_path: str) -> tuple[WorkflowArtifact, ...]:
    """Load only MVP allowlisted workflow files (project root + parent folder)."""
    root = Path(project_path).resolve()
    search_roots = _search_roots(root)
    allowlist = {name.lower(): (name, kind, tier) for name, kind, tier in ALLOWED_WORKFLOW_FILES}

    picked: list[Path] = []
    seen: set[str] = set()
    for base in search_roots:
        if not base.is_dir():
            continue
        for filename, kind, tier in ALLOWED_WORKFLOW_FILES:
            path = base / filename
            if not is_safe_project_path(path, base):
                continue
            if not path.is_file():
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            picked.append(path)

    artifacts: list[WorkflowArtifact] = []
    for path in picked:
        parsed = _parse_artifact(path, root, allowlist)
        if parsed is not None:
            artifacts.append(parsed)

    artifacts.extend(_follow_continuation_links(picked, root, allowlist, seen))
    artifacts.extend(_discover_root_pattern_files(root, allowlist, seen))

    artifacts.sort(key=_artifact_sort_key)
    return tuple(artifacts)


def _artifact_matches_modified(
    artifact: WorkflowArtifact, modified_files: tuple[str, ...]
) -> bool:
    if not modified_files:
        return False
    rel = artifact.relative_path.replace("\\", "/").lower()
    name = artifact.filename.lower()
    for raw in modified_files:
        token = raw.replace("\\", "/").lower()
        if token == rel or token.endswith(f"/{name}") or token == name:
            return True
    return False


def primary_handoff(
    artifacts: tuple[WorkflowArtifact, ...],
    *,
    modified_files: tuple[str, ...] = (),
) -> WorkflowArtifact | None:
    handoffs = [artifact for artifact in artifacts if artifact.kind == "handoff"]
    if not handoffs:
        return None
    if modified_files:
        for artifact in handoffs:
            if _artifact_matches_modified(artifact, modified_files):
                return artifact
    return handoffs[0]


def _artifact_sort_key(item: WorkflowArtifact) -> tuple[int, int, int, str]:
    return (
        0 if item.priority_tier == "high" else 1,
        workflow_filename_priority(item.filename),
        KIND_ORDER.get(item.kind, 99),
        item.filename.lower(),
    )


def _follow_continuation_links(
    picked: list[Path],
    project_root: Path,
    allowlist: dict[str, tuple[str, str, str]],
    seen: set[str],
) -> list[WorkflowArtifact]:
    """Follow markdown links from continuation documents up to depth and count limits."""
    extras: list[WorkflowArtifact] = []
    followed_count = 0
    queue: deque[tuple[Path, int]] = deque()

    for path in picked:
        if _is_continuation_link_source(path):
            queue.append((path, 0))

    while queue and followed_count < LINK_CHAIN_MAX_DOCUMENTS:
        source, depth = queue.popleft()
        if depth >= LINK_CHAIN_MAX_DEPTH:
            continue

        raw = _read_bounded_text(source)
        if raw is None:
            continue

        for target_raw in _extract_link_targets(raw):
            target = _resolve_local_markdown_path(target_raw, source.parent, project_root)
            if target is None:
                continue
            key = str(target)
            if key in seen:
                continue
            seen.add(key)
            followed_count += 1
            if followed_count > LINK_CHAIN_MAX_DOCUMENTS:
                break

            parsed = _parse_artifact(target, project_root, allowlist, allow_linked=True)
            if parsed is not None:
                extras.append(parsed)
            queue.append((target, depth + 1))

    return extras


def _is_continuation_link_source(path: Path) -> bool:
    return path.name.lower() in CONTINUATION_LINK_SOURCE_NAMES


def _extract_link_targets(text: str) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    lines = text.splitlines()

    def add(raw: str) -> None:
        cleaned = raw.strip().strip("<>").strip()
        if not cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        targets.append(cleaned)

    for _label, target_raw in MARKDOWN_LINK.findall(text):
        add(target_raw)

    for index, line in enumerate(lines):
        stripped = line.strip()
        match = SIMPLE_REF_LINE.match(stripped)
        if match:
            add(match.group(1))
            continue
        if stripped.lower().startswith("see:"):
            candidate = stripped[4:].strip()
            if candidate.lower().endswith(".md"):
                add(candidate)
            continue
        if re.match(r"^(?:remaining work|project continuation)\s*:?\s*$", stripped, re.I):
            if index + 1 < len(lines):
                nxt = lines[index + 1].strip()
                if nxt.lower().endswith(".md") and "://" not in nxt:
                    add(nxt)

    return targets


def _resolve_local_markdown_path(
    target_raw: str,
    source_dir: Path,
    project_root: Path,
) -> Path | None:
    token = target_raw.strip().strip("<>").strip()
    if not token:
        return None

    lower = token.lower()
    if lower.startswith(_EXTERNAL_LINK_PREFIXES):
        return None
    if "://" in token:
        return None
    if token.startswith("#"):
        return None
    if not lower.endswith(".md"):
        return None

    joined = source_dir / token
    if is_unsafe_symlink(joined):
        # Not followed even when the resolved target would stay in-root —
        # symlinks are rejected outright, by default.
        return None
    candidate = joined.resolve()
    if not _is_safe_project_path(candidate, project_root):
        return None
    if not candidate.is_file():
        return None
    return candidate


def _is_safe_project_path(path: Path, project_root: Path) -> bool:
    return is_safe_project_path(path, project_root)


def _infer_artifact_meta(filename: str) -> tuple[str, str, str]:
    lower = filename.lower()
    if not lower.endswith(".md"):
        return (filename, "notes", "medium")

    if "continuation" in lower or "handoff" in lower or "handover" in lower:
        return (filename, "handoff", "high")
    if lower.startswith("next") or "next_steps" in lower:
        return (filename, "next", "high")
    if "session" in lower:
        return (filename, "session", "high")
    if "exit" in lower and "note" in lower:
        return (filename, "exit_note", "high")
    if "todo" in lower:
        return (filename, "todo", "medium")
    if lower == "readme.md":
        return (filename, "readme", "medium")
    if "changelog" in lower:
        return (filename, "changelog", "medium")
    if "note" in lower:
        return (filename, "notes", "medium")
    return (filename, "notes", "medium")


def _discover_root_pattern_files(
    root: Path,
    allowlist: dict[str, tuple[str, str, str]],
    seen: set[str],
) -> list[WorkflowArtifact]:
    """Discover extra note/handoff markdown files in the project root only."""
    extras: list[WorkflowArtifact] = []
    if not root.is_dir():
        return extras
    for pattern in _ROOT_NOTE_PATTERNS:
        for path in sorted(root.glob(pattern)):
            if not is_safe_project_path(path, root):
                continue
            if not path.is_file():
                continue
            key = str(path.resolve())
            if key in seen or path.name.lower() in allowlist:
                continue
            seen.add(key)
            kind = "notes"
            tier = "medium"
            lower = path.name.lower()
            if "handoff" in lower or "handover" in lower or "continuation" in lower:
                kind = "handoff"
                tier = "high"
            elif "todo" in lower:
                kind = "todo"
            dynamic_allowlist = {
                path.name.lower(): (path.name, kind, tier),
            }
            parsed = _parse_artifact(path, root, dynamic_allowlist)
            if parsed is not None:
                extras.append(parsed)
    return extras


def _search_roots(root: Path) -> list[Path]:
    roots = [root]
    parent = root.parent
    if parent != root and parent.is_dir():
        roots.append(parent)
    return roots


def _parse_artifact(
    path: Path,
    project_root: Path,
    allowlist: dict[str, tuple[str, str, str]],
    *,
    allow_linked: bool = False,
) -> WorkflowArtifact | None:
    meta = allowlist.get(path.name.lower())
    if meta is None and allow_linked:
        meta = _infer_artifact_meta(path.name)
    if meta is None:
        return None
    if is_unsafe_symlink(path):
        # Final choke point: never read through a symlink/reparse point,
        # regardless of which discovery path produced this candidate.
        return None
    _canonical_name, kind, tier = meta

    raw = _read_bounded_text(path)
    if raw is None:
        return None

    lines = [line.rstrip() for line in raw.splitlines()]
    title = _extract_title(lines)
    focus_area = _sanitize_workflow_text(_extract_labeled(lines, FOCUS_PATTERNS))
    next_step = _sanitize_workflow_text(_extract_labeled(lines, NEXT_STEP_PATTERNS))
    raw_state = _extract_project_state_sentence(lines) or _extract_where_left_off_section(lines)
    project_state: str | None = None
    if raw_state:
        state_body, inline_next = _split_inline_next(raw_state)
        project_state = _sanitize_workflow_text(state_body or raw_state)
        if inline_next and not next_step:
            next_step = inline_next
    if not next_step:
        next_step = _sanitize_workflow_text(
            _extract_inline_next(lines), strip_doc_index_prefix=False
        )
    handoff_summary = _extract_handoff_blockquote(lines)
    if not next_step:
        next_step = _sanitize_workflow_text(_extract_first_not_done_item(lines))
    if not next_step:
        next_step = _sanitize_workflow_text(_extract_recommended_work_row(lines))
    preview = _meaningful_preview(lines, title)
    recent_work = _extract_latest_milestone(lines) if kind == "readme" else None
    if not recent_work:
        recent_work = _sanitize_workflow_text(_extract_section_lead(lines))
    unfinished = tuple(
        item
        for item in (_sanitize_workflow_text(x) for x in _extract_not_done_items(lines)[:4])
        if item
    )
    blockers = tuple(
        item
        for item in (_sanitize_workflow_text(x) for x in _extract_labeled_all(lines, BLOCKER_PATTERNS)[:2])
        if item
    )

    if (
        not preview
        and not title
        and not focus_area
        and not next_step
        and not recent_work
        and not project_state
        and not handoff_summary
        and not unfinished
    ):
        return None

    in_root = True
    try:
        rel = path.relative_to(project_root).as_posix()
    except ValueError:
        rel = path.name
        in_root = False

    return WorkflowArtifact(
        filename=path.name,
        relative_path=rel,
        kind=kind,
        priority_tier=tier,
        title=title,
        preview_lines=preview,
        focus_area=focus_area,
        next_step_line=next_step,
        recent_work=recent_work,
        project_state=project_state,
        handoff_summary=handoff_summary,
        unfinished_items=unfinished,
        blocker_items=blockers,
        in_project_root=in_root,
    )


def _extract_title(lines: list[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            return _clip_line(stripped.lstrip("#").strip())
    return None


def _extract_labeled(lines: list[str], patterns: tuple[re.Pattern[str], ...]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        for pattern in patterns:
            match = pattern.match(stripped)
            if match:
                return match.group(1).strip()
    return None


def _extract_project_state_sentence(lines: list[str]) -> str | None:
    in_section = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^##\s+1\.\s+Project state", stripped, re.I):
            in_section = True
            continue
        if in_section and re.match(r"^##\s+", stripped):
            break
        if in_section and stripped:
            text = _plain_text(stripped.strip("* "))
            return _sanitize_workflow_text(text)
    return None


def _extract_where_left_off_section(lines: list[str]) -> str | None:
    in_section = False
    for line in lines:
        stripped = line.strip()
        if WHERE_LEFT_OFF_HEADING_RE.match(stripped):
            in_section = True
            continue
        if in_section and WORKFLOW_SECTION_HEADING_RE.match(stripped):
            break
        if not in_section or not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(">"):
            continue
        plain = _plain_text(stripped.strip("*_ "))
        plain, _ = _split_inline_next(plain)
        if not plain or _is_boilerplate_line(plain) or _is_meta_intro_line(plain):
            continue
        if _is_doc_index_line(stripped) and len(plain) < 80:
            continue
        return plain
    return None


def _strip_trailing_doc_pointer(text: str) -> str:
    # Case-SENSITIVE "See" — same reasoning as INLINE_NEXT_RE above: only the
    # capitalized doc-pointer convention should be stripped, not the ordinary
    # word "see" occurring naturally within the text being kept.
    return re.sub(r"\s+See\s+.+$", "", text).strip().rstrip(".")


def _split_inline_next(text: str) -> tuple[str, str | None]:
    match = INLINE_NEXT_RE.search(text)
    if not match:
        return _strip_trailing_doc_pointer(text), None
    state = _strip_trailing_doc_pointer(text[: match.start()].strip().rstrip("."))
    nxt = match.group(1).strip().rstrip(".")
    return state, nxt or None


def _extract_inline_next(lines: list[str]) -> str | None:
    for line in lines:
        match = INLINE_NEXT_RE.search(line)
        if match:
            return match.group(1).strip().rstrip(".")
    return None


def _extract_handoff_blockquote(lines: list[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(">"):
            continue
        text = _plain_text(stripped.lstrip(">").strip())
        if text and len(text) >= 40:
            return _sanitize_workflow_text(text)
    return None


def _extract_first_not_done_item(lines: list[str]) -> str | None:
    items = _extract_not_done_items(lines)
    return items[0] if items else None


def _extract_not_done_items(lines: list[str]) -> list[str]:
    in_section = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^##\s+3\.\s+What is NOT done", stripped, re.I):
            in_section = True
            continue
        if in_section and re.match(r"^##\s+", stripped):
            break
        if not in_section:
            continue
        match = re.match(r"^\d+\.\s+\*\*(.+?)\*\*\s*[—\-–]\s*(.+)$", stripped)
        if match:
            detail = _plain_text(match.group(2))
            label = match.group(1).strip()
            if detail.lower().endswith(".md") or detail.lower().endswith(".md."):
                out.append(label)
            else:
                out.append(f"{label} — {detail}".rstrip("."))
            continue
        match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if match:
            text = _plain_text(match.group(1))
            if text:
                out.append(text)
    return out


def _extract_recommended_work_row(lines: list[str]) -> str | None:
    in_section = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^##\s+5\.\s+Recommended work order", stripped, re.I):
            in_section = True
            continue
        if in_section and re.match(r"^##\s+", stripped):
            break
        if not in_section or not stripped.startswith("|"):
            continue
        if "---" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() in {"order", "#"}:
            continue
        if cells[0] != "1":
            continue
        task = _plain_text(cells[1].strip("` "))
        outcome = _plain_text(cells[2])
        if task:
            return f"{task} — done when {outcome}" if outcome else task
    return None


def _extract_labeled_all(
    lines: list[str], patterns: tuple[re.Pattern[str], ...]
) -> list[str]:
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        for pattern in patterns:
            match = pattern.match(stripped)
            if match:
                text = _clip_line(match.group(1).strip())
                if text:
                    out.append(text)
    return out


def _extract_latest_milestone(lines: list[str]) -> str | None:
    candidates: list[tuple[int, str]] = []
    for line in lines:
        match = MILESTONE_HEADING_RE.match(line.strip())
        if match:
            candidates.append((int(match.group(1)), _clip_line(match.group(2).strip())))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def _extract_section_lead(lines: list[str]) -> str | None:
    current_heading: str | None = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        heading_match = WORKFLOW_SECTION_HEADING_RE.match(stripped)
        if heading_match:
            current_heading = heading_match.group(1).strip()
            continue
        if stripped.startswith(("-", "*")) and current_heading:
            if not _heading_is_workflow(current_heading):
                continue
            bullet = stripped.lstrip("-* ").strip()
            if bullet:
                return _clip_line(bullet)
    return None


def _heading_is_workflow(heading: str) -> bool:
    lower = heading.lower()
    return any(keyword in lower for keyword in WORKFLOW_SECTION_KEYWORDS)


def _meaningful_preview(lines: list[str], title: str | None) -> tuple[str, ...]:
    out: list[str] = []
    title_lower = title.lower() if title else None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(("-", "*", ">")):
            stripped = stripped.lstrip("-*> ").strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if title_lower and lower == title_lower:
            continue
        if any(p.match(stripped) for p in (*NEXT_STEP_PATTERNS, *FOCUS_PATTERNS)):
            continue
        if lower.startswith("```"):
            continue
        if POINTER_LINE.match(stripped):
            continue
        if _markdown_link_density(stripped) > 0.5:
            continue
        cleaned = _plain_text(stripped)
        if not cleaned:
            continue
        if re.match(r"^\d+\.?\s*$", cleaned):
            continue
        if _is_boilerplate_line(cleaned):
            continue
        if _is_meta_intro_line(cleaned):
            continue
        if _is_doc_index_line(stripped):
            continue
        out.append(_clip_line(cleaned))
        if len(out) >= MAX_PREVIEW_LINES:
            break
    return tuple(out)


def _plain_text(line: str) -> str:
    text = MARKDOWN_LINK.sub(r"\1", line)
    text = re.sub(r"[*`#>|]", "", text)
    return " ".join(text.split()).strip()


def _markdown_link_density(line: str) -> float:
    if not line.strip():
        return 0.0
    link_chars = sum(len(m.group(0)) for m in MARKDOWN_LINK.finditer(line))
    return link_chars / max(len(line), 1)
