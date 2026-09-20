"""Export every project's GrafiTalk handoff into an inbox folder.

Layout (no absolute user paths, no database ids)::

    <inbox>/
      manifest.json      index of exported projects
      README.md
      projects/<slug>.json   one lean GrafiTalk-compatible handoff per project
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from grafid import __version__
from grafid.config.paths import resolve_app_config_dir
from grafid.core.exceptions import ValidationError
from grafid.db.connection import DatabaseConnection
from grafid.handoff.builder import build_handoff
from grafid.handoff.render import render_json
from grafid.services.project_overview import build_dashboard_item, project_context_for_item
from grafid.services.project_export import project_slug, write_text_atomic
from grafid.services.project_registry import ProjectRegistryService
from grafid.utils.logging_setup import get_logger

logger = get_logger("grafitalk_export")

INBOX_MANIFEST_VERSION = 1
PROJECTS_SUBDIR = "projects"
MANIFEST_NAME = "manifest.json"
README_NAME = "README.md"
DEFAULT_INBOX_DIRNAME = "grafitalk-inbox"


def default_grafitalk_dir(config_dir: Path | None = None) -> Path:
    """
    Default inbox: ``<Graf-Id data folder>/grafitalk-inbox``.

    Override with ``GRAFID_GRAFITALK_DIR``. (It used to live next to the source
    checkout, which is meaningless — and unwritable — in an installed app.)
    """
    if raw := os.environ.get("GRAFID_GRAFITALK_DIR"):
        return Path(raw).expanduser().resolve()
    return (config_dir or resolve_app_config_dir()) / DEFAULT_INBOX_DIRNAME


def _unique_filename(slug: str, used: set[str]) -> str:
    candidate = f"{slug}.json"
    counter = 2
    while candidate.lower() in used:
        candidate = f"{slug}-{counter}.json"
        counter += 1
    used.add(candidate.lower())
    return candidate


def _readme_text() -> str:
    return (
        "# GrafiTalk inbox (Graf-Id)\n\n"
        "One GrafiTalk-compatible handoff file (contract v0.1) per project.\n"
        "Import a file from `projects/` with GrafiTalk's Context panel > Import.\n\n"
        "Nothing here contains your local folder paths. Re-export from Graf-Id "
        "(Settings > Data > Export all projects...) to refresh.\n"
    )


def export_grafitalk_inbox(
    *,
    db_path: Path,
    output_dir: Path | None = None,
    config_dir: Path | None = None,
) -> Path:
    """Write one handoff file per registered project plus a manifest. Returns the inbox dir."""
    inbox = (output_dir or default_grafitalk_dir(config_dir or db_path.parent)).expanduser().resolve()
    if inbox.exists() and not inbox.is_dir():
        raise ValidationError(f"Export folder is not a directory: {inbox}")
    projects_dir = inbox / PROJECTS_SUBDIR
    projects_dir.mkdir(parents=True, exist_ok=True)

    exported_at = datetime.now(UTC).isoformat(timespec="seconds")
    registry = ProjectRegistryService(db_path)
    used: set[str] = set()
    entries: list[dict[str, object]] = []

    for record in registry.list_projects():
        with DatabaseConnection(db_path) as conn:
            item = build_dashboard_item(conn, db_path, record)
        context = project_context_for_item(item, db_path)
        payload = build_handoff(context, include_extension=False)
        filename = _unique_filename(project_slug(str(record.name)), used)
        write_text_atomic(projects_dir / filename, render_json(payload))
        entries.append(
            {
                "name": str(record.name),
                "file": f"{PROJECTS_SUBDIR}/{filename}",
                "headline": payload.get("current_status"),
            }
        )

    manifest = {
        "manifest_version": INBOX_MANIFEST_VERSION,
        "app": "Graf-Id",
        "app_version": __version__,
        "exported_at": exported_at,
        "handoff_schema_version": "0.1",
        "project_count": len(entries),
        "projects": entries,
    }
    write_text_atomic(inbox / MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    write_text_atomic(inbox / README_NAME, _readme_text())

    logger.info("GrafiTalk inbox exported to %s (%s projects)", inbox, len(entries))
    return inbox
