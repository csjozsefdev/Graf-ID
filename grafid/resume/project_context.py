"""ProjectContext — backend/domain source of truth for Project Snapshot and exports.

One deterministic, UI-independent description of "where a project stands",
built from the stable local sources only (session fields, workflow documents,
git snapshot, project notes). The dashboard Snapshot card and every export
(JSON / Markdown / TXT / GrafiTalk handoff) are rendered FROM this object;
nothing downstream re-parses UI text such as ``mvp_sections``.

Deliberately not used as sources, because they read as noise on real projects:
scanner code-marker text, README prose, and sentence fragments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from grafid.utils.text import dedupe
from grafid.resume.quality import normalize_note
from grafid.resume.summary_composition import _NO_STRONG_MARKER_MESSAGE, CompositionResult
from grafid.resume.workflow_artifacts import WorkflowArtifact, primary_handoff
from grafid.resume.workflow_state import extract_workflow_state
from grafid.scanner.ignore import is_ignored_relative_path

MAX_LIST_ITEMS = 5
MAX_ITEM_CHARS = 200
MAX_FILES = 20

_ELLIPSIS = "…"


# --------------------------------------------------------------------------- text


def clip(text: str, limit: int = MAX_ITEM_CHARS) -> str:
    """Collapse whitespace; when over ``limit`` cut on a word boundary with an ellipsis."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    segment = collapsed[: limit - 1]
    space = segment.rfind(" ")
    if space > limit * 0.5:
        segment = segment[:space]
    return segment.rstrip(" ,;:-–—(") + _ELLIPSIS


# A sentence ends at . ! ? followed by WHITESPACE and then something that starts
# a new sentence. "v1.0.0", "e.g.foo", "a.b" contain no whitespace after the dot,
# so they can never be split ("v1.0.0 is..." must not become "v1").
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[À-ɏ])")
_LEADING_BULLET = re.compile(r"^[\s\-*•>#]+")


def first_sentence(text: str | None, limit: int = MAX_ITEM_CHARS) -> str | None:
    """First sentence of the first non-empty line, clipped — never split inside tokens."""
    if not text:
        return None
    for raw in text.splitlines():
        line = _LEADING_BULLET.sub("", raw).strip()
        if not line:
            continue
        sentence = _SENTENCE_BOUNDARY.split(line, maxsplit=1)[0].strip()
        return clip(sentence, limit) or None
    return None


def _dedupe_clipped(items: list[str], limit: int = MAX_LIST_ITEMS) -> tuple[str, ...]:
    return tuple(dedupe(items, limit=limit, clean=clip))


# ----------------------------------------------------------------- commit subjects

_CONVENTIONAL = re.compile(
    r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^)]*)\))?!?:\s*(?P<rest>\S.*)$"
)
_FIX_TYPES = frozenset({"fix", "bugfix", "hotfix"})
_IMPROVE_TYPES = frozenset({"feat", "feature", "perf", "refactor", "improve", "enhance"})
_IGNORED_TYPES = frozenset(
    {"chore", "docs", "doc", "test", "tests", "ci", "build", "style", "revert", "wip", "merge"}
)
_FIX_VERBS = frozenset({"fix", "fixed", "fixes", "resolve", "resolved", "repair", "correct"})
_IMPROVE_VERBS = frozenset(
    {
        "add", "added", "implement", "introduce", "improve", "enhance", "polish",
        "support", "refactor", "harden", "optimize", "extend",
    }
)


def classify_commit_subject(subject: str | None) -> tuple[str | None, str | None]:
    """
    Return (kind, display text) with kind in {"fix", "improvement"}, or (None, None).

    Only two shapes are trusted: a conventional-commit prefix ("fix:", "feat(x):")
    or an imperative first word ("Fix ...", "Add ..."). Free-text matching
    anywhere in the subject is NOT used, so "docs: explain how to fix X" is ignored.
    """
    if not subject:
        return None, None
    text = " ".join(subject.split())
    if len(text) < 8 or text.lower().startswith("merge"):
        return None, None

    match = _CONVENTIONAL.match(text)
    if match:
        commit_type = match.group("type").lower()
        rest = match.group("rest").strip()
        if commit_type in _IGNORED_TYPES:
            return None, None
        kind = (
            "fix" if commit_type in _FIX_TYPES
            else "improvement" if commit_type in _IMPROVE_TYPES
            else None
        )
        if kind is None:
            return None, None
        return kind, clip(rest[:1].upper() + rest[1:])

    first_word = text.split(" ", 1)[0].lower().rstrip(":")
    if first_word in _FIX_VERBS:
        return "fix", clip(text)
    if first_word in _IMPROVE_VERBS:
        return "improvement", clip(text)
    return None, None


