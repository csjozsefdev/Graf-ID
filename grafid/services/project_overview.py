"""Project overview assembly: dashboard items, resume panels and ProjectContext.

Everything the desktop UI and the exports need to describe one project (git,
session, scan and summary facts) is built here from the database. The IPC
handlers only call these functions and wrap the result in an envelope; the
export services use them directly, so no service depends on the IPC layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from grafid.core.exceptions import ProjectError
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.git_snapshot_repository import GitSnapshotRepository
from grafid.db.repositories.scan_finding_repository import ScanFindingRepository
from grafid.db.repositories.session_repository import SessionRepository
from grafid.db.repositories.snapshot_repository import SnapshotRepository
from grafid.models.session import WorkSessionRecord
from grafid.models.snapshot import GitSnapshotRecord
from grafid.resume.generator import count_open_tasks
from grafid.resume.human_display import humanize_stored_body
from grafid.resume.quality import normalize_note
from grafid.resume.session_signals import resolve_summary_session_fields
from grafid.resume.summary_engine import SummaryEngine
from grafid.resume.workflow_artifacts import load_workflow_artifacts
from grafid.scanner.ignore import is_ignored_relative_path
from grafid.services.history_display import build_history_display_rows
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.resume_service import ResumeService
from grafid.utils.logging_setup import get_logger

if TYPE_CHECKING:
    from grafid.scanner.models import TaskFinding

logger = get_logger("services.project_overview")

RESUME_EXCERPT_CHARS = 400
HISTORY_LIMIT_DEFAULT = 15
MODIFIED_FILES_LIMIT = 5
ALLOWED_SCAN_MARKERS = frozenset({"TODO", "FIXME", "BUG", "NEXT", "HACK"})
TASK_MARKER_PREVIEW_LIMIT = 3


def top_task_marker_lines(db_path, project_id: int, limit: int = TASK_MARKER_PREVIEW_LIMIT) -> tuple[str, ...]:
    """Clean, grouped lines from latest scan markers (not raw code fragments)."""
    from grafid.scanner.marker_quality import format_markers_for_summary

    findings = task_findings_from_latest_scan(db_path, project_id)
    return format_markers_for_summary(list(findings), limit=limit, low_confidence=False)


def task_findings_from_latest_scan(
    db_path,
    project_id: int,
    *,
    limit: int = 40,
) -> tuple["TaskFinding", ...]:
    from grafid.scanner.models import TaskFinding

    with DatabaseConnection(db_path) as conn:
        entries = SnapshotRepository(conn).list_history_for_project(project_id, limit=1)
        if not entries:
            return ()
        raw = ScanFindingRepository(conn).list_for_snapshot(entries[0].snapshot_id)

    findings: list[TaskFinding] = []
    seen: set[tuple[str, int, str]] = set()
    for row in raw:
        if row.marker not in ALLOWED_SCAN_MARKERS:
            continue
        # Findings stored by an older scan may still sit under a virtualenv or
        # other ignored tree; never surface third-party code as project work.
        if is_ignored_relative_path(row.file_path):
            continue
        key = (row.file_path, row.line_number, row.marker)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            TaskFinding(
                file_path=row.file_path,
                line_number=row.line_number,
                marker=row.marker,
                text=row.text,
                severity=row.severity or "low",
                created_at=row.created_at or "",
            )
        )
        if len(findings) >= limit:
            break
    return tuple(findings)


def _git_lists_from_snapshot(
    db_path, project_id: int
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[dict[str, str], ...]]:
    """(modified files, staged files, recent commits) from the latest git snapshot."""
    try:
        with DatabaseConnection(db_path) as conn:
            git = GitSnapshotRepository(conn).get_latest_for_project(project_id)
    except Exception as exc:  # noqa: BLE001 — context build must not fail on this
        logger.warning("Could not load git context for project_id=%s: %s", project_id, exc)
        return (), (), ()
    if git is None:
        return (), (), ()
    return tuple(git.modified_files), tuple(git.staged_files), tuple(git.latest_commits)


def _last_exit_preview(sessions: list[dict[str, Any]] | None) -> str | None:
    for row in sessions or []:
        note = (row.get("exit_note") or "").strip()
        if note:
            return note
    return None


def _summary_inputs(
    item: dict[str, Any],
    db_path,
    *,
    timeline_sessions: list[dict[str, Any]] | None = None,
    root_only: bool = False,
) -> tuple[dict[str, Any], Any, tuple, tuple[str, ...], list[dict[str, Any]]]:
    """
    Gather the local inputs shared by the dashboard summary and ProjectContext.

    Returns (common kwargs, session signals, workflow artifacts, task markers,
    timeline sessions). The kwargs are accepted by both SummaryEngine.build_dashboard
    and human_context.build_context_bundle, so the UI and every export are built
    from the same facts.
    """
    session = item.get("latest_session") or {}
    project_id = int(item["id"])
    with DatabaseConnection(db_path) as conn:
        session_signals = resolve_summary_session_fields(conn, project_id)
    git = item.get("git_status") or {}
    git_label = git.get("label")
    if git.get("branch"):
        git_label = f"{git_label} — branch {git['branch']}"

    artifacts = load_workflow_artifacts(str(item.get("path", "")))
    if root_only:
        artifacts = tuple(a for a in artifacts if a.in_project_root)
    task_markers = top_task_marker_lines(db_path, project_id)
    modified_files = modified_files_from_git(db_path, project_id)
    if timeline_sessions is None:
        with DatabaseConnection(db_path) as conn:
            timeline_sessions = [
                session_to_dict(s, is_active=s.ended_at is None)
                for s in SessionRepository(conn).list_for_project(project_id, limit=3)
            ]
    git_modified, git_staged, git_commits = _git_lists_from_snapshot(db_path, project_id)
    kwargs: dict[str, Any] = dict(
        project_name=str(item.get("name", "")),
        project_notes=item.get("notes"),
        last_session_label=_format_last_session_label(session),
        modified_files=modified_files,
        exit_note=session_signals.exit_note,
        blocker=session_signals.blocker,
        next_step=session_signals.next_step,
        has_active_session=session_signals.has_active_session,
        artifacts=artifacts,
        open_task_count=item.get("open_task_count"),
        has_scan=item.get("latest_scan_at") is not None,
        git_label=git_label,
        task_markers=task_markers,
        session_started_at=session_signals.session_started_at,
        last_refreshed_at=item.get("last_refreshed_at"),
        git_state=git.get("state"),
        git_branch=git.get("branch"),
        git_is_repo=bool(git.get("is_git_repo")),
        git_commits=git_commits,
        git_modified_files=git_modified,
        git_staged_files=git_staged,
        project_category=item.get("category"),
        project_status=item.get("status"),
        last_session_exit_preview=_last_exit_preview(timeline_sessions),
    )
    return kwargs, session_signals, artifacts, task_markers, timeline_sessions


def project_context_for_item(item: dict[str, Any], db_path):
    """Backend ProjectContext for a dashboard item (used by exports and handoff)."""
    from grafid.resume.human_context import build_context_bundle

    # Exports never carry content from outside the project root (parent-folder
    # documents are a local UI convenience only).
    kwargs, _signals, _artifacts, _markers, _timeline = _summary_inputs(
        item, db_path, root_only=True
    )
    _composed, context = build_context_bundle(
        **kwargs, last_opened_at=item.get("last_opened_at")
    )
    return context


def build_human_summary_block(
    item: dict[str, Any],
    db_path,
    *,
    timeline_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Human-facing summary for dashboard/resume panel (unified SummaryEngine)."""
    session = item.get("latest_session") or {}
    kwargs, session_signals, artifacts, task_markers, timeline_sessions = _summary_inputs(
        item, db_path, timeline_sessions=timeline_sessions
    )
    engine = SummaryEngine()
    result = engine.build_dashboard(
        **kwargs,
        timeline_sessions=timeline_sessions,
        last_opened_at=item.get("last_opened_at"),
        last_session_ended_at=session_signals.last_session_ended_at or session.get("ended_at"),
    )
    return {
        "headline": result.headline,
        "summary_text": result.body,
        "scroll_excerpt": result.body,
        "generated_at": item.get("updated_at"),
        "source": "summary_engine",
        "sources_used": result.sources_used,
        "attributed_lines": result.attributed_lines,
        "timeline": result.to_dict()["timeline"],
        "away_label": result.away_label,
        "workflow_files": [a.filename for a in artifacts],
        "task_markers": list(task_markers),
        "confidence": result.confidence,
        "mvp_sections": result.mvp_sections,
        "project_snapshot": result.project_snapshot,
    }


