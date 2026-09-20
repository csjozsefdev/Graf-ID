"""GrafiTalk contract oracle for tests.

Encodes GrafiTalk's documented v0.1 importer rules independently of Graf-Id's own
validator (grafid.handoff.validate), so a regression in that validator can never
hide a broken export. Test support only - not part of the shipped application.
"""

from __future__ import annotations

import json
from typing import Any

from grafid.handoff.schema import GRAFITALK_MAX_BYTES


def check_grafitalk_compatibility(payload: dict[str, Any]) -> list[str]:
    """
    Return the reasons GrafiTalk's documented importer would reject ``payload``
    (empty list means compatible). Independent of validate_handoff on purpose:
    it encodes GrafiTalk's rules, so a regression in Graf-Id's own validator can
    never hide a broken export.
    """
    problems: list[str] = []
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(encoded) >= GRAFITALK_MAX_BYTES:
        problems.append("file is 256 KB or larger")
    if payload.get("source") != "graf-id":
        problems.append('source must be "graf-id"')
    if payload.get("schema_version") != "0.1":
        problems.append('schema_version must be the string "0.1"')
    name = payload.get("project_name")
    if not isinstance(name, str) or not name.strip():
        problems.append("project_name must be a non-empty string")
    for key in ("current_status", "estimated_time", "notes"):
        if key in payload and not isinstance(payload[key], str):
            problems.append(f"{key} must be a string")
    for key in ("changes", "blockers", "next_steps", "files"):
        if key in payload and not (
            isinstance(payload[key], list) and all(isinstance(i, str) for i in payload[key])
        ):
            problems.append(f"{key} must be a list of strings")
    return problems
