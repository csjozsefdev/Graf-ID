"""Build GrafiTalk handoff payloads from a ProjectContext (never from UI text)."""

from __future__ import annotations

import json
from typing import Any

from grafid import __version__
from grafid.handoff.schema import (
    EXTENSION_KEY,
    EXTENSION_VERSION,
    HANDOFF_SCHEMA_VERSION,
    HANDOFF_SOURCE,
    MAX_HANDOFF_BYTES,
)
from grafid.resume.project_context import ProjectContext, clip
from grafid.utils.text import dedupe

_MAX_CHANGES = 10
_MAX_FILES = 20


def _squash(text: str) -> str:
    return " ".join(str(text).split())


def git_summary_line(context: ProjectContext) -> str | None:
    """One human line for the flat contract (which has no git field)."""
    git = context.git
    if not git.is_repo:
        return None
    files = list(dict.fromkeys([*git.modified_files, *git.staged_files]))
    branch = f" on {git.branch}" if git.branch else ""
    if git.state == "dirty":
        count = len(files)
        detail = f", {count} changed file{'s' if count != 1 else ''}" if count else ""
        return f"Git: uncommitted changes{branch}{detail}."
    if git.state == "clean":
        return f"Git: working tree clean{branch}."
    return None


def build_flat(context: ProjectContext) -> dict[str, Any]:
    """The GrafiTalk-compatible lean envelope (contract v0.1). Empty optionals omitted."""
    c = context.continuity
    payload: dict[str, Any] = {
        "source": HANDOFF_SOURCE,
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "project_name": context.identity.name,
    }

    # Only a reliable focus (exit note / handoff focus). Document prose picked as a
    # "where you left off" anchor stays in graf_id.continuity, not in the lean status.
    if c.current_focus:
        payload["current_status"] = c.current_focus

    changes = dedupe(
        [*( [c.last_completed] if c.last_completed else [] ), *c.recent_fixes, *c.recent_improvements],
        limit=_MAX_CHANGES,
        clean=_squash,
    )
    if changes:
        payload["changes"] = changes
    if c.blockers:
        payload["blockers"] = list(c.blockers)
    if c.suggested_next_step:
        payload["next_steps"] = [c.suggested_next_step]

    notes_parts = [part for part in (context.context.notes, git_summary_line(context)) if part]
    if notes_parts:
        payload["notes"] = "\n".join(notes_parts)

    files = dedupe(
        [*context.git.modified_files, *context.git.staged_files],
        limit=_MAX_FILES,
        clean=_squash,
    )
    if files:
        payload["files"] = files
    return payload


def _compact(value: dict[str, Any]) -> dict[str, Any]:
    """Drop None / empty containers so optional fields simply do not appear."""
    return {k: v for k, v in value.items() if v not in (None, [], {}, "")}


def build_extension(context: ProjectContext, *, exported_at: str) -> dict[str, Any]:
    """The additive ``graf_id`` block: structured continuity, git and context."""
    ident, c, git, ctx = context.identity, context.continuity, context.git, context.context
    return {
        "extension_version": EXTENSION_VERSION,
        "exported_at": exported_at,
        "app_version": __version__,
        "project": _compact(
            {
                "name": ident.name,
                "category": ident.category,
                "status": ident.status,
                "last_opened_at": ident.last_opened_at,
                "has_open_session": ident.has_open_session,
            }
        ),
        "continuity": _compact(
            {
                "current_focus": c.current_focus,
                "where_you_left_off": list(c.where_you_left_off),
                "suggested_next_step": c.suggested_next_step,
                "blockers": list(c.blockers),
                "open_issues": list(c.open_issues),
                "last_completed": c.last_completed,
                "recent_fixes": list(c.recent_fixes),
                "recent_improvements": list(c.recent_improvements),
                "confidence": c.confidence,
                "sources": list(c.sources),
            }
        ),
        "git": _compact(
            {
                "is_repo": git.is_repo,
                "branch": git.branch,
                "state": git.state,
                "modified_files": list(git.modified_files),
                "staged_files": list(git.staged_files),
                "recent_commits": [
                    _compact(
                        {
                            "subject": commit.subject,
                            "committed_at": commit.committed_at,
                            "short_hash": commit.short_hash,
                        }
                    )
                    for commit in git.recent_commits
                ],
            }
        ),
        "context": _compact(
            {
                "notes": ctx.notes,
                "workflow_files": [
                    {"path": ref.path, "kind": ref.kind} for ref in ctx.workflow_files
                ],
            }
        ),
    }


def build_handoff(
    context: ProjectContext,
    *,
    include_extension: bool,
    exported_at: str | None = None,
) -> dict[str, Any]:
    """
    Lean handoff (``include_extension=False``) or the full JSON export
    (flat envelope + ``graf_id`` block). Deterministic for a given context and
    ``exported_at``.
    """
    payload = build_flat(context)
    if include_extension:
        if exported_at is None:
            raise ValueError("exported_at is required for the full JSON export")
        payload[EXTENSION_KEY] = build_extension(context, exported_at=exported_at)
    return enforce_size_limit(payload)


def serialized_size(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def enforce_size_limit(payload: dict[str, Any], limit: int = MAX_HANDOFF_BYTES) -> dict[str, Any]:
    """
    Keep the file under GrafiTalk's 256 KB cap by shedding the least important
    material first: extension commits, workflow files, then long notes.
    """
    if serialized_size(payload) <= limit:
        return payload
    out = json.loads(json.dumps(payload))
    ext = out.get(EXTENSION_KEY)
    if isinstance(ext, dict):
        ext.get("git", {}).pop("recent_commits", None)
        if serialized_size(out) <= limit:
            return out
        ext.get("context", {}).pop("workflow_files", None)
        if serialized_size(out) <= limit:
            return out
    if isinstance(out.get("notes"), str):
        out["notes"] = clip(out["notes"], 2000)
    if serialized_size(out) > limit and isinstance(ext, dict):
        out.pop(EXTENSION_KEY, None)
    return out
