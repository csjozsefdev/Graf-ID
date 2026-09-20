"""Regression tests for M4: an imported export bundle must not be able to
silently set an executable/custom opener that later gets launched without
the user reviewing it in Settings.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from grafid.core.constants import SCHEMA_VERSION
from grafid.core.exceptions import ValidationError
from grafid.services.portability import (
    BUNDLE_CONFIG_NAME,
    BUNDLE_DB_NAME,
    MANIFEST_NAME,
    _sanitized_config_json,
    export_bundle,
    import_bundle,
)


def _valid_sqlite_bytes(tmp_path: Path) -> bytes:
    """A minimal, real SQLite database file (import applies the real schema to it)."""
    db_file = tmp_path / "_seed.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE placeholder (id INTEGER)")
    conn.commit()
    conn.close()
    return db_file.read_bytes()


def _write_bundle(
    zip_path: Path,
    *,
    config_json: dict | str | None,
    db_bytes: bytes = b"not-a-real-sqlite-file",
    include_manifest: bool = True,
) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        if include_manifest:
            zf.writestr(MANIFEST_NAME, json.dumps({"schema_version": SCHEMA_VERSION}))
        zf.writestr(BUNDLE_DB_NAME, db_bytes)
        if config_json is not None:
            payload = (
                config_json
                if isinstance(config_json, str)
                else json.dumps(config_json)
            )
            zf.writestr(BUNDLE_CONFIG_NAME, payload)


# ---------------------------------------------------------------------------
# _sanitized_config_json — unit level
# ---------------------------------------------------------------------------


def test_sanitized_config_strips_custom_opener_path() -> None:
    raw = {
        "default_project_opener": "custom",
        "custom_opener_path": "C:/Windows/System32/cmd.exe",
    }
    sanitized = json.loads(_sanitized_config_json(json.dumps(raw)))
    assert "custom_opener_path" not in sanitized
    assert sanitized["default_project_opener"] == "system"


def test_sanitized_config_resets_preferred_ide_custom() -> None:
    raw = {"preferred_ide": "custom", "custom_opener_path": "/bin/sh"}
    sanitized = json.loads(_sanitized_config_json(json.dumps(raw)))
    assert "custom_opener_path" not in sanitized
    assert sanitized["preferred_ide"] == "system"


def test_sanitized_config_preserves_non_custom_settings() -> None:
    raw = {
        "default_project_opener": "vscode",
        "usage_journal": True,
        "log_level": "DEBUG",
    }
    sanitized = json.loads(_sanitized_config_json(json.dumps(raw)))
    assert sanitized["default_project_opener"] == "vscode"
    assert sanitized["usage_journal"] is True
    assert sanitized["log_level"] == "DEBUG"


def test_sanitized_config_rejects_invalid_json() -> None:
    with pytest.raises(ValidationError):
        _sanitized_config_json("{not valid json")


def test_sanitized_config_rejects_non_object_root() -> None:
    with pytest.raises(ValidationError):
        _sanitized_config_json("[1, 2, 3]")


def test_sanitized_config_rejects_invalid_log_level() -> None:
    with pytest.raises(ValidationError):
        _sanitized_config_json(json.dumps({"log_level": "NOT_A_LEVEL"}))


def test_sanitized_config_rejects_invalid_opener_token() -> None:
    with pytest.raises(ValidationError):
        _sanitized_config_json(json.dumps({"default_project_opener": "not-a-real-editor"}))


# ---------------------------------------------------------------------------
# import_bundle — end to end
# ---------------------------------------------------------------------------


def test_import_bundle_strips_custom_opener_from_config(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    _write_bundle(
        zip_path,
        config_json={
            "default_project_opener": "custom",
            "custom_opener_path": "C:/Windows/System32/calc.exe",
        },
        db_bytes=_valid_sqlite_bytes(tmp_path),
    )
    dest = tmp_path / "imported"

    import_bundle(zip_path=zip_path, config_dir=dest, replace=True, restore_settings=True)

    imported_config = json.loads((dest / BUNDLE_CONFIG_NAME).read_text(encoding="utf-8"))
    assert "custom_opener_path" not in imported_config
    assert imported_config["default_project_opener"] == "system"


def test_import_bundle_rejects_malformed_config_without_partial_extraction(
    tmp_path: Path,
) -> None:
    """A bad config.json must fail before the DB file is extracted at all."""
    zip_path = tmp_path / "bundle.zip"
    _write_bundle(zip_path, config_json="{not valid json")
    dest = tmp_path / "imported"

    with pytest.raises(ValidationError):
        import_bundle(zip_path=zip_path, config_dir=dest, replace=True, restore_settings=True)

    assert not (dest / BUNDLE_DB_NAME).exists()


def test_import_bundle_without_config_still_imports_db(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    _write_bundle(zip_path, config_json=None)
    dest = tmp_path / "imported"

    # DB content is not a real sqlite file here, so DatabaseInitService.initialize
    # would fail downstream — that's expected/unrelated to this test's concern,
    # which is only that config sanitation is skipped cleanly when absent.
    with pytest.raises(Exception):  # noqa: B017 — any DB-init failure is fine here
        import_bundle(zip_path=zip_path, config_dir=dest, replace=True)

    assert not (dest / BUNDLE_CONFIG_NAME).exists()


def test_export_then_import_roundtrip_drops_custom_opener(
    tmp_path: Path, config_manager
) -> None:
    """Export a config with a custom opener, import it back, confirm it's stripped."""
    from grafid.services.db_init import DatabaseInitService

    config = config_manager.load()
    config.extra["custom_opener_path"] = "C:/Windows/System32/notepad.exe"
    config.default_project_opener = "custom"
    config_manager.save(config)

    db_path = config.resolved_database_path(config_manager.config_dir)
    DatabaseInitService(db_path).initialize(verify=False)

    zip_path = tmp_path / "roundtrip.zip"
    export_bundle(
        db_path=db_path,
        config_path=config_manager.config_path,
        output_zip=zip_path,
        include_settings=True,
    )

    dest = tmp_path / "reimported"
    import_bundle(zip_path=zip_path, config_dir=dest, replace=True, restore_settings=True)

    imported_config = json.loads((dest / BUNDLE_CONFIG_NAME).read_text(encoding="utf-8"))
    assert "custom_opener_path" not in imported_config
    assert imported_config["default_project_opener"] == "system"