# ------------------------------------------------------------------------- paths

_SENSITIVE_NAME = re.compile(
    r"""(?ix)
    ^(\.env(\..*)?|\.npmrc|\.pypirc|\.netrc|\.htpasswd|
      id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|
      credentials(\..*)?|secrets?(\..*)?|.*\.(pem|key|pfx|p12|kdbx|tfstate|keystore|jks))$
    """
)


def export_safe_relative_path(path: str | None) -> str | None:
    """
    A project-relative, forward-slash path that is safe to put in an export, or None.

    Rejects absolute paths, parent traversal, drive letters, secret-looking file
    names, and anything inside an ignored/virtualenv tree.
    """
    if not path:
        return None
    cleaned = path.strip().replace("\\", "/")
    if not cleaned or cleaned.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", cleaned):
        return None
    segments = [seg for seg in cleaned.split("/") if seg]
    if not segments or any(seg in (".", "..") for seg in segments):
        return None
    if _SENSITIVE_NAME.match(segments[-1]):
        return None
    if is_ignored_relative_path("/".join(segments)):
        return None
    return "/".join(segments)


def _safe_paths(paths: tuple[str, ...], limit: int = MAX_FILES) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        safe = export_safe_relative_path(raw)
        if safe and safe not in seen:
            seen.add(safe)
            out.append(safe)
        if len(out) >= limit:
            break
    return tuple(out)


# ------------------------------------------------------------------------- model


@dataclass(frozen=True)
class ProjectIdentity:
    name: str
    category: str | None = None
    status: str | None = None
    last_opened_at: str | None = None
    has_open_session: bool = False


@dataclass(frozen=True)
class CommitRef:
    subject: str
    committed_at: str | None = None
    short_hash: str | None = None


@dataclass(frozen=True)
class GitContext:
    is_repo: bool = False
    branch: str | None = None
    state: str = "unknown"  # clean | dirty | unknown
    modified_files: tuple[str, ...] = ()
    staged_files: tuple[str, ...] = ()
    recent_commits: tuple[CommitRef, ...] = ()


@dataclass(frozen=True)
class WorkflowFileRef:
    path: str
    kind: str


@dataclass(frozen=True)
class Continuity:
    current_focus: str | None = None
    where_you_left_off: tuple[str, ...] = ()
    suggested_next_step: str | None = None
    blockers: tuple[str, ...] = ()
    open_issues: tuple[str, ...] = ()
    last_completed: str | None = None
    recent_fixes: tuple[str, ...] = ()
    recent_improvements: tuple[str, ...] = ()
    confidence: str = "weak"
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextNotes:
    notes: str | None = None
    workflow_files: tuple[WorkflowFileRef, ...] = ()


@dataclass(frozen=True)
class ProjectContext:
    identity: ProjectIdentity
    continuity: Continuity = field(default_factory=Continuity)
    git: GitContext = field(default_factory=GitContext)
    context: ContextNotes = field(default_factory=ContextNotes)

    def snapshot_payload(self) -> dict[str, object] | None:
        """UI Project Snapshot payload, or None when there is nothing reliable to show."""
        c = self.continuity
        payload: dict[str, object] = {
            "current_focus": [c.current_focus] if c.current_focus else [],
            "open_issues": list(c.open_issues),
            "recent_fixes": list(c.recent_fixes),
            "recent_improvements": list(c.recent_improvements),
            "suggested_next_step": c.suggested_next_step,
        }
        has_content = any(
            payload[key]
            for key in (
                "current_focus", "open_issues", "recent_fixes",
                "recent_improvements", "suggested_next_step",
            )
        )
        return payload if has_content else None


@dataclass(frozen=True)
class ContextSources:
    """Everything the builder needs; assembled by the caller from local stores."""

    identity: ProjectIdentity
    notes: str | None = None
    exit_note: str | None = None
    blocker: str | None = None
    next_step: str | None = None
    artifacts: tuple[WorkflowArtifact, ...] = ()
    git_is_repo: bool = False
    git_state: str | None = None
    git_branch: str | None = None
    modified_files: tuple[str, ...] = ()
    staged_files: tuple[str, ...] = ()
    commits: tuple[dict[str, str], ...] = ()
    last_session_exit_preview: str | None = None


# ----------------------------------------------------------------------- builder

_WYLO_PREFIXES = ("suggested next step:", "blocked on:")


def _is_marker_derived(line: str) -> bool:
    """Lines the composer builds from scanner code markers (never exported as context)."""
    lowered = line.lower()
    return (
        "open marker" in lowered
        or "code marker" in lowered
        or _NO_STRONG_MARKER_MESSAGE.lower() in lowered
    )


