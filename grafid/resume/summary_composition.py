"""Workflow-first resume composition (no scanner changes, no AI)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from grafid.resume.quality import MAX_PREVIEW_CHARS, normalize_note, trim_preview_text
from grafid.resume.workflow_artifacts import (
    WorkflowArtifact,
    _sanitize_workflow_text,
    primary_handoff,
)
from grafid.resume.workflow_state import (
    WorkflowState,
    extract_workflow_state,
    looks_like_shell_command,
    workflow_anchor_phrase,
)
from grafid.scanner.marker_quality import (
    assess_marker_text_usefulness,
    extract_marker_text_from_summary_line,
    workflow_marker_lines,
)

_NO_STRONG_MARKER_MESSAGE = (
    "No strong workflow marker found yet. Consider adding an Exit Note before closing the session."
)

MAX_PRIMARY_LINES = 5
MAX_LINE_CHARS = MAX_PREVIEW_CHARS

# Git labels/states that should never appear in the primary resume panel.
_GIT_SKIP_LABELS = frozenset(
    {
        "no scan yet",
        "unknown",
        "not a git repository",
        "not a git repo",
    }
)

_ARTIFACT_KIND_ORDER: tuple[str, ...] = (
    "handoff",
    "next",
    "session",
    "exit_note",
    "todo",
    "notes",
    "readme",
)


@dataclass(frozen=True)
class CompositionInput:
    """Verified local inputs for one project resume."""

    project_name: str = ""
    exit_note: str | None = None
    next_step: str | None = None
    blocker: str | None = None
    has_active_session: bool = False
    session_started_at: str | None = None
    last_refreshed_at: str | None = None
    project_notes: str | None = None
    artifacts: tuple[WorkflowArtifact, ...] = ()
    task_markers: tuple[str, ...] = ()
    open_task_count: int | None = None
    has_scan: bool = False
    modified_files: tuple[str, ...] = ()
    git_label: str | None = None
    git_state: str | None = None
    git_branch: str | None = None
    git_is_repo: bool = False
    last_session_label: str | None = None


@dataclass(frozen=True)
class CompositionResult:
    headline: str
    primary_lines: tuple[str, ...]
    sources_used: tuple[str, ...]
    suggested_next_step: str | None
    where_left_off: tuple[str, ...]
    supporting_notes: tuple[str, ...]
    technical_notes: tuple[str, ...]
    confidence: str
    # Where the suggestion came from: session | workflow | handoff | blocker |
    # unfinished | fallback (a generic "continue ..." / "review changes ..." hint).
    suggested_next_step_source: str | None = None


def compose_workflow_summary(data: CompositionInput) -> CompositionResult:
    """Build a short, resume-oriented primary summary from ranked signals."""
    exit_clean = normalize_note(data.exit_note)
    next_clean = normalize_note(data.next_step)
    blocker_clean = normalize_note(data.blocker)
    handoff = primary_handoff(data.artifacts)
    notes_clean = normalize_note(data.project_notes)
    workflow_state = extract_workflow_state(
        data.artifacts,
        exit_note=data.exit_note,
        next_step=data.next_step,
        blocker=data.blocker,
        project_notes=data.project_notes,
    )

    handoff_next = (
        normalize_note(handoff.next_step_line) if handoff and handoff.next_step_line else None
    )
    workflow_markers = workflow_marker_lines(data.task_markers)
    scan_had_markers_only_noise = bool(data.task_markers) and not workflow_markers
    has_human_doc = _has_human_documentation_signal(
        exit_clean=exit_clean,
        blocker_clean=blocker_clean,
        notes_clean=notes_clean,
        next_clean=next_clean,
        handoff=handoff,
        workflow_state=workflow_state,
        artifacts=data.artifacts,
        task_markers=workflow_markers,
    )
    suggested, suggested_source = _pick_suggested_next_step(
        next_clean=next_clean,
        handoff_next=handoff_next,
        blocker_clean=blocker_clean,
        handoff=handoff,
        task_markers=workflow_markers,
        exit_clean=exit_clean,
        modified_files=data.modified_files,
        workflow_state=workflow_state,
        artifacts=data.artifacts,
        has_human_doc=has_human_doc,
    )

    sources: list[str] = []
    primary: list[str] = []
    technical: list[str] = []

    # 1. Strongest workflow signal → "where you left off"
    anchor = _strongest_anchor_line(
        exit_clean=exit_clean,
        blocker_clean=blocker_clean,
        handoff=handoff,
        next_clean=next_clean,
        notes_clean=notes_clean,
        task_markers=workflow_markers,
        modified_files=data.modified_files,
        project_name=data.project_name,
        scan_had_markers_only_noise=scan_had_markers_only_noise,
        has_scan=data.has_scan,
        workflow_state=workflow_state,
        has_active_session=data.has_active_session,
        artifacts=data.artifacts,
        has_human_doc=has_human_doc,
    )
    if anchor:
        primary.append(anchor.line)
        sources.append(anchor.source)

    # 2. Suggested next step (once)
    if suggested and not _line_mentions_next(primary, suggested):
        primary.append(f"Suggested next step: {_trim(suggested)}")
        sources.append("next step")

    # 3. Unfinished work
    if blocker_clean and not _any_contains(primary, blocker_clean):
        primary.append(f"Blocked on: {_trim(blocker_clean)}")
        sources.append("blocker")
    elif data.has_active_session:
        session_note = _active_session_note(
            data,
            has_anchor=bool(anchor),
            workflow_confidence=workflow_state.confidence,
        )
        if session_note and len(primary) < MAX_PRIMARY_LINES:
            primary.append(session_note)
            sources.append("active session")

    # 4. One supporting note (readme / handoff focus / markers / files) — not raw dumps
    support = _supporting_context_line(
        data,
        handoff=handoff,
        notes_clean=notes_clean,
        workflow_markers=workflow_markers,
    )
    if support and len(primary) < MAX_PRIMARY_LINES:
        primary.append(support.line)
        sources.append(support.source)

    # 5. Git — only when useful
    git_line = _git_workflow_line(
        git_label=data.git_label,
        git_state=data.git_state,
        git_branch=data.git_branch,
        git_is_repo=data.git_is_repo,
        modified_files=data.modified_files,
    )
    if git_line:
        if has_human_doc:
            technical.append(git_line)
            sources.append("git")
        elif len(primary) < MAX_PRIMARY_LINES:
            primary.append(git_line)
            sources.append("git")

    # Technical / diagnostics (for MVP detail sections, not primary wall of text)
    if workflow_markers:
        technical.extend(workflow_markers[:5])
    elif scan_had_markers_only_noise:
        technical.append(
            "Latest scan had code markers, but none read like workflow notes."
        )
    elif data.has_scan and data.open_task_count:
        technical.append(
            f"{data.open_task_count} code marker(s) in the latest scan."
        )
    if data.last_refreshed_at:
        technical.append(f"Context last refreshed: {data.last_refreshed_at}")

    readme_artifact = _find_readme(data.artifacts)
    if readme_artifact and readme_artifact.preview_lines:
        technical.append(
            f"README excerpt: {_trim(readme_artifact.preview_lines[0], 120)}"
        )

    primary = _dedupe_lines(primary)[:MAX_PRIMARY_LINES]
    confidence = _confidence(data, exit_clean, handoff, notes_clean, anchor is not None)

    if not primary and confidence == "weak" and not data.has_active_session:
        primary = [
            "No workflow context yet. Add an Exit Note or handoff note when you pause work."
        ]

    headline = _headline(
        anchor=anchor,
        suggested=suggested,
        exit_clean=exit_clean,
        blocker_clean=blocker_clean,
        handoff=handoff,
        has_active_session=data.has_active_session,
        project_name=data.project_name,
        primary=primary,
    )

    supporting_notes = _supporting_notes_for_sections(
        data, handoff=handoff, notes_clean=notes_clean
    )

    return CompositionResult(
        headline=headline,
        primary_lines=tuple(primary),
        sources_used=tuple(_dedupe_sources(sources)),
        suggested_next_step=suggested,
        where_left_off=tuple(primary[:3]),
        supporting_notes=supporting_notes,
        technical_notes=tuple(technical[:6]),
        confidence=confidence,
        suggested_next_step_source=suggested_source if suggested else None,
    )


@dataclass(frozen=True)
class _Anchor:
    line: str
    source: str


def _looks_like_identity_blurb(text: str) -> bool:
    lower = text.lower()
    return lower.startswith("local-first") or "utility for developers" in lower


def _first_meaningful_preview_line(artifact: WorkflowArtifact) -> str | None:
    if artifact.recent_work:
        line = _trim(artifact.recent_work)
        if line and not _looks_like_identity_blurb(line) and not looks_like_shell_command(line):
            return line
    for raw in artifact.preview_lines:
        line = _trim(raw)
        if line and not _looks_like_identity_blurb(line) and not looks_like_shell_command(line):
            return line
    return None


def _artifact_kind_rank(artifact: WorkflowArtifact) -> int:
    try:
        return _ARTIFACT_KIND_ORDER.index(artifact.kind)
    except ValueError:
        return 99


def _sorted_doc_artifacts(
    artifacts: tuple[WorkflowArtifact, ...],
    handoff: WorkflowArtifact | None,
) -> list[WorkflowArtifact]:
    seen: set[str] = set()
    ordered: list[WorkflowArtifact] = []
    if handoff:
        ordered.append(handoff)
        seen.add(handoff.filename.lower())
    for artifact in sorted(
        artifacts,
        key=lambda item: (_artifact_kind_rank(item), item.filename.lower()),
    ):
        if artifact.kind == "changelog":
            continue
        key = artifact.filename.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(artifact)
    return ordered


def _artifact_content_anchor(
    artifacts: tuple[WorkflowArtifact, ...],
    handoff: WorkflowArtifact | None,
) -> _Anchor | None:
    for artifact in _sorted_doc_artifacts(artifacts, handoff):
        if artifact.focus_area:
            continue
        line = _first_meaningful_preview_line(artifact)
        if line:
            return _Anchor(f"Where you left off: {line}", artifact.filename)
    return None


def _has_human_documentation_signal(
    *,
    exit_clean: str | None,
    blocker_clean: str | None,
    notes_clean: str | None,
    next_clean: str | None,
    handoff: WorkflowArtifact | None,
    workflow_state: WorkflowState | None,
    artifacts: tuple[WorkflowArtifact, ...],
    task_markers: tuple[str, ...],
) -> bool:
    if exit_clean or blocker_clean or notes_clean or next_clean:
        return True
    if handoff and (
        handoff.focus_area
        or handoff.next_step_line
        or handoff.preview_lines
        or handoff.recent_work
        or handoff.title
    ):
        return True
    if workflow_state and (
        workflow_state.current_focus
        or workflow_state.recent_work
        or workflow_state.next_step
        or workflow_state.unfinished_items
    ):
        if (
            workflow_state.confidence != "weak"
            or workflow_state.recent_work
            or workflow_state.unfinished_items
        ):
            return True
    if _artifact_content_anchor(artifacts, handoff) is not None:
        return True
    if _first_marker_hint(task_markers):
        return True
    return False


def _strongest_anchor_line(
    *,
    exit_clean: str | None,
    blocker_clean: str | None,
    handoff: WorkflowArtifact | None,
    next_clean: str | None,
    notes_clean: str | None,
    task_markers: tuple[str, ...],
    modified_files: tuple[str, ...],
    project_name: str,
    scan_had_markers_only_noise: bool = False,
    has_scan: bool = False,
    workflow_state: WorkflowState | None = None,
    has_active_session: bool = False,
    artifacts: tuple[WorkflowArtifact, ...] = (),
    has_human_doc: bool = False,
) -> _Anchor | None:
    if exit_clean:
        return _Anchor(f"Where you left off: {_trim(exit_clean)}", "exit note")
    if blocker_clean:
        return _Anchor(f"Where you left off: blocked on {_trim(blocker_clean)}", "blocker")
    if handoff:
        if handoff.focus_area:
            label = handoff.title or handoff.filename.replace(".md", "")
            return _Anchor(
                f"Where you left off: {label} — focus on {handoff.focus_area}",
                handoff.filename,
            )
        preview_line = _first_meaningful_preview_line(handoff)
        if preview_line:
            return _Anchor(f"Where you left off: {preview_line}", handoff.filename)
        label = handoff.title or handoff.filename.replace(".md", "")
        return _Anchor(f"Where you left off: {label}", handoff.filename)
    if workflow_state:
        phrase = workflow_anchor_phrase(workflow_state, project_name=project_name)
        if phrase and not (
            phrase.startswith("pick up work on")
            and workflow_state.confidence == "weak"
            and not workflow_state.recent_work
        ):
            return _Anchor(
                f"Where you left off: {_trim(phrase)}",
                workflow_state.source_label or "workflow",
            )
        if workflow_state.recent_work:
            return _Anchor(
                "Where you left off: Recent work focused on "
                f"{_trim(workflow_state.recent_work)}.",
                workflow_state.source_label or "workflow",
            )
        if workflow_state.unfinished_items:
            item = _trim(workflow_state.unfinished_items[0])
            return _Anchor(
                f"Where you left off: unfinished — {item}",
                workflow_state.source_label or "workflow",
            )
    artifact_anchor = _artifact_content_anchor(artifacts, handoff)
    if artifact_anchor:
        return artifact_anchor
    if next_clean:
        return _Anchor(f"Where you left off: continue with {_trim(next_clean)}", "session")
    if notes_clean:
        return _Anchor(f"Where you left off: {_trim(notes_clean)}", "project notes")
    marker_hint = _first_marker_hint(task_markers)
    if marker_hint:
        return _Anchor(f"Where you left off: {marker_hint}", "scan markers")
    if scan_had_markers_only_noise and has_scan:
        return _Anchor(f"Where you left off: {_NO_STRONG_MARKER_MESSAGE}", "scan markers")
    if modified_files and not has_human_doc:
        names = ", ".join(modified_files[:2])
        return _Anchor(f"Where you left off: recent edits in {names}", "git changes")
    if has_active_session:
        return _Anchor(
            "Where you left off: active session exists, but no detailed Exit Note or workflow handoff was found.",
            "active session",
        )
    name = (project_name or "").strip()
    if name:
        return _Anchor(f"Where you left off: pick up work on {name}", "project")
    return None


def _pick_suggested_next_step(
    *,
    next_clean: str | None,
    handoff_next: str | None,
    blocker_clean: str | None,
    handoff: WorkflowArtifact | None,
    task_markers: tuple[str, ...],
    exit_clean: str | None,
    modified_files: tuple[str, ...],
    workflow_state: WorkflowState | None = None,
    artifacts: tuple[WorkflowArtifact, ...] = (),
    has_human_doc: bool = False,
) -> tuple[str | None, str | None]:
    """
    Pick the suggested next step and report which kind of source it came from.

    Priority: session next step, workflow state, handoff next line, resolving
    the blocker, an unfinished item, then generic fallbacks. Scanner code-marker
    text is intentionally NOT a source: it produced fragments such as
    'address open marker: { label: "Next", ... },' on real projects. Markers stay
    available as evidence in the details section.
    """
    if next_clean:
        return next_clean, "session"
    if workflow_state and workflow_state.next_step:
        return workflow_state.next_step, "workflow"
    if handoff_next:
        step = _sanitize_workflow_text(handoff_next)
        if step:
            return step, "handoff"
    if blocker_clean:
        return f"resolve the blocker ({blocker_clean})", "blocker"
    if exit_clean:
        return None, None
    if workflow_state and workflow_state.unfinished_items:
        return workflow_state.unfinished_items[0], "unfinished"
    if workflow_state and workflow_state.recent_work:
        return f"continue {workflow_state.recent_work}", "fallback"
    if handoff and handoff.focus_area:
        return f"continue in {handoff.focus_area}", "fallback"
    for artifact in _sorted_doc_artifacts(artifacts, handoff):
        if artifact.next_step_line:
            step = _sanitize_workflow_text(normalize_note(artifact.next_step_line))
            if step:
                return step, "handoff"
    if modified_files and not has_human_doc:
        return f"review changes in {modified_files[0]}", "fallback"
    return None, None


def _first_marker_hint(
    task_markers: tuple[str, ...],
    *,
    for_next_step: bool = False,
) -> str | None:
    for raw in task_markers:
        body = extract_marker_text_from_summary_line(raw)
        if not body:
            continue
        if assess_marker_text_usefulness(body) == "low":
            continue
        if assess_marker_text_usefulness(body) == "possible" and for_next_step:
            continue
        detail = body
        if for_next_step:
            return f"address open marker: {detail[:80]}"
        return f"open marker — {detail[:80]}"
    return None


def _active_session_note(
    data: CompositionInput,
    *,
    has_anchor: bool,
    workflow_confidence: str = "weak",
) -> str | None:
    if not data.has_active_session:
        return None
    if not has_anchor:
        if workflow_confidence == "weak":
            return (
                "Active session exists, but no detailed Exit Note or workflow handoff was found."
            )
        name = (data.project_name or "").strip() or "this project"
        return f"Work in progress on {name}."
    if data.session_started_at:
        when = _relative_day(data.session_started_at)
        if when:
            return f"Session still open (started {when})."
    return "Session still open on this project."


def _supporting_context_line(
    data: CompositionInput,
    *,
    handoff: WorkflowArtifact | None,
    notes_clean: str | None,
    workflow_markers: tuple[str, ...] = (),
) -> _Anchor | None:
    readme = _find_readme(data.artifacts)
    if readme:
        focus = _readme_focus_line(readme)
        if focus:
            return _Anchor(focus, readme.filename)
    if handoff and handoff.focus_area:
        return None  # already in anchor
    if notes_clean:
        return _Anchor(f"Pinned note: {_trim(notes_clean)}", "project notes")
    if workflow_markers and len(workflow_markers) > 1:
        return _Anchor(
            f"{len(workflow_markers)} more readable code markers in the latest scan.",
            "scan markers",
        )
    return None


def _readme_focus_line(artifact: WorkflowArtifact) -> str | None:
    """One short identity line — never dump the README intro verbatim."""
    raw = ""
    if artifact.preview_lines:
        raw = artifact.preview_lines[0].strip()
    elif artifact.title:
        raw = artifact.title.strip()
    if not raw:
        return None
    raw = re.sub(r"^#+\s*", "", raw)
    raw = re.sub(r"[*_`]", "", raw)
    # Drop leading project name token if duplicated (e.g. "Graf-Id Local-first...")
    name_token = (artifact.title or "").split()[0] if artifact.title else ""
    if name_token and raw.lower().startswith(name_token.lower()):
        raw = raw[len(name_token) :].strip(" -—:")
    sentence = re.split(r"[.!?\n]", raw, maxsplit=1)[0].strip()
    if not sentence:
        return None
    sentence = sentence.lower() if sentence.isupper() else sentence
    if len(sentence) > 90:
        sentence = sentence[:87].rstrip() + "…"
    return f"Project focus: {sentence}."


def _git_workflow_line(
    *,
    git_label: str | None,
    git_state: str | None,
    git_branch: str | None,
    git_is_repo: bool,
    modified_files: tuple[str, ...],
) -> str | None:
    label = (git_label or "").strip().lower()
    if label in _GIT_SKIP_LABELS or not git_is_repo:
        return None
    state = (git_state or "").lower()
    branch = git_branch or "unknown"
    if state == "dirty" or "dirty" in label:
        if modified_files:
            return f"Uncommitted work on {branch} ({modified_files[0]} and others)."
        return f"Uncommitted changes on branch {branch}."
    if state == "clean" or "clean" in label:
        return f"Working tree clean on {branch}."
    return None


def _supporting_notes_for_sections(
    data: CompositionInput,
    *,
    handoff: WorkflowArtifact | None,
    notes_clean: str | None,
) -> tuple[str, ...]:
    lines: list[str] = []
    if notes_clean:
        lines.append(notes_clean)
    if handoff and handoff.preview_lines:
        lines.append(f"{handoff.filename}: {_trim(handoff.preview_lines[0], 100)}")
    readme = _find_readme(data.artifacts)
    if readme:
        focus = _readme_focus_line(readme)
        if focus:
            lines.append(focus)
    return tuple(lines[:4])


def _find_readme(artifacts: tuple[WorkflowArtifact, ...]) -> WorkflowArtifact | None:
    for artifact in artifacts:
        if artifact.kind == "readme":
            return artifact
    return None


def _headline(
    *,
    anchor: _Anchor | None,
    suggested: str | None,
    exit_clean: str | None,
    blocker_clean: str | None,
    handoff: WorkflowArtifact | None,
    has_active_session: bool,
    project_name: str,
    primary: list[str],
) -> str:
    if primary:
        first = primary[0]
        if first.startswith("Where you left off:"):
            return _trim(first.replace("Where you left off:", "").strip(), 100)
        return _trim(first, 100)
    if suggested:
        return f"Next: {_trim(suggested, 80)}"
    if handoff:
        label = handoff.title or handoff.filename.replace(".md", "")
        return _trim(label, 100)
    if has_active_session:
        name = (project_name or "").strip() or "this project"
        return f"Resume {name}"
    return "Where you left off"


def _confidence(
    data: CompositionInput,
    exit_clean: str | None,
    handoff: WorkflowArtifact | None,
    notes_clean: str | None,
    has_anchor: bool,
) -> str:
    if exit_clean or handoff:
        return "high"
    if has_anchor or notes_clean or data.has_active_session:
        return "medium"
    if data.has_scan or workflow_marker_lines(data.task_markers):
        return "low"
    return "weak"


def _trim(text: str, limit: int = MAX_LINE_CHARS) -> str:
    return trim_preview_text(text, limit)


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def _dedupe_sources(sources: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for source in sources:
        key = source.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(source)
    return out


def _any_contains(lines: list[str], fragment: str) -> bool:
    frag = fragment.lower()
    return any(frag in line.lower() for line in lines)


def _line_mentions_next(lines: list[str], suggested: str) -> bool:
    needle = suggested.lower()[:40]
    return any(needle in line.lower() for line in lines)


def _relative_day(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        token = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(token)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        delta = (now.date() - dt.date()).days
        if delta == 0:
            return "today"
        if delta == 1:
            return "yesterday"
        return f"on {dt.date().isoformat()}"
    except ValueError:
        return None