def modified_files_from_git(db_path, project_id: int) -> tuple[str, ...]:
    try:
        with DatabaseConnection(db_path) as conn:
            git = GitSnapshotRepository(conn).get_latest_for_project(project_id)
    except Exception as exc:  # noqa: BLE001 — dashboard row build must not fail on this
        logger.warning(
            "Could not load modified files for project_id=%s: %s", project_id, exc
        )
        return ()
    if git is None:
        return ()
    return tuple(git.modified_files[:5])


def _format_last_session_label(session: dict[str, Any]) -> str | None:
    if not session:
        return None
    if session.get("is_active"):
        started = session.get("started_at", "")
        return f"Active session since {started}" if started else "Active session"
    ended = session.get("ended_at")
    if ended:
        return f"Ended {ended}"
    return None


def public_dashboard_item(item: dict[str, Any]) -> dict[str, Any]:
    """Drop internal-only fields before JSON IPC responses."""
    public = dict(item)
    public.pop("_summary_block", None)
    return public


def item_and_resume_panel(
    conn,
    db_path,
    record,
    project_id: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build dashboard row + resume panel without duplicate summary work."""
    item = build_dashboard_item(conn, db_path, record)
    summary_block = item.pop("_summary_block", None)
    resume_panel = build_resume_panel(
        db_path, project_id, item, startup_block=summary_block
    )
    return item, resume_panel


def project_detail_payload(conn, db_path, record) -> dict[str, Any]:
    """Preload project detail for desktop without extra IPC calls."""
    item, resume_panel = item_and_resume_panel(conn, db_path, record, int(record.id))
    history = build_history_display_rows(
        project_id=int(record.id),
        project_name=str(record.name),
        db_path=db_path,
        limit=HISTORY_LIMIT_DEFAULT,
    )
    return {
        "project": public_dashboard_item(item),
        "resume_panel": resume_panel,
        "history": history,
    }


def _minimal_dashboard_project(record) -> dict[str, Any]:
    """Safe dashboard row when full detail build fails."""
    return {
        **project_to_dict(record),
        "has_open_session": False,
        "latest_session": None,
        "summary_preview": None,
        "git_status": _git_status_dict(None),
        "has_resume": False,
        "open_task_count": None,
        "latest_scan_at": None,
        "load_error": None,
    }


def _bootstrap_project_fallback(record, error_message: str) -> dict[str, Any]:
    """One project entry when preload fails — keeps bootstrap usable."""
    project = _minimal_dashboard_project(record)
    project["load_error"] = error_message
    return {
        **project,
        "resume_panel": {},
        "history": [],
    }


def build_bootstrap_projects(db_path, projects: list) -> list[dict[str, Any]]:
    """Bootstrap payload: include per-project cached detail (panel + history)."""
    with DatabaseConnection(db_path) as conn:
        out: list[dict[str, Any]] = []
        for record in projects:
            try:
                payload = project_detail_payload(conn, db_path, record)
                out.append(
                    {
                        **payload["project"],
                        "resume_panel": payload["resume_panel"],
                        "history": payload["history"],
                    }
                )
            except Exception as exc:  # noqa: BLE001 — isolate per project
                logger.warning(
                    "Bootstrap preload failed for project_id=%s: %s",
                    record.id,
                    exc,
                )
                out.append(_bootstrap_project_fallback(record, str(exc)))
        return out


def resolve_project(registry: ProjectRegistryService, project_id: int):
    try:
        return registry.get_info(str(project_id))
    except ProjectError as exc:
        raise ProjectError(f"Project not found: {project_id}") from exc


def build_dashboard_item(conn, db_path, record) -> dict[str, Any]:
    project = project_to_dict(record)
    session = _latest_session(conn, record.id)
    git = GitSnapshotRepository(conn).get_latest_for_project(record.id)
    resume = ResumeService(db_path).get_latest_stored_summary(record.id, mode="short")
    scan_ctx = _scan_context(conn, record.id)

    git_status = _git_status_dict(git)
    scan_ctx = _scan_context(conn, record.id)
    item_ctx = {
        **project,
        "latest_session": session,
        "git_status": git_status,
        "open_task_count": scan_ctx["open_task_count"],
        "latest_scan_at": scan_ctx["latest_scan_at"],
    }
    summary_block = build_human_summary_block(item_ctx, db_path)
    summary_preview: dict[str, Any] | None = None
    if summary_block:
        summary_preview = {
            "headline": summary_block["headline"],
            "summary_text": summary_block["summary_text"],
            "generated_at": summary_block.get("generated_at"),
            "source": summary_block.get("source"),
        }

    return {
        **project,
        "has_open_session": bool(session and session.get("is_active")),
        "latest_session": session,
        "summary_preview": summary_preview,
        "git_status": git_status,
        "has_resume": resume is not None,
        "open_task_count": scan_ctx["open_task_count"],
        "latest_scan_at": scan_ctx["latest_scan_at"],
        "_summary_block": summary_block,
    }


def build_resume_panel(
    db_path,
    project_id: int,
    item: dict[str, Any],
    *,
    startup_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session = item.get("latest_session") or {}
    stored = ResumeService(db_path).get_latest_stored_summary(project_id, mode="short")

    with DatabaseConnection(db_path) as conn:
        session_signals = resolve_summary_session_fields(conn, project_id)

    blocker = session_signals.blocker
    next_step = session_signals.next_step
    exit_note = session_signals.exit_note

    modified_files: list[str] = []
    with DatabaseConnection(db_path) as conn:
        git = GitSnapshotRepository(conn).get_latest_for_project(project_id)
        if git is not None:
            modified_files = list(git.modified_files[:MODIFIED_FILES_LIMIT])

    if startup_block is None:
        startup_block = build_human_summary_block(item, db_path)

    scan_ctx = scan_context_from_item(item)

    return {
        "startup_summary": startup_block,
        "workflow_files": startup_block.get("workflow_files", []),
        "sources_used": startup_block.get("sources_used", []),
        "blocker": blocker,
        "next_step": next_step,
        "exit_note": exit_note,
        "modified_files": modified_files,
        "stored_resume_excerpt": _excerpt(
            humanize_stored_body(stored.summary_body) if stored else None
        ),
        "git_status": item.get("git_status"),
        "has_stored_resume": stored is not None,
        "latest_session": session if session else None,
        "last_opened_at": item.get("last_opened_at"),
        "open_task_count": scan_ctx["open_task_count"],
        "latest_scan_at": scan_ctx["latest_scan_at"],
        "last_refreshed_at": item.get("last_refreshed_at"),
        "confidence": startup_block.get("confidence"),
        "mvp_sections": startup_block.get("mvp_sections", []),
        "timeline": startup_block.get("timeline", []),
        "attributed_lines": startup_block.get("attributed_lines", []),
        "away_label": startup_block.get("away_label"),
        "project_snapshot": startup_block.get("project_snapshot"),
    }


def _scan_context(conn, project_id: int) -> dict[str, Any]:
    """Latest scan task-marker count (deterministic, DB-only)."""
    entries = SnapshotRepository(conn).list_history_for_project(project_id, limit=1)
    if not entries:
        return {"open_task_count": None, "latest_scan_at": None}
    entry = entries[0]
    findings = ScanFindingRepository(conn).list_for_snapshot(entry.snapshot_id)
    return {
        "open_task_count": count_open_tasks(tuple(findings)),
        "latest_scan_at": entry.scanned_at,
    }


def scan_context_from_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "open_task_count": item.get("open_task_count"),
        "latest_scan_at": item.get("latest_scan_at"),
    }


def _latest_session(conn, project_id: int) -> dict[str, Any] | None:
    repo = SessionRepository(conn)
    active = repo.get_active_for_project(project_id)
    if active is not None:
        return session_to_dict(active, is_active=True)
    ended = repo.get_last_ended_for_project(project_id)
    if ended is not None:
        return session_to_dict(ended, is_active=False)
    return None


def session_to_dict(session: WorkSessionRecord, *, is_active: bool) -> dict[str, Any]:
    return {
        "id": session.id,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "is_active": is_active,
        "status": session.status,
        "summary": session.summary,
        "exit_note": normalize_note(session.exit_note),
        "blocker": normalize_note(session.blocker),
        "next_step": normalize_note(session.next_step),
    }


def _git_status_dict(git: GitSnapshotRecord | None) -> dict[str, Any]:
    if git is None:
        return {
            "state": "unknown",
            "label": "No scan yet",
            "is_git_repo": False,
            "is_dirty": False,
            "branch": None,
        }
    if not git.is_git_repo:
        return {
            "state": "not_repo",
            "label": "Not a git repository",
            "is_git_repo": False,
            "is_dirty": False,
            "branch": None,
        }
    state = "dirty" if git.is_dirty else "clean"
    label = "Git: uncommitted changes" if git.is_dirty else "Git: clean"
    branch = git.current_branch or "unknown"
    return {
        "state": state,
        "label": label,
        "is_git_repo": True,
        "is_dirty": git.is_dirty,
        "branch": branch,
    }


def _excerpt(text: str | None, limit: int = RESUME_EXCERPT_CHARS) -> str | None:
    if not text:
        return None
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def project_to_dict(record) -> dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name,
        "path": record.path,
        "path_accessible": Path(record.path).is_dir(),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "last_opened_at": record.last_opened_at,
        "preferred_ide": record.preferred_ide,
        "is_active": record.is_active,
        "category": record.category,
        "status": record.status,
        "notes": record.notes,
        "last_refreshed_at": record.last_refreshed_at,
        "sidebar_order": record.sidebar_order,
    }
