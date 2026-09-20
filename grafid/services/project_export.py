"""Export one project as GrafiTalk handoff, full JSON context, Markdown or plain text.

Every format is rendered from the backend ProjectContext (never from UI text):

- ``handoff``  lean GrafiTalk-compatible flat envelope (contract v0.1)
- ``json``     the same flat envelope plus the additive ``graf_id`` block
- ``markdown`` / ``txt``  the lean envelope in GrafiTalk's labelled sections
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from grafid.core.exceptions import ProjectError, ValidationError
from grafid.db.connection import DatabaseConnection
from grafid.handoff.builder import build_handoff
from grafid.handoff.render import render_json, render_markdown, render_text
from grafid.resume.project_context import ProjectContext, ProjectIdentity
from grafid.services.project_overview import build_dashboard_item, project_context_for_item
from grafid.services.project_registry import ProjectRegistryService
from grafid.utils.logging_setup import get_logger

logger = get_logger("project_export")

ExportFormat = Literal["json", "markdown", "txt", "handoff"]

VALID_FORMATS: frozenset[str] = frozenset({"json", "markdown", "txt", "handoff"})
FORMAT_EXTENSIONS: dict[str, str] = {
    "json": "json",
    "markdown": "md",
    "txt": "txt",
    "handoff": "json",
}
FILENAME_LABELS: dict[str, str] = {
    "json": "context",
    "markdown": "summary",
    "txt": "summary",
    "handoff": "grafitalk-handoff",
}


@dataclass(frozen=True)
class ExportWriteResult:
    """Result of writing one export file."""

    path: str
    format: str
    bytes_written: int
    suggested_filename: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "format": self.format,
            "bytes_written": self.bytes_written,
            "suggested_filename": self.suggested_filename,
        }


def _normalize_format(export_format: str) -> ExportFormat:
    cleaned = export_format.strip().lower()
    if cleaned == "md":
        cleaned = "markdown"
    if cleaned not in VALID_FORMATS:
        raise ValidationError(
            f"Unsupported export format: {export_format!r}. "
            "Use one of: handoff, json, markdown, txt."
        )
    return cleaned  # type: ignore[return-value]


def project_slug(project_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", project_name.lower()).strip("-")
    return slug[:60] or "project"


def suggested_filename(
    project_name: str,
    export_format: str,
    *,
    exported_at: datetime | None = None,
) -> str:
    """Safe dated filename for desktop save dialogs."""
    normalized = _normalize_format(export_format)
    stamp = (exported_at or datetime.now(UTC)).strftime("%Y-%m-%d")
    label = FILENAME_LABELS[normalized]
    return f"{project_slug(project_name)}-{label}-{stamp}.{FORMAT_EXTENSIONS[normalized]}"


def build_export_payload(
    db_path: Path,
    project_id: int,
    export_format: str,
    *,
    exported_at: str | None = None,
) -> dict[str, Any]:
    """Structured export payload for one project, from the backend ProjectContext."""
    normalized = _normalize_format(export_format)
    registry = ProjectRegistryService(db_path)
    try:
        record = registry.get_info(str(project_id))
    except ProjectError as exc:
        raise ValidationError(str(exc)) from exc

    try:
        with DatabaseConnection(db_path) as conn:
            item = build_dashboard_item(conn, db_path, record)
        context = project_context_for_item(item, db_path)
    except Exception as exc:  # noqa: BLE001 — a partial export beats no export
        logger.warning(
            "Full export context build failed for project_id=%s, falling back to "
            "an identity-only export: %s",
            project_id,
            exc,
        )
        context = ProjectContext(identity=ProjectIdentity(name=str(record.name)))
    return build_handoff(
        context,
        include_extension=normalized == "json",
        exported_at=exported_at or datetime.now(UTC).isoformat(timespec="seconds"),
    )


def render_export_content(payload: dict[str, Any], export_format: str) -> str:
    """Serialize a payload for the requested format."""
    normalized = _normalize_format(export_format)
    if normalized in ("json", "handoff"):
        return render_json(payload)
    if normalized == "markdown":
        return render_markdown(payload)
    return render_text(payload)


def write_text_atomic(target: Path, content: str) -> int:
    """Write ``content`` to ``target`` via a temp file + replace (never a half-written export)."""
    data = content.encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return len(data)


def export_to_path(
    db_path: Path,
    project_id: int,
    output_path: Path,
    export_format: str,
) -> ExportWriteResult:
    """Write export content to ``output_path``."""
    normalized = _normalize_format(export_format)
    registry = ProjectRegistryService(db_path)
    try:
        record = registry.get_info(str(project_id))
    except ProjectError as exc:
        raise ValidationError(str(exc)) from exc

    target = output_path.expanduser().resolve()
    if target.is_dir():
        raise ValidationError(f"Export path is a directory: {target}")

    payload = build_export_payload(db_path, project_id, normalized)
    content = render_export_content(payload, normalized)
    try:
        written = write_text_atomic(target, content)
    except OSError as exc:
        raise ValidationError(f"Could not write export file: {exc}") from exc

    return ExportWriteResult(
        path=str(target),
        format=normalized,
        bytes_written=written,
        suggested_filename=suggested_filename(str(record.name), normalized),
    )
