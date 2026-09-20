"""Project context import: validate, preview, confirmed apply into project notes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grafid.core.exceptions import ValidationError
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.project_repository import ProjectRepository
from grafid.handoff.importer import (
    MAX_BLOCK_CHARS,
    apply_context_import,
    notes_fingerprint,
    preview_context_import,
    read_handoff_file,
)
from grafid.handoff.schema import GRAFITALK_MAX_BYTES
from grafid.handoff.validate import HandoffValidationError
from grafid.ipc.import_handlers import handle_apply_context_import, handle_preview_context_import
from grafid.services.project_registry import ProjectRegistryService

TODAY = "2026-09-20"


def handoff(**over) -> dict:
    data = {
        "source": "graf-id",
        "schema_version": "0.1",
        "project_name": "test-project",
        "current_status": "Checkout done; receipt page next.",
        "changes": ["Manual QA completed."],
        "blockers": ["Waiting for the API key"],
        "next_steps": ["Wire the receipt page"],
        "notes": "Client prefers weekly summaries.",
        "files": ["src/a.py", "src/b.py"],
    }
    data.update(over)
    return {k: v for k, v in data.items() if v is not None}


def write(tmp_path: Path, data: object, name: str = "handoff.json") -> Path:
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def notes_of(db_path, project_id: int) -> str | None:
    return ProjectRegistryService(db_path).get_info(str(project_id)).notes


def set_notes(db_path, project_id: int, notes: str | None) -> None:
    with DatabaseConnection(db_path) as conn:
        conn.execute("UPDATE projects SET notes = ? WHERE id = ?", (notes, project_id))
        conn.commit()


def apply(db_path, project_id, path, *, mode="append", confirmed=True, fingerprint=None):
    if fingerprint is None:
        fingerprint = preview_context_import(db_path, project_id, path, today=TODAY).fingerprint
    return apply_context_import(db_path, project_id, path, mode=mode,
                                expected_fingerprint=fingerprint, confirmed=confirmed, today=TODAY)


# --------------------------------------------------------------------- preview


def test_preview_describes_the_import_and_writes_nothing(db_path, project_id: int, tmp_path: Path) -> None:
    set_notes(db_path, project_id, "My own note")
    preview = preview_context_import(db_path, project_id, write(tmp_path, handoff()), today=TODAY)

    assert preview.project_name == "test-project" and preview.name_matches is True
    assert preview.current_notes == "My own note"
    assert preview.block.splitlines()[0] == "Imported handoff (2026-09-20) from test-project"
    for line in ("Status: Checkout done; receipt page next.", "- Manual QA completed.",
                 "- Waiting for the API key", "- Wire the receipt page", "Notes: Client prefers weekly summaries."):
        assert line in preview.block
    assert preview.proposed_notes_append == f"My own note\n\n{preview.block}"
    assert preview.files_not_imported == 2 and "src/a.py" not in preview.block
    assert preview.fits is True and preview.warnings == ()
    assert notes_of(db_path, project_id) == "My own note"  # nothing written


def test_preview_warns_when_the_file_is_for_another_project(db_path, project_id: int, tmp_path: Path) -> None:
    preview = preview_context_import(db_path, project_id, write(tmp_path, handoff(project_name="Other App")))
    assert preview.name_matches is False
    assert any("Other App" in w and "test-project" in w for w in preview.warnings)


def test_unknown_optional_fields_are_ignored_and_reported(db_path, project_id: int, tmp_path: Path) -> None:
    preview = preview_context_import(db_path, project_id, write(tmp_path, handoff(future_field=1, estimated_time="2 days")))
    assert preview.ignored_keys == ("future_field",) and "Estimated time: 2 days" in preview.block


def test_extension_and_hostile_fields_are_never_applied(config_manager, db_path, project_id: int, tmp_path: Path) -> None:
    before = config_manager.config_path.read_bytes() if config_manager.config_path.exists() else b""
    hostile = handoff(
        custom_opener_path="C:/Windows/System32/calc.exe",
        default_project_opener="custom",
        coding_agents=[{"id": "evil", "display_name": "Evil", "executable": "C:/evil.exe"}],
        graf_id={"extension_version": 1, "project": {"name": "x"}, "secret_plan": "exfiltrate"},
    )
    path = write(tmp_path, hostile)
    apply(db_path, project_id, path)
    notes = notes_of(db_path, project_id)
    assert "calc.exe" not in notes and "evil" not in notes.lower() and "exfiltrate" not in notes
    after = config_manager.config_path.read_bytes() if config_manager.config_path.exists() else b""
    assert after == before  # an import can never touch user configuration


def test_unicode_and_large_notes_are_handled(db_path, project_id: int, tmp_path: Path) -> None:
    path = write(tmp_path, handoff(notes="Árvíztűrő tükörfúrógép 日本語 " * 500, changes=["Kosár ✓"]))
    preview = preview_context_import(db_path, project_id, path, today=TODAY)
    assert "Kosár ✓" in preview.block and "Árvíztűrő" in preview.block
    assert len(preview.block) <= MAX_BLOCK_CHARS


# ----------------------------------------------------------------------- apply


def test_apply_requires_explicit_confirmation(db_path, project_id: int, tmp_path: Path) -> None:
    set_notes(db_path, project_id, "keep me")
    with pytest.raises(ValidationError, match="explicit confirmation"):
        apply(db_path, project_id, write(tmp_path, handoff()), confirmed=False)
    assert notes_of(db_path, project_id) == "keep me"


def test_append_is_the_non_destructive_default(db_path, project_id: int, tmp_path: Path) -> None:
    set_notes(db_path, project_id, "First note.\nSecond line.")
    result = apply(db_path, project_id, write(tmp_path, handoff()))
    stored = notes_of(db_path, project_id)
    assert stored == result and stored.startswith("First note.\nSecond line.\n\nImported handoff (2026-09-20)")


def test_import_into_empty_notes_stores_just_the_block(db_path, project_id: int, tmp_path: Path) -> None:
    set_notes(db_path, project_id, None)
    apply(db_path, project_id, write(tmp_path, handoff()))
    assert notes_of(db_path, project_id).startswith("Imported handoff (2026-09-20)")


def test_replace_is_explicit_and_drops_the_old_notes(db_path, project_id: int, tmp_path: Path) -> None:
    set_notes(db_path, project_id, "old text")
    apply(db_path, project_id, write(tmp_path, handoff()), mode="replace")
    stored = notes_of(db_path, project_id)
    assert "old text" not in stored and stored.startswith("Imported handoff")


def test_unknown_mode_is_rejected(db_path, project_id: int, tmp_path: Path) -> None:
    set_notes(db_path, project_id, "safe")
    with pytest.raises(ValidationError, match="Unknown import mode"):
        apply(db_path, project_id, write(tmp_path, handoff()), mode="merge-everything")
    assert notes_of(db_path, project_id) == "safe"


def test_import_is_refused_if_the_notes_changed_since_the_preview(db_path, project_id: int, tmp_path: Path) -> None:
    path = write(tmp_path, handoff())
    set_notes(db_path, project_id, "before")
    fingerprint = preview_context_import(db_path, project_id, path).fingerprint
    set_notes(db_path, project_id, "edited meanwhile")  # the user kept typing
    with pytest.raises(ValidationError, match="changed since the preview"):
        apply(db_path, project_id, path, fingerprint=fingerprint)
    assert notes_of(db_path, project_id) == "edited meanwhile"


def test_overflowing_the_notes_limit_is_rejected_without_changes(db_path, project_id: int, tmp_path: Path) -> None:
    existing = "x" * 3900
    set_notes(db_path, project_id, existing)
    path = write(tmp_path, handoff())
    preview = preview_context_import(db_path, project_id, path, today=TODAY)
    assert preview.fits is False and any("limit" in w for w in preview.warnings)
    with pytest.raises(ValidationError, match="too long"):
        apply(db_path, project_id, path)
    assert notes_of(db_path, project_id) == existing
    apply(db_path, project_id, path, mode="replace")  # replacing still works
    assert notes_of(db_path, project_id).startswith("Imported handoff")


def test_a_failure_inside_the_transaction_rolls_everything_back(
    db_path, project_id: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_notes(db_path, project_id, "original")
    path = write(tmp_path, handoff())
    fingerprint = preview_context_import(db_path, project_id, path).fingerprint
    real = ProjectRepository.update_metadata

    def write_then_explode(self, project_id, **kwargs):  # noqa: ANN001
        real(self, project_id, **kwargs)  # the UPDATE really happens...
        raise RuntimeError("disk error while finishing the import")  # ...then fails

    monkeypatch.setattr(ProjectRepository, "update_metadata", write_then_explode)
    with pytest.raises(RuntimeError):
        apply_context_import(db_path, project_id, path, mode="append",
                             expected_fingerprint=fingerprint, confirmed=True)
    monkeypatch.undo()
    assert notes_of(db_path, project_id) == "original"  # rolled back, not half-applied


def test_unknown_project_is_rejected(db_path, project_id: int, tmp_path: Path) -> None:
    path = write(tmp_path, handoff())
    with pytest.raises(ValidationError):
        preview_context_import(db_path, 9999, path)
    with pytest.raises(ValidationError, match="not found"):
        apply_context_import(db_path, 9999, path, mode="append", expected_fingerprint="x", confirmed=True)


def test_fingerprint_is_stable_and_distinguishes_notes() -> None:
    assert notes_fingerprint("a") == notes_fingerprint("a") != notes_fingerprint("b")
    assert notes_fingerprint(None) == notes_fingerprint("")


# ------------------------------------------------- malformed / hostile input


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "not valid JSON"),
        ("[1, 2, 3]", "must be a JSON object"),
        ("", "empty"),
        (json.dumps(handoff(schema_version="0.2")), "Unsupported schema_version"),
        (json.dumps(handoff(source="grafitalk")), "Unsupported source"),
        (json.dumps({k: v for k, v in handoff().items() if k != "project_name"}), "project_name"),
        (json.dumps(handoff(changes="not a list")), "changes"),
        (json.dumps(handoff(notes={"a": 1})), "notes"),
    ],
)
def test_malformed_files_are_rejected_and_nothing_is_written(db_path, project_id, tmp_path, content, message) -> None:
    set_notes(db_path, project_id, "untouched")
    path = write(tmp_path, content)
    with pytest.raises(HandoffValidationError, match=message):
        preview_context_import(db_path, project_id, path)
    with pytest.raises(HandoffValidationError):
        apply_context_import(db_path, project_id, path, mode="append", expected_fingerprint="x", confirmed=True)
    assert notes_of(db_path, project_id) == "untouched"


def test_corrupted_bytes_are_rejected(db_path, project_id: int, tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff\xfe\x00\x81garbage")
    with pytest.raises(HandoffValidationError):
        preview_context_import(db_path, project_id, path)


def test_oversized_file_is_rejected_before_it_is_read(tmp_path: Path) -> None:
    path = tmp_path / "huge.json"
    path.write_bytes(b" " * (GRAFITALK_MAX_BYTES + 1))
    with pytest.raises(HandoffValidationError, match="too large"):
        read_handoff_file(path)


def test_only_regular_json_files_are_accepted(tmp_path: Path) -> None:
    folder = tmp_path / "folder.json"
    folder.mkdir()
    with pytest.raises(HandoffValidationError, match="not a folder"):
        read_handoff_file(folder)
    with pytest.raises(HandoffValidationError, match="not found"):
        read_handoff_file(tmp_path / "missing.json")
    other = tmp_path / "notes.txt"
    other.write_text("{}", encoding="utf-8")
    with pytest.raises(HandoffValidationError, match=r"\.json"):
        read_handoff_file(other)


def test_exported_handoffs_import_back(db_path, project_id: int, tmp_path: Path) -> None:
    """Round trip: what Graf-Id exports, Graf-Id can import (lean and full JSON)."""
    from grafid.services.project_export import export_to_path

    for fmt in ("handoff", "json"):
        target = tmp_path / f"{fmt}.json"
        export_to_path(db_path, project_id, target, fmt)
        preview = preview_context_import(db_path, project_id, target, today=TODAY)
        assert preview.name_matches and preview.fits


# ------------------------------------------------------------------------- IPC


def test_ipc_preview_then_confirmed_apply(config_manager, db_path, project_id: int, tmp_path: Path) -> None:
    from grafid.services.runtime import reset_runtime_cache

    reset_runtime_cache()
    path = write(tmp_path, handoff())
    preview = handle_preview_context_import(project_id, str(path), config_manager=config_manager)
    assert preview.ok is True, preview
    fingerprint = preview.data["fingerprint"]

    refused = handle_apply_context_import(project_id, str(path), mode="append", fingerprint=fingerprint,
                                          confirmed=False, config_manager=config_manager)
    assert refused.ok is False and notes_of(db_path, project_id) is None

    applied = handle_apply_context_import(project_id, str(path), mode="append", fingerprint=fingerprint,
                                          confirmed=True, config_manager=config_manager)
    assert applied.ok is True and "Imported handoff" in notes_of(db_path, project_id)


def test_ipc_reports_validation_problems(config_manager, db_path, project_id: int, tmp_path: Path) -> None:
    from grafid.services.runtime import reset_runtime_cache

    reset_runtime_cache()
    bad = write(tmp_path, "{oops")
    response = handle_preview_context_import(project_id, str(bad), config_manager=config_manager)
    assert response.ok is False and response.error.code == "validation_error"
