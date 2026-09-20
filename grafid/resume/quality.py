"""Resume readability helpers (deterministic noise reduction)."""

from __future__ import annotations

from typing import Literal

SummaryPurpose = Literal["resume", "startup"]

# Canonical lowercase phrases treated as empty / skipped (exact match after cleanup).
PLACEHOLDER_PHRASES: frozenset[str] = frozenset(
    {
        "",
        "-",
        ".",
        "nil",
        "null",
        "none",
        "n/a",
        "na",
        "ok",
        "nothing",
        "no",
        "no blocker",
        "no blockers",
        "no next step",
        "no next steps",
        "no note",
        "no notes",
        "no exit note",
        "nothing to report",
        "not applicable",
    }
)

MAX_SCROLL_CHARS_RESUME = 12_000
MAX_SCROLL_CHARS_STARTUP = 6_000
MAX_PREVIEW_CHARS = 320


def trim_preview_text(text: str, limit: int = MAX_PREVIEW_CHARS) -> str:
    """Collapse whitespace and truncate on a word boundary with an ellipsis."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    segment = collapsed[: limit - 1]
    last_space = segment.rfind(" ")
    if last_space > 0:
        segment = segment[:last_space]
    return segment.rstrip() + "…"


def canonical_note_text(value: str) -> str:
    """Normalize user text for deterministic placeholder comparison."""
    cleaned = " ".join(value.strip().split()).lower()
    return cleaned.rstrip(".,!?;:")


def is_meaningful_text(value: str | None) -> bool:
    """Return True when text should appear in a user-facing summary."""
    if value is None:
        return False
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return False
    return canonical_note_text(cleaned) not in PLACEHOLDER_PHRASES


def normalize_note(value: str | None) -> str | None:
    """Strip and drop placeholder / low-value notes."""
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    if not is_meaningful_text(cleaned):
        return None
    return cleaned


def truncate_scroll_content(text: str, *, purpose: SummaryPurpose) -> str:
    """Cap scrollable body size with an explicit truncation marker."""
    limit = (
        MAX_SCROLL_CHARS_STARTUP if purpose == "startup" else MAX_SCROLL_CHARS_RESUME
    )
    if len(text) <= limit:
        return text
    marker = "\n... (truncated for display; full data remains in the database)"
    keep = limit - len(marker)
    return text[:keep].rstrip() + marker


def compact_section_title(title: str) -> str:
    """Shorter section labels for startup summaries."""
    mapping = {
        "Last session note (done)": "Done",
        "Current blocker": "Blocker",
        "Next step": "Next",
        "Unfinished task markers": "Tasks",
        "Last active files": "Files",
        "Modified files": "Modified",
        "Context": "Info",
    }
    return mapping.get(title, title)
