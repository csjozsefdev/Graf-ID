"""Validate incoming handoff JSON (contract v0.1 + optional ``graf_id`` extension).

Used by project-context import and by contract tests. Rules mirror GrafiTalk's
documented importer: source "graf-id", schema_version "0.1", non-empty
project_name, files under 256 KB, unknown keys ignored, malformed or newer
optional extension tolerated (dropped with a warning), never a reason to
reject the flat part.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from grafid.core.exceptions import ValidationError
from grafid.handoff.schema import (
    EXTENSION_KEY,
    EXTENSION_VERSION,
    FLAT_KEYS,
    GRAFITALK_MAX_BYTES,
    HANDOFF_SCHEMA_VERSION,
    HANDOFF_SOURCE,
    LIST_KEYS,
    MAX_LIST_ITEMS,
    MAX_TEXT_CHARS,
    STRING_KEYS,
)


class HandoffValidationError(ValidationError):
    """The input is not an acceptable Graf-Id handoff."""


@dataclass(frozen=True)
class ValidatedHandoff:
    data: dict[str, Any]
    extension: dict[str, Any] | None = None
    ignored_keys: tuple[str, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)


def parse_handoff_bytes(raw: bytes) -> ValidatedHandoff:
    """Decode + validate a handoff file (size, encoding, JSON, schema)."""
    if len(raw) > GRAFITALK_MAX_BYTES:
        raise HandoffValidationError(
            f"Handoff file is too large ({len(raw)} bytes; limit {GRAFITALK_MAX_BYTES})."
        )
    if not raw.strip():
        raise HandoffValidationError("Handoff file is empty.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HandoffValidationError("Handoff file is not valid UTF-8 text.") from exc
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HandoffValidationError(f"Handoff file is not valid JSON: {exc.msg}.") from exc
    return validate_handoff(loaded)


def _clean_string(value: object, key: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise HandoffValidationError(f"Missing required field: {key}.")
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise HandoffValidationError(f"Field {key} must be a string.")
    text = str(value).replace("\x00", "").strip()
    if not text:
        if required:
            raise HandoffValidationError(f"Field {key} must not be empty.")
        return None
    if len(text) > MAX_TEXT_CHARS:
        raise HandoffValidationError(f"Field {key} is too long (max {MAX_TEXT_CHARS} characters).")
    return text


def _clean_list(value: object, key: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HandoffValidationError(f"Field {key} must be a list of strings.")
    if len(value) > MAX_LIST_ITEMS:
        raise HandoffValidationError(f"Field {key} has too many entries (max {MAX_LIST_ITEMS}).")
    out: list[str] = []
    for item in value:
        text = _clean_string(item, key)
        if text:
            out.append(text)
    return out


def _clean_extension(value: object, warnings: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        warnings.append(f"Ignored {EXTENSION_KEY}: not an object.")
        return None
    version = value.get("extension_version")
    if isinstance(version, bool) or not isinstance(version, int):
        warnings.append(f"Ignored {EXTENSION_KEY}: missing or invalid extension_version.")
        return None
    if version > EXTENSION_VERSION:
        warnings.append(
            f"Ignored {EXTENSION_KEY}: extension_version {version} is newer than "
            f"supported ({EXTENSION_VERSION})."
        )
        return None
    return value


def validate_handoff(raw: object) -> ValidatedHandoff:
    """Validate an already-parsed JSON value. Raises HandoffValidationError."""
    if not isinstance(raw, dict):
        raise HandoffValidationError("Handoff must be a JSON object.")

    source = raw.get("source")
    if source is None:
        raise HandoffValidationError('Missing required field: source (expected "graf-id").')
    if source != HANDOFF_SOURCE:
        raise HandoffValidationError(
            f'Unsupported source {source!r}: only "{HANDOFF_SOURCE}" handoffs can be imported.'
        )

    version = raw.get("schema_version")
    if version is None:
        raise HandoffValidationError("Missing required field: schema_version.")
    if isinstance(version, bool) or not isinstance(version, (str, int, float)):
        raise HandoffValidationError("schema_version must be a string.")
    if str(version) != HANDOFF_SCHEMA_VERSION:
        raise HandoffValidationError(
            f"Unsupported schema_version {version!r}: this version of Graf-Id "
            f"supports only {HANDOFF_SCHEMA_VERSION!r}."
        )

    data: dict[str, Any] = {"source": HANDOFF_SOURCE, "schema_version": HANDOFF_SCHEMA_VERSION}
    data["project_name"] = _clean_string(raw.get("project_name"), "project_name", required=True)
    for key in STRING_KEYS:
        if key == "project_name":
            continue
        text = _clean_string(raw.get(key), key)
        if text:
            data[key] = text
    for key in LIST_KEYS:
        items = _clean_list(raw.get(key), key)
        if items:
            data[key] = items

    warnings: list[str] = []
    extension = None
    if EXTENSION_KEY in raw:
        extension = _clean_extension(raw[EXTENSION_KEY], warnings)

    ignored = tuple(sorted(k for k in raw if k not in FLAT_KEYS and k != EXTENSION_KEY))
    return ValidatedHandoff(
        data=data, extension=extension, ignored_keys=ignored, warnings=tuple(warnings)
    )


# ----------------------------------------------------------- GrafiTalk simulation