def _wylo_lines(composed: CompositionResult) -> tuple[str, ...]:
    lines: list[str] = []
    for raw in composed.where_left_off:
        line = raw.strip()
        if not line or line.lower().startswith(_WYLO_PREFIXES):
            continue  # those have their own fields
        if _is_marker_derived(line):
            continue
        lines.append(line.removeprefix("Where you left off:").strip())
    return _dedupe_clipped([ln for ln in lines if ln], limit=3)


def _current_focus(src: ContextSources, handoff: WorkflowArtifact | None) -> str | None:
    exit_note = normalize_note(src.exit_note)
    if exit_note:
        return first_sentence(exit_note)
    if handoff and handoff.focus_area:
        return first_sentence(handoff.focus_area)
    state = extract_workflow_state(
        src.artifacts,
        exit_note=src.exit_note,
        next_step=src.next_step,
        blocker=src.blocker,
        project_notes=src.notes,
    )
    # Only a strong, document-backed focus; weak "first preview line" leads are noise.
    if state.confidence == "strong" and state.source_label not in ("blocker", "session"):
        if state.current_focus and (not handoff or state.current_focus != handoff.title):
            return first_sentence(state.current_focus)
    return None


def _blockers(src: ContextSources, handoff: WorkflowArtifact | None) -> tuple[str, ...]:
    items: list[str] = []
    session_blocker = normalize_note(src.blocker)
    if session_blocker:
        items.append(session_blocker)
    if handoff:
        items.extend(handoff.blocker_items)
    return _dedupe_clipped(items, limit=3)


def _workflow_files(artifacts: tuple[WorkflowArtifact, ...]) -> tuple[WorkflowFileRef, ...]:
    refs: list[WorkflowFileRef] = []
    seen: set[str] = set()
    for artifact in artifacts:
        safe = export_safe_relative_path(artifact.relative_path or artifact.filename)
        if safe is None or safe.lower() in seen:
            continue
        seen.add(safe.lower())
        refs.append(WorkflowFileRef(path=safe, kind=artifact.kind))
        if len(refs) >= 12:
            break
    return tuple(refs)


def _commit_refs(commits: tuple[dict[str, str], ...]) -> tuple[CommitRef, ...]:
    refs: list[CommitRef] = []
    for commit in commits[:10]:
        subject = clip(" ".join(str(commit.get("subject") or "").split()), 160)
        if not subject:
            continue
        digest = str(commit.get("commit_hash") or "").strip()
        refs.append(
            CommitRef(
                subject=subject,
                committed_at=str(commit.get("committed_at") or "") or None,
                short_hash=digest[:8] or None,
            )
        )
    return tuple(refs)


def build_project_context(src: ContextSources, composed: CompositionResult) -> ProjectContext:
    """Assemble the domain object. Pure: no I/O, no clock, deterministic."""
    handoff = primary_handoff(src.artifacts, modified_files=src.modified_files)

    fixes: list[str] = []
    improvements: list[str] = []
    for commit in src.commits:
        kind, text = classify_commit_subject(str(commit.get("subject") or ""))
        if kind == "fix" and text:
            fixes.append(text)
        elif kind == "improvement" and text:
            improvements.append(text)

    blockers = _blockers(src, handoff)
    unfinished = list(handoff.unfinished_items) if handoff else []
    exit_note = normalize_note(src.exit_note)
    last_completed = first_sentence(exit_note) if exit_note else first_sentence(
        src.last_session_exit_preview
    )

    reliable_next = (
        composed.suggested_next_step
        if composed.suggested_next_step_source not in (None, "fallback")
        else None
    )

    continuity = Continuity(
        current_focus=_current_focus(src, handoff),
        where_you_left_off=_wylo_lines(composed),
        suggested_next_step=clip(reliable_next, 240) if reliable_next else None,
        blockers=blockers,
        open_issues=_dedupe_clipped([*blockers, *unfinished]),
        last_completed=last_completed,
        recent_fixes=_dedupe_clipped(fixes),
        recent_improvements=_dedupe_clipped(improvements),
        confidence=composed.confidence,
        sources=tuple(composed.sources_used),
    )

    state = (src.git_state or "").lower()
    git = GitContext(
        is_repo=src.git_is_repo,
        branch=src.git_branch,
        state=state if state in ("clean", "dirty") else "unknown",
        modified_files=_safe_paths(src.modified_files),
        staged_files=_safe_paths(src.staged_files),
        recent_commits=_commit_refs(src.commits),
    )

    notes = normalize_note(src.notes)
    return ProjectContext(
        identity=src.identity,
        continuity=continuity,
        git=git,
        context=ContextNotes(
            notes=clip(notes, 1200) if notes else None,
            workflow_files=_workflow_files(src.artifacts),
        ),
    )
