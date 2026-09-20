"""Unified deterministic summary engine (dashboard, resume, startup)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from grafid.resume.human_context import build_dashboard_summary
from grafid.resume.display_format import format_duration_label
from grafid.resume.workflow_artifacts import WorkflowArtifact

SummaryOutput = Literal["dashboard"]


@dataclass(frozen=True)
class TimelineEntry:
    """One row in the session timeline block."""

    session_id: int
    started_at: str
    ended_at: str | None
    status: str
    exit_note_preview: str | None
    duration_label: str | None


@dataclass(frozen=True)
class SummaryEngineResult:
    """Unified summary payload for IPC/UI."""

    output: SummaryOutput
    headline: str
    body: str
    sources_used: list[str]
    attributed_lines: list[dict[str, str]]
    timeline: list[TimelineEntry]
    away_label: str | None
    confidence: str
    mvp_sections: list[dict[str, str]]
    project_snapshot: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "headline": self.headline,
            "body": self.body,
            "sources_used": self.sources_used,
            "attributed_lines": self.attributed_lines,
            "timeline": [
                {
                    "session_id": e.session_id,
                    "started_at": e.started_at,
                    "ended_at": e.ended_at,
                    "status": e.status,
                    "exit_note_preview": e.exit_note_preview,
                    "duration_label": e.duration_label,
                }
                for e in self.timeline
            ],
            "away_label": self.away_label,
            "confidence": self.confidence,
            "mvp_sections": self.mvp_sections,
            "project_snapshot": self.project_snapshot,
        }


def build_session_timeline(
    sessions: list[dict[str, Any]],
    *,
    limit: int = 3,
) -> list[TimelineEntry]:
    """Last N sessions for timeline UI."""
    entries: list[TimelineEntry] = []
    for row in sessions[:limit]:
        exit_note = row.get("exit_note") or ""
        preview = None
        if exit_note:
            first = exit_note.strip().split("\n", 1)[0]
            preview = first[:120] if first else None
        entries.append(
            TimelineEntry(
                session_id=int(row["id"]),
                started_at=str(row.get("started_at", "")),
                ended_at=row.get("ended_at"),
                status=str(row.get("status", "completed")),
                exit_note_preview=preview,
                duration_label=format_duration_label(row.get("duration_seconds")),
            )
        )
    return entries


def compute_away_label(
    *,
    last_opened_at: str | None,
    last_session_ended_at: str | None,
    last_refreshed_at: str | None = None,
) -> str | None:
    """
    Human label for how stale the project's data actually is.

    Anchored on last_refreshed_at first — that is the honest "how long
    since this project's data was actually updated" signal — falling back
    to session/open times only for a project that has never been
    refreshed at all. Deliberately NOT gated on has_active_session by the
    caller: a work session left open for months (no auto-close exists)
    must not be able to hide a long-stale project (found via real-world
    use — a 90-day-old session made a 90-day-stale project look current).
    """
    from datetime import UTC, datetime

    anchor = last_refreshed_at or last_session_ended_at or last_opened_at
    if not anchor:
        return None
    try:
        if anchor.endswith("Z"):
            anchor = anchor[:-1] + "+00:00"
        then = datetime.fromisoformat(anchor)
        if then.tzinfo is None:
            then = then.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        days = (now - then).days
    except ValueError:
        return None
    if days < 1:
        return None
    if days == 1:
        return "Away for 1 day"
    return f"Away for {days} days"


def _attribute_lines(sources_used: list[str], body_lines: list[str]) -> list[dict[str, str]]:
    """Map summary lines to primary source tags for UI."""
    attributed: list[dict[str, str]] = []
    primary = sources_used[0] if sources_used else "context"
    for line in body_lines[:6]:
        tag = primary
        lower = line.lower()
        if "blocker" in lower:
            tag = "session blocker"
        elif "handoff" in lower:
            tag = "handoff"
        elif line.startswith("Suggested"):
            tag = "next step"
        attributed.append({"text": line, "source": tag})
    return attributed


class SummaryEngine:
    """Single entry point for deterministic summaries."""

    def build_dashboard(
        self,
        *,
        project_name: str = "",
        project_notes: str | None = None,
        last_session_label: str | None = None,
        modified_files: tuple[str, ...] = (),
        exit_note: str | None,
        blocker: str | None,
        next_step: str | None,
        has_active_session: bool,
        artifacts: tuple[WorkflowArtifact, ...],
        open_task_count: int | None,
        has_scan: bool,
        git_label: str | None,
        task_markers: tuple[str, ...] = (),
        timeline_sessions: list[dict[str, Any]] | None = None,
        last_opened_at: str | None = None,
        last_session_ended_at: str | None = None,
        session_started_at: str | None = None,
        last_refreshed_at: str | None = None,
        git_state: str | None = None,
        git_branch: str | None = None,
        git_is_repo: bool = False,
        git_commits: tuple[dict[str, str], ...] = (),
        git_modified_files: tuple[str, ...] | None = None,
        git_staged_files: tuple[str, ...] = (),
        project_category: str | None = None,
        project_status: str | None = None,
        last_session_exit_preview: str | None = None,
    ) -> SummaryEngineResult:
        human = build_dashboard_summary(
            project_name=project_name,
            project_notes=project_notes,
            last_session_label=last_session_label,
            session_started_at=session_started_at,
            last_refreshed_at=last_refreshed_at,
            modified_files=modified_files,
            exit_note=exit_note,
            blocker=blocker,
            next_step=next_step,
            has_active_session=has_active_session,
            artifacts=artifacts,
            open_task_count=open_task_count,
            has_scan=has_scan,
            git_label=git_label,
            task_markers=task_markers,
            git_state=git_state,
            git_branch=git_branch,
            git_is_repo=git_is_repo,
            git_commits=git_commits,
            git_modified_files=git_modified_files,
            git_staged_files=git_staged_files,
            project_category=project_category,
            project_status=project_status,
            last_opened_at=last_opened_at,
            last_session_exit_preview=last_session_exit_preview,
        )
        body = str(human.get("summary_text", ""))
        lines = [ln for ln in body.split("\n") if ln.strip()]
        sources = list(human.get("sources_used", []))
        timeline = build_session_timeline(timeline_sessions or [])
        away = compute_away_label(
            last_opened_at=last_opened_at,
            last_session_ended_at=last_session_ended_at,
            last_refreshed_at=last_refreshed_at,
        )
        headline = str(human.get("headline", ""))
        if away:
            headline = f"{away} — {headline}" if headline else away
        return SummaryEngineResult(
            output="dashboard",
            headline=headline,
            body=body,
            sources_used=sources,
            attributed_lines=_attribute_lines(sources, lines),
            timeline=timeline,
            away_label=away,
            confidence=str(human.get("confidence", "medium")),
            mvp_sections=list(human.get("mvp_sections") or []),
            project_snapshot=human.get("project_snapshot"),  # type: ignore[arg-type]
        )
