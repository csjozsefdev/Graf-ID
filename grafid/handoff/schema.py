"""GrafiTalk handoff contract constants.

The flat envelope is OWNED BY GRAFITALK (see its docs/GRAF_ID_EXPORT_SCHEMA.md):
``source`` "graf-id", ``schema_version`` "0.1" (string, the only version it
accepts), ``project_name``, and optional ``current_status``, ``changes``,
``blockers``, ``next_steps``, ``estimated_time``, ``notes``, ``files``. Unknown
keys are ignored by GrafiTalk and files must stay under 256 KB.

Graf-Id therefore never changes that envelope. Richer, structured data rides in
one additive ``graf_id`` extension object with its own version.
"""

from __future__ import annotations

HANDOFF_SOURCE = "graf-id"
HANDOFF_SCHEMA_VERSION = "0.1"  # GrafiTalk-owned; do NOT bump without GrafiTalk

EXTENSION_KEY = "graf_id"
EXTENSION_VERSION = 1  # Graf-Id-owned; additive changes only

# GrafiTalk rejects files >= 256 KB; leave headroom.
GRAFITALK_MAX_BYTES = 256 * 1024
MAX_HANDOFF_BYTES = 200 * 1024

MAX_TEXT_CHARS = 20_000
MAX_LIST_ITEMS = 100

FLAT_KEYS: tuple[str, ...] = (
    "source",
    "schema_version",
    "project_name",
    "current_status",
    "changes",
    "blockers",
    "next_steps",
    "estimated_time",
    "notes",
    "files",
)
STRING_KEYS = ("project_name", "current_status", "estimated_time", "notes")
LIST_KEYS = ("changes", "blockers", "next_steps", "files")
