"""Render a handoff payload as JSON, Markdown or plain text.

Markdown and text use exactly the labels GrafiTalk's importer recognises
(Project / Current status / What changed / Current blocker / Next step /
Estimated time / Notes / Files updated), so every format imports to the same
context.
"""

from __future__ import annotations

from grafid.utils.text import clean_optional_text

import json
from typing import Any


def _items(value: object | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _sections(payload: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """(label, body, is_list) in contract order; empty sections are omitted."""
    out: list[tuple[str, str, bool]] = [("Project", str(payload["project_name"]).strip(), False)]
    status = clean_optional_text(payload.get("current_status"))
    if status:
        out.append(("Current status", status, False))
    for key, label in (
        ("changes", "What changed"),
        ("blockers", "Current blocker"),
        ("next_steps", "Next step"),
    ):
        items = _items(payload.get(key))
        if items:
            out.append((label, "\n".join(f"- {item}" for item in items), True))
    estimated = clean_optional_text(payload.get("estimated_time"))
    if estimated:
        out.append(("Estimated time", estimated, False))
    notes = clean_optional_text(payload.get("notes"))
    if notes:
        out.append(("Notes", notes, False))
    files = _items(payload.get("files"))
    if files:
        out.append(("Files updated", "\n".join(f"- {item}" for item in files), True))
    return out


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_text(payload: dict[str, Any]) -> str:
    return "\n\n".join(f"{label}:\n{body}" for label, body, _ in _sections(payload)) + "\n"


def render_markdown(payload: dict[str, Any]) -> str:
    return "\n\n".join(f"# {label}\n{body}" if label == "Project" else f"## {label}\n{body}"
                       for label, body, _ in _sections(payload)) + "\n"
