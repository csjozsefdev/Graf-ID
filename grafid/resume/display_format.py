"""Deterministic display formatting for timestamps, durations and scan previews."""

from __future__ import annotations


def format_display_timestamp(iso: str | None) -> str | None:
    """ISO timestamp to ``YYYY-MM-DD HH:MM`` (deterministic, no locale)."""
    if not iso or not iso.strip():
        return None
    cleaned = iso.strip().replace("T", " ")
    if len(cleaned) >= 19:
        return cleaned[:19]
    return cleaned


def format_duration_label(seconds: float | None) -> str | None:
    """Human duration label for sessions (omit sub-minute spans)."""
    if seconds is None or seconds < 60:
        return None
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    rem = minutes % 60
    return f"{hours}h {rem}m" if rem else f"{hours}h"


def session_duration_seconds(
    started_at: str | None,
    ended_at: str | None,
) -> float | None:
    """Elapsed seconds between ISO timestamps when both ends are present."""
    if not started_at or not ended_at:
        return None
    try:
        from datetime import UTC, datetime

        start_raw = started_at.strip()
        end_raw = ended_at.strip()
        if start_raw.endswith("Z"):
            start_raw = start_raw[:-1] + "+00:00"
        if end_raw.endswith("Z"):
            end_raw = end_raw[:-1] + "+00:00"
        start = datetime.fromisoformat(start_raw)
        end = datetime.fromisoformat(end_raw)
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        delta = (end - start).total_seconds()
        return delta if delta >= 0 else None
    except (TypeError, ValueError):
        return None


def build_scan_summary_preview(
    *,
    scanned_files_count: int,
    findings_count: int,
    git_branch: str | None = None,
    git_dirty: bool | None = None,
) -> str:
    """Deterministic one-line preview when no session note is correlated."""
    parts = [f"Scanned {scanned_files_count} files", f"{findings_count} findings"]
    if git_branch:
        dirty = "dirty" if git_dirty else "clean"
        parts.append(f"{git_branch} ({dirty})")
    return ", ".join(parts)
