"""Deterministic workflow-state extraction from artifacts and session fields."""

from __future__ import annotations

import re
from dataclasses import dataclass

from grafid.utils.text import dedupe
from grafid.resume.quality import normalize_note
from grafid.resume.workflow_artifacts import WorkflowArtifact, primary_handoff

KIND_PRIORITY: tuple[str, ...] = (
    "handoff",
    "next",
    "session",
    "exit_note",
    "todo",
    "notes",
    "readme",
    "changelog",
)

MAX_FIELD_CHARS = 160

_SHELL_COMMAND_LEAD = re.compile(
    r"""(?ix)^(
        (cd|npm|npx|yarn|pnpm|cargo|pip3?|python3?|powershell|pwsh|winget|choco)(\s|$)
      | [$>]\s
    )"""
)


def looks_like_shell_command(text: str) -> bool:
    """
    A doc line that is really a shell command ("cd backend"), not prose.

    Prose that merely starts with a tool name ("Python is required.") is kept:
    a command is short and does not end like a sentence.
    """
    stripped = text.strip().strip("`")
    if not stripped:
        return False
    words = stripped.split()
    sentence_like = stripped[-1] in ".?!" or len(words) > 8
    if _SHELL_COMMAND_LEAD.match(stripped) and not sentence_like:
        return True
    return len(words) <= 4 and any(word.startswith("--") for word in words)


@dataclass(frozen=True)
class WorkflowState:
    """Normalized local workflow signals for summary composition."""

    current_focus: str | None
    recent_work: str | None
    unfinished_items: tuple[str, ...]
    blockers: tuple[str, ...]
    next_step: str | None
    source_label: str | None
    confidence: str  # strong | medium | weak


def extract_workflow_state(
    artifacts: tuple[WorkflowArtifact, ...],
    *,
    exit_note: str | None = None,
    next_step: str | None = None,
    blocker: str | None = None,
    project_notes: str | None = None,
) -> WorkflowState:
    """Merge session fields and markdown artifacts into one workflow state."""
    exit_clean = normalize_note(exit_note)
    next_clean = normalize_note(next_step)
    blocker_clean = normalize_note(blocker)
    notes_clean = normalize_note(project_notes)
    handoff = primary_handoff(artifacts)

    if exit_clean:
        state = WorkflowState(
            current_focus=exit_clean,
            recent_work=None,
            unfinished_items=(),
            blockers=(blocker_clean,) if blocker_clean else (),
            next_step=next_clean or (handoff.next_step_line if handoff else None),
            source_label="exit note",
            confidence="strong",
        )
        return state

    if blocker_clean:
        state = WorkflowState(
            current_focus=f"blocked on {blocker_clean}",
            recent_work=None,
            unfinished_items=(),
            blockers=(blocker_clean,),
            next_step=next_clean,
            source_label="blocker",
            confidence="strong",
        )
        return state

    if handoff and (handoff.focus_area or handoff.next_step_line):
        state = WorkflowState(
            current_focus=handoff.focus_area or handoff.title,
            recent_work=handoff.recent_work or _first_preview(handoff),
            unfinished_items=handoff.unfinished_items,
            blockers=handoff.blocker_items,
            next_step=handoff.next_step_line or next_clean,
            source_label=handoff.filename,
            confidence="strong",
        )
        return state

    merged = _merge_artifact_signals(artifacts)
    if next_clean and not merged.next_step:
        merged = _with_next(merged, next_clean, "session")

    if notes_clean and not merged.current_focus:
        merged = WorkflowState(
            current_focus=notes_clean,
            recent_work=merged.recent_work,
            unfinished_items=merged.unfinished_items,
            blockers=merged.blockers,
            next_step=merged.next_step or next_clean,
            source_label=merged.source_label or "project notes",
            confidence="medium" if merged.confidence == "weak" else merged.confidence,
        )

    if not merged.current_focus and not merged.recent_work and next_clean:
        merged = WorkflowState(
            current_focus=f"continue with {next_clean}",
            recent_work=None,
            unfinished_items=merged.unfinished_items,
            blockers=merged.blockers,
            next_step=next_clean,
            source_label="session",
            confidence="medium",
        )

    return merged


