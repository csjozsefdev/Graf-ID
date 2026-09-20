"""Append-only local usage journal for personal workflow validation."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grafid.config.paths import resolve_app_config_dir
from grafid.core.constants import LOG_DIR_NAME
from grafid.observability.settings import usage_journal_enabled
from grafid.utils.logging_setup import get_logger

logger = get_logger("usage_journal")

JOURNAL_FILENAME = "usage_journal.jsonl"
MAX_READ_LINES = 2000


def journal_path_for(config_dir: Path | None = None) -> Path:
    base = config_dir if config_dir is not None else resolve_app_config_dir()
    return (base / LOG_DIR_NAME / JOURNAL_FILENAME).resolve()


def record_event(
    event: str,
    *,
    config_dir: Path | None = None,
    config: Any | None = None,
    **fields: Any,
) -> None:
    """
    Append one local observation event when the usage journal is enabled.

    Events stay on disk only (JSONL under the log directory).
    """
    from grafid.config.manager import AppConfig

    cfg = config if isinstance(config, AppConfig) else None
    if not usage_journal_enabled(cfg):
        return

    path = journal_path_for(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **{k: v for k, v in fields.items() if v is not None},
    }
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Could not write usage journal: %s", exc)


def _read_recent_lines(path: Path, limit: int = MAX_READ_LINES) -> list[str]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return lines[-limit:]


def summarize_journal(
    *,
    config_dir: Path | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Aggregate recent local events for reflection (CLI / IPC)."""
    path = journal_path_for(config_dir)
    lines = _read_recent_lines(path, limit=limit)
    counts: Counter[str] = Counter()
    recent: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or "event" not in row:
            continue
        counts[str(row["event"])] += 1
        recent.append(row)
    recent = recent[-20:]

    friction_hints = _friction_hints(counts)
    return {
        "journal_enabled": usage_journal_enabled(),
        "journal_path": str(path),
        "journal_exists": path.is_file(),
        "events_read": len(recent),
        "event_counts": dict(counts.most_common(30)),
        "friction_hints": friction_hints,
        "recent_events": recent,
    }


def _friction_hints(counts: Counter[str]) -> list[str]:
    hints: list[str] = []
    bootstrap = counts.get("ipc.bootstrap", 0)
    dismiss = counts.get("ipc.dismiss_startup", 0)
    skip_notes = counts.get("session.close_skip_notes", 0)
    close_total = counts.get("session.close", 0) + skip_notes

    if bootstrap >= 3 and dismiss >= bootstrap:
        hints.append(
            "Startup summaries are often dismissed — consider shorter headlines or fewer repeats."
        )
    if close_total >= 2 and skip_notes >= max(1, close_total // 2):
        hints.append(
            "Exit notes are often skipped — try `graf-id session close --prompt` when tired."
        )
    if counts.get("startup.summary_empty", 0) >= 2:
        hints.append(
            "Empty startup summaries repeat — run scan + session notes to build continuity."
        )
    if counts.get("ipc.bootstrap_failed", 0) >= 1:
        hints.append("Bootstrap failures logged — check config.json and database integrity.")
    return hints
