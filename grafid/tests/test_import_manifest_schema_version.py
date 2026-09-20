"""Milestone 5B regression tests: real audit finding L2.

The original finding: `isinstance(schema, int) and schema > SCHEMA_VERSION`
in portability.import_bundle silently skips the whole check whenever
schema_version is missing or not a plain int — no error, the import just
proceeds unverified. Fixed with explicit presence/type/range validation
(_validate_manifest_schema_version) that always raises ValidationError for
anything that isn't a genuine, in-range integer, never falls through silently.
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
    BUNDLE_DB_NAME,
    MANIFEST_NAME,
    MIN_SUPPORTED_SCHEMA_VERSION,
    import_bundle,
)


def _valid_sqlite_bytes(tmp_path: Path, name: str) -> bytes:
    db_file = tmp_path / name
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE placeholder (id INTEGER)")
    conn.commit()
    conn.close()
    return db_file.read_bytes()


def _write_bundle(zip_path: Path, *, manifest_body: bytes | None, db_bytes: bytes) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        if manifest_body is not None:
            zf.writestr(MANIFEST_NAME, manifest_body)
        zf.writestr(BUNDLE_DB_NAME, db_bytes)


def _import(tmp_path: Path, zip_name: str, manifest_obj: object) -> None:
    zip_path = tmp_path / zip_name
    body = json.dumps(manifest_obj).encode("utf-8") if not isinstance(manifest_obj, bytes) else manifest_obj
    _write_bundle(
        zip_path,
        manifest_body=body,
        db_bytes=_valid_sqlite_bytes(tmp_path, f"{zip_name}.db"),
    )
    import_bundle(zip_path=zip_path, config_dir=tmp_path / f"{zip_name}-config", replace=True)


def test_supported_integer_schema_version_is_accepted(tmp_path: Path) -> None:
    _import(tmp_path, "ok", {"schema_version": SCHEMA_VERSION})


def test_missing_schema_version_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="missing schema_version"):
        _import(tmp_path, "missing", {"app": "Graf-Id"})


def test_string_schema_version_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="must be an integer"):
        _import(tmp_path, "string", {"schema_version": "12"})


def test_null_schema_version_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="must be an integer"):
        _import(tmp_path, "null", {"schema_version": None})


def test_float_schema_version_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="must be an integer"):
        _import(tmp_path, "float", {"schema_version": 12.0})


def test_bool_schema_version_is_rejected(tmp_path: Path) -> None:
    """bool is a subclass of int in Python — must not silently pass as 1/0."""
    with pytest.raises(ValidationError, match="must be an integer"):
        _import(tmp_path, "bool", {"schema_version": True})


def test_negative_schema_version_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="older than the minimum"):
        _import(tmp_path, "negative", {"schema_version": -1})


def test_too_new_schema_version_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="newer than this app"):
        _import(tmp_path, "toonew", {"schema_version": SCHEMA_VERSION + 1000})


def test_too_old_unsupported_schema_version_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="older than the minimum"):
        _import(tmp_path, "tooold", {"schema_version": MIN_SUPPORTED_SCHEMA_VERSION - 1})


def test_malformed_manifest_json_is_rejected(tmp_path: Path) -> None:
    zip_path = tmp_path / "malformed.zip"
    _write_bundle(
        zip_path,
        manifest_body=b"{not valid json!!!",
        db_bytes=_valid_sqlite_bytes(tmp_path, "malformed.db"),
    )
    with pytest.raises(ValidationError, match="malformed"):
        import_bundle(zip_path=zip_path, config_dir=tmp_path / "malformed-config", replace=True)


def test_manifest_that_is_a_json_array_not_object_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="must be a JSON object"):
        _import(tmp_path, "array", [1, 2, 3])


def test_missing_manifest_file_is_rejected(tmp_path: Path) -> None:
    zip_path = tmp_path / "nomanifest.zip"
    _write_bundle(
        zip_path,
        manifest_body=None,
        db_bytes=_valid_sqlite_bytes(tmp_path, "nomanifest.db"),
    )
    with pytest.raises(ValidationError, match=MANIFEST_NAME):
        import_bundle(zip_path=zip_path, config_dir=tmp_path / "nomanifest-config", replace=True)