def workflow_anchor_phrase(state: WorkflowState, *, project_name: str = "") -> str | None:
    """Human-readable phrase for 'where you left off' from workflow state."""
    if state.current_focus:
        focus = _trim(state.current_focus)
        if state.confidence in ("strong", "medium") and state.source_label not in (
            "exit note",
            "blocker",
            "session",
        ):
            return f"Last known focus: {focus}"
        if state.source_label in ("exit note", "blocker"):
            return focus
        return f"Last known focus: {focus}"
    if state.recent_work:
        return f"Recent work focused on {_trim(state.recent_work)}."
    name = (project_name or "").strip()
    if name and state.confidence != "weak":
        return f"pick up work on {name}"
    return None


def _merge_artifact_signals(
    artifacts: tuple[WorkflowArtifact, ...],
) -> WorkflowState:
    current_focus: str | None = None
    recent_work: str | None = None
    unfinished: list[str] = []
    blockers: list[str] = []
    next_step: str | None = None
    source: str | None = None
    confidence = "weak"

    sorted_artifacts = sorted(
        artifacts,
        key=lambda a: (
            KIND_PRIORITY.index(a.kind) if a.kind in KIND_PRIORITY else 99,
            a.filename.lower(),
        ),
    )

    for artifact in sorted_artifacts:
        if artifact.kind == "changelog":
            continue

        tier_boost = artifact.priority_tier == "high"

        if artifact.kind != "readme":
            if artifact.focus_area and not current_focus:
                current_focus = artifact.focus_area
                source = artifact.filename
                confidence = "strong" if tier_boost else "medium"
            if artifact.next_step_line and not next_step:
                next_step = artifact.next_step_line
            if artifact.recent_work and not recent_work:
                recent_work = artifact.recent_work
                source = source or artifact.filename
            unfinished.extend(artifact.unfinished_items)
            blockers.extend(artifact.blocker_items)
            if not current_focus and artifact.preview_lines and artifact.kind in {
                "todo",
                "notes",
                "next",
                "session",
            }:
                lead = _trim(artifact.preview_lines[0])
                if (
                    lead
                    and not _looks_like_identity_blurb(lead)
                    and not looks_like_shell_command(lead)
                ):
                    current_focus = lead
                    source = artifact.filename
                    confidence = "medium"
        else:
            if artifact.recent_work and not recent_work:
                recent_work = artifact.recent_work
                source = source or artifact.filename
                confidence = "medium"
            if artifact.focus_area and not current_focus:
                current_focus = artifact.focus_area
                source = artifact.filename
                confidence = "medium"

    if not current_focus and recent_work:
        confidence = "medium" if confidence == "weak" else confidence

    return WorkflowState(
        current_focus=current_focus,
        recent_work=recent_work,
        unfinished_items=tuple(dedupe(unfinished)[:3]),
        blockers=tuple(dedupe(blockers)[:2]),
        next_step=next_step,
        source_label=source,
        confidence=confidence,
    )


def _looks_like_identity_blurb(text: str) -> bool:
    lower = text.lower()
    return lower.startswith("local-first") or "utility for developers" in lower


def _first_preview(artifact: WorkflowArtifact) -> str | None:
    if artifact.preview_lines:
        return _trim(artifact.preview_lines[0])
    return None


def _with_next(state: WorkflowState, next_step: str, source: str) -> WorkflowState:
    return WorkflowState(
        current_focus=state.current_focus,
        recent_work=state.recent_work,
        unfinished_items=state.unfinished_items,
        blockers=state.blockers,
        next_step=next_step,
        source_label=source,
        confidence=state.confidence,
    )


def _trim(text: str, limit: int = MAX_FIELD_CHARS) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


