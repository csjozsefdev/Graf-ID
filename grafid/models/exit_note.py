"""Exit note history models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExitNoteHistoryRecord:
    """One persisted exit-note event when a session closes."""

    id: int
    project_id: int
    session_id: int
    exit_note: str | None
    blocker: str | None
    next_step: str | None
    recorded_at: str
    skipped: bool
