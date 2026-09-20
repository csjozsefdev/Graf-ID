"""Import a Graf-Id / GrafiTalk handoff file into a project's notes.

1.0 scope, deliberately small and safe:

- validate the file against the handoff contract (schema, version, limits);
- PREVIEW exactly what would be stored, without writing anything;
- apply only with explicit confirmation, into the EXISTING project notes field
  (no new database schema);
- never overwrite silently: the default is to APPEND a dated block, replacing
  is an explicit choice, and the write is refused if the notes changed since
  the preview (fingerprint), so the user never loses text they did not see.

Only the plain contract fields are read. File paths, the ``graf_id`` extension
and anything executable-looking are never applied.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from grafid.core.exceptions import ProjectError, ValidationError
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.project_repository import ProjectRepository
from grafid.handoff.schema import GRAFITALK_MAX_BYTES
from grafid.handoff.validate import HandoffValidationError, ValidatedHandoff, parse_handoff_bytes
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.project_validation import normalize_notes

ImportMode = Literal["append", "replace"]
VALID_MODES = ("append", "replace")
MAX_BLOCK_CHARS = 2400


def notes_fingerprint(notes: str | None) -> str:
    """Stable digest of the current notes, used to detect changes between preview and apply."""
    return hashlib.sha256((notes or "").encode("utf-8")).hexdigest()[:16]


def read_handoff_file(path: str | Path) -> ValidatedHandoff:
    """Read and validate a handoff file. Size is checked BEFORE reading it into memory."""
    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise HandoffValidationError(f"Handoff file not found: {candidate}") from exc
    if not resolved.is_file():
        raise HandoffValidationError("Choose a handoff .json file, not a folder.")
    if resolved.suffix.lower() != ".json":
        raise HandoffValidationError("Only .json handoff files can be imported.")
    try:
        size = resolved.stat().st_size
        if size > GRAFITALK_MAX_BYTES:
            raise HandoffValidationError(
                f"Handoff file is too large ({size} bytes; limit {GRAFITALK_MAX_BYTES})."
            )
        with resolved.open("rb") as handle:
            raw = handle.read(GRAFITALK_MAX_BYTES + 1)
    except OSError as exc:
        raise HandoffValidationError(f"Could not read the handoff file: {exc}") from exc
    return parse_handoff_bytes(raw)


def _bullets(label: str, items: list[str]) -> list[str]:
    return [f"{label}:", *[f"- {item}" for item in items]] if items else []


def render_import_block(handoff: dict[str, Any], *, stamp: str) -> str:
    """The text that gets stored in the project notes (compact, human-readable)."""
    lines = [f"Imported handoff ({stamp}) from {handoff['project_name']}"]
    if handoff.get("current_status"):
        lines.append(f"Status: {handoff['current_status']}")
    lines += _bullets("Changes", handoff.get("changes", []))
    lines += _bullets("Blockers", handoff.get("blockers", []))
    lines += _bullets("Next steps", handoff.get("next_steps", []))
    if handoff.get("estimated_time"):
        lines.append(f"Estimated time: {handoff['estimated_time']}")
    if handoff.get("notes"):
        lines.append(f"Notes: {handoff['notes']}")
    text = "\n".join(lines)
    if len(text) > MAX_BLOCK_CHARS:
        text = text[: MAX_BLOCK_CHARS - 1].rstrip() + "…"
    return text


def _compose(existing: str | None, block: str, mode: str) -> str:
    if mode == "replace" or not (existing and existing.strip()):
        return block
    return f"{existing.rstrip()}\n\n{block}"


def _normalize_mode(mode: str) -> ImportMode:
    if mode not in VALID_MODES:
        raise ValidationError(f"Unknown import mode {mode!r}: use append or replace.")
    return mode  # type: ignore[return-value]


@dataclass(frozen=True)
class ImportPreview:
    project_id: int
    project_name: str
    handoff_project_name: str
    name_matches: bool
    current_notes: str | None
    block: str
    proposed_notes_append: str
    fingerprint: str
    warnings: tuple[str, ...]
    ignored_keys: tuple[str, ...]
    fits: bool
    files_not_imported: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "handoff_project_name": self.handoff_project_name,
            "name_matches": self.name_matches,
            "current_notes": self.current_notes,
            "block": self.block,
            "proposed_notes_append": self.proposed_notes_append,
            "fingerprint": self.fingerprint,
            "warnings": list(self.warnings),
            "ignored_keys": list(self.ignored_keys),
            "fits": self.fits,
            "files_not_imported": self.files_not_imported,
        }


def _stamp(today: str | None) -> str:
    from datetime import UTC, datetime

    return today or datetime.now(UTC).strftime("%Y-%m-%d")


def preview_context_import(
    db_path: Path, project_id: int, file_path: str | Path, *, today: str | None = None
) -> ImportPreview:
    """Validate the file and describe what applying it would do. Writes nothing."""
    validated = read_handoff_file(file_path)
    try:
        record = ProjectRegistryService(db_path).get_info(str(project_id))
    except ProjectError as exc:
        raise ValidationError(str(exc)) from exc

    handoff = validated.data
    block = render_import_block(handoff, stamp=_stamp(today))
    appended = _compose(record.notes, block, "append")
    warnings = list(validated.warnings)
    name_matches = str(handoff["project_name"]).strip().lower() == str(record.name).strip().lower()
    if not name_matches:
        warnings.append(
            f"The file is for '{handoff['project_name']}', not '{record.name}'. "
            "Check it is the right project before importing."
        )
    try:
        normalize_notes(appended)
        fits = True
    except ValidationError:
        fits = False
        warnings.append(
            "Appending would exceed the project notes limit; import as a replacement "
            "or shorten your existing notes first."
        )
    return ImportPreview(
        project_id=int(record.id),
        project_name=str(record.name),
        handoff_project_name=str(handoff["project_name"]),
        name_matches=name_matches,
        current_notes=record.notes,
        block=block,
        proposed_notes_append=appended,
        fingerprint=notes_fingerprint(record.notes),
        warnings=tuple(warnings),
        ignored_keys=validated.ignored_keys,
        fits=fits,
        files_not_imported=len(handoff.get("files", [])),
    )


def apply_context_import(
    db_path: Path,
    project_id: int,
    file_path: str | Path,
    *,
    mode: str,
    expected_fingerprint: str,
    confirmed: bool,
    today: str | None = None,
) -> str:
    """
    Store the imported block in the project's notes and return the new notes.

    Refuses unless ``confirmed``; re-validates the file (the preview is never
    trusted); and runs in ONE transaction that first checks the notes still
    match ``expected_fingerprint`` — any failure leaves the project untouched.
    """
    if not confirmed:
        raise ValidationError("Import needs explicit confirmation.")
    chosen = _normalize_mode(mode)
    validated = read_handoff_file(file_path)
    block = render_import_block(validated.data, stamp=_stamp(today))

    with DatabaseConnection(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            repo = ProjectRepository(conn)
            current = repo.get_by_id(project_id)
            if current is None:
                raise ValidationError(f"Project not found: {project_id}")
            if notes_fingerprint(current.notes) != expected_fingerprint:
                raise ValidationError(
                    "The project notes changed since the preview. Preview the import again."
                )
            new_notes = normalize_notes(_compose(current.notes, block, chosen))
            repo.update_metadata(project_id, notes=new_notes)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return new_notes or ""
