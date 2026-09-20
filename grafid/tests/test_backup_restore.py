"""Backup / restore: round-trip, transactional safety, resource limits, config safety."""

from __future__ import annotations

import json
import os
import sqlite3
import zipfile
from pathlib import Path

import pytest

from grafid.core.exceptions import DatabaseError, ValidationError
from grafid.ipc.backup_handlers import handle_create_backup, handle_restore_backup
from grafid.services import portability
from grafid.services.db_init import DatabaseInitService
from grafid.services.portability import (
    BUNDLE_CONFIG_NAME,
    BUNDLE_DB_NAME,
    MANIFEST_NAME,
    export_bundle,
    import_bundle,
)
from grafid.services.project_registry import ProjectRegistryService


def project_names(db: Path) -> list[str]:
    conn = sqlite3.connect(db)
    try:
        return sorted(r[0] for r in conn.execute("SELECT name FROM projects"))
    finally:
        conn.close()


def make_data_dir(root: Path, name: str, projects: list[str]) -> Path:
    """A fresh, valid Graf-Id database with the given projects."""
    data = root / name
    data.mkdir()
    db = data / BUNDLE_DB_NAME
    DatabaseInitService(db).initialize(verify=False)
    registry = ProjectRegistryService(db)
    for project in projects:
        folder = root / f"{name}-{project}"
        folder.mkdir()
        registry.add(project, str(folder))
    return data


def snapshot_bytes(path: Path) -> bytes:
    return path.read_bytes()


@pytest.fixture
def live(tmp_path: Path) -> Path:
    return make_data_dir(tmp_path, "live", ["alpha", "bravo"])


@pytest.fixture
def backup_zip(tmp_path: Path) -> Path:
    source = make_data_dir(tmp_path, "source", ["one", "two", "three"])
    return export_bundle(
        db_path=source / BUNDLE_DB_NAME, config_path=source / BUNDLE_CONFIG_NAME,
        output_zip=tmp_path / "backup.zip",
    )


def rewrite_zip(src: Path, dst: Path, *, replace: dict[str, bytes] | None = None,
                add: dict[str, bytes] | None = None, drop: tuple[str, ...] = ()) -> Path:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            if name in drop:
                continue
            zout.writestr(name, (replace or {}).get(name, zin.read(name)))
        for name, data in (add or {}).items():
            zout.writestr(name, data)
    return dst


def no_leftovers(config_dir: Path) -> None:
    stray = [p.name for p in config_dir.iterdir() if p.name.startswith(".graf-id-restore-")]
    assert stray == []


# ------------------------------------------------------------------ round trip


def test_backup_restore_round_trip_into_a_fresh_folder(backup_zip: Path, tmp_path: Path) -> None:
    dest = tmp_path / "fresh"
    result = import_bundle(zip_path=backup_zip, config_dir=dest)
    assert result.project_count == 3 and result.pre_restore_backup is None
    assert project_names(dest / BUNDLE_DB_NAME) == ["one", "three", "two"]
    no_leftovers(dest)


def test_backup_contains_only_known_members_and_a_valid_manifest(backup_zip: Path) -> None:
    with zipfile.ZipFile(backup_zip) as zf:
        assert sorted(zf.namelist()) == ["README.md", "graf-id.db", "grafid-export.json"]
        manifest = json.loads(zf.read(MANIFEST_NAME))
    assert manifest["project_count"] == 3 and manifest["contains_settings"] is False
    assert manifest["app_version"] == "1.0.0"


def test_backup_is_a_consistent_snapshot_even_with_an_open_writer(tmp_path: Path) -> None:
    data = make_data_dir(tmp_path, "busy", ["a", "b"])
    db = data / BUNDLE_DB_NAME
    writer = sqlite3.connect(db)
    writer.execute("BEGIN IMMEDIATE")  # an uncommitted write must not leak into the backup
    writer.execute("UPDATE projects SET name = 'HALF-WRITTEN' WHERE name = 'a'")
    zip_path = tmp_path / "busy.zip"
    try:
        # A raw file copy would race with this open transaction; the SQLite backup API
        # reads a consistent committed state.
        try:
            export_bundle(db_path=db, config_path=data / "config.json", output_zip=zip_path)
        except DatabaseError:
            pytest.skip("SQLite refused a snapshot while a writer held the lock")
    finally:
        writer.rollback()
        writer.close()
    dest = tmp_path / "out"
    import_bundle(zip_path=zip_path, config_dir=dest)
    assert "HALF-WRITTEN" not in project_names(dest / BUNDLE_DB_NAME)


def test_unicode_and_spaced_paths_work(tmp_path: Path) -> None:
    data = make_data_dir(tmp_path, "adat mappa é", ["kosár"])
    zip_path = tmp_path / "mentés ő" / "backup file.zip"
    export_bundle(db_path=data / BUNDLE_DB_NAME, config_path=data / "config.json", output_zip=zip_path)
    dest = tmp_path / "vissza állít"
    import_bundle(zip_path=zip_path, config_dir=dest)
    assert project_names(dest / BUNDLE_DB_NAME) == ["kosár"]


# --------------------------------------------------- restore over existing data


def test_restore_replaces_the_database_and_keeps_a_safety_copy(live: Path, backup_zip: Path) -> None:
    result = import_bundle(zip_path=backup_zip, config_dir=live, replace=True)
    assert project_names(live / BUNDLE_DB_NAME) == ["one", "three", "two"]
    assert result.pre_restore_backup is not None
    assert result.pre_restore_backup.parent == live / "backups"
    assert project_names(result.pre_restore_backup) == ["alpha", "bravo"]
    assert sqlite3.connect(result.pre_restore_backup).execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    no_leftovers(live)


def test_restore_without_replace_refuses_and_touches_nothing(live: Path, backup_zip: Path) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    with pytest.raises(ValidationError, match="already exists"):
        import_bundle(zip_path=backup_zip, config_dir=live)
    assert snapshot_bytes(live / BUNDLE_DB_NAME) == before and not (live / "backups").exists()


# ------------------------------------ atomicity: failures never damage live data


def assert_untouched(live: Path, before: bytes) -> None:
    assert snapshot_bytes(live / BUNDLE_DB_NAME) == before
    assert project_names(live / BUNDLE_DB_NAME) == ["alpha", "bravo"]
    no_leftovers(live)


def test_garbage_database_member_rolls_back_and_leaves_live_data_byte_identical(
    live: Path, backup_zip: Path, tmp_path: Path
) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    bad = rewrite_zip(backup_zip, tmp_path / "bad.zip", replace={BUNDLE_DB_NAME: b"NOT A DATABASE" * 500})
    with pytest.raises(DatabaseError):
        import_bundle(zip_path=bad, config_dir=live, replace=True)
    assert_untouched(live, before)
    assert not (live / "backups").exists()  # failed before anything was changed


def test_truncated_database_fails_integrity_and_rolls_back(live: Path, backup_zip: Path, tmp_path: Path) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    with zipfile.ZipFile(backup_zip) as zf:
        good = zf.read(BUNDLE_DB_NAME)
    bad = rewrite_zip(backup_zip, tmp_path / "trunc.zip", replace={BUNDLE_DB_NAME: good[: len(good) // 2]})
    with pytest.raises(DatabaseError):
        import_bundle(zip_path=bad, config_dir=live, replace=True)
    assert_untouched(live, before)


def test_corrupted_zip_is_rejected_cleanly(live: Path, tmp_path: Path) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"PK\x03\x04 this is not really a zip" * 20)
    with pytest.raises(ValidationError, match="not a valid zip"):
        import_bundle(zip_path=junk, config_dir=live, replace=True)
    assert_untouched(live, before)


def test_newer_schema_database_is_rejected_before_anything_changes(
    live: Path, backup_zip: Path, tmp_path: Path
) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    with zipfile.ZipFile(backup_zip) as zf:
        data = zf.read(BUNDLE_DB_NAME)
    tampered = tmp_path / "newer.db"
    tampered.write_bytes(data)
    conn = sqlite3.connect(tampered)
    conn.execute("UPDATE schema_meta SET value = '999' WHERE key = 'version'")
    conn.commit(); conn.close()
    bad = rewrite_zip(backup_zip, tmp_path / "newer.zip", replace={BUNDLE_DB_NAME: tampered.read_bytes()})
    with pytest.raises(ValidationError, match="newer"):
        import_bundle(zip_path=bad, config_dir=live, replace=True)
    assert_untouched(live, before)


def test_failed_migration_on_the_temp_copy_rolls_back(
    live: Path, backup_zip: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)

    def boom(self, *, verify: bool = True):  # noqa: ANN001
        raise DatabaseError("simulated migration failure")

    monkeypatch.setattr(DatabaseInitService, "initialize", boom)
    with pytest.raises(DatabaseError, match="simulated migration failure"):
        import_bundle(zip_path=backup_zip, config_dir=live, replace=True)
    assert_untouched(live, before)


def test_failure_of_the_final_swap_keeps_live_data_and_cleans_staging(
    live: Path, backup_zip: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    real_replace = os.replace

    def failing_replace(src, dst, *a, **k):  # noqa: ANN001
        if str(dst).endswith(BUNDLE_DB_NAME):
            raise PermissionError("file is locked by another process")
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(portability.os, "replace", failing_replace)
    with pytest.raises(ValidationError, match="could not replace the database"):
        import_bundle(zip_path=backup_zip, config_dir=live, replace=True)
    assert snapshot_bytes(live / BUNDLE_DB_NAME) == before
    no_leftovers(live)


def test_a_damaged_live_database_can_still_be_replaced_and_is_preserved_raw(
    live: Path, backup_zip: Path
) -> None:
    damaged = b"CORRUPTED LIVE DATABASE" * 100
    (live / BUNDLE_DB_NAME).write_bytes(damaged)
    result = import_bundle(zip_path=backup_zip, config_dir=live, replace=True)
    assert project_names(live / BUNDLE_DB_NAME) == ["one", "three", "two"]
    assert result.pre_restore_backup is not None and result.pre_restore_backup.read_bytes() == damaged


# ------------------------------------------------------------- resource limits


def test_unexpected_or_traversal_entries_are_rejected(live: Path, backup_zip: Path, tmp_path: Path) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    for name in ("../evil.txt", "extra.bin", "sub/graf-id.db", "/abs.txt"):
        bad = rewrite_zip(backup_zip, tmp_path / "x.zip", add={name: b"x"})
        with pytest.raises(ValidationError, match="unexpected entry"):
            import_bundle(zip_path=bad, config_dir=live, replace=True)
    assert_untouched(live, before)


def test_compression_bomb_is_rejected_without_extracting(live: Path, backup_zip: Path, tmp_path: Path) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    bomb = rewrite_zip(backup_zip, tmp_path / "bomb.zip", replace={BUNDLE_DB_NAME: b"\0" * (64 * 1024 * 1024)})
    assert bomb.stat().st_size < 1024 * 1024
    with pytest.raises(ValidationError, match="compression ratio"):
        import_bundle(zip_path=bomb, config_dir=live, replace=True)
    assert_untouched(live, before)


def test_member_size_limit_is_enforced(live: Path, backup_zip: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    monkeypatch.setattr(portability, "MAX_MEMBER_BYTES", 1024)
    with pytest.raises(ValidationError, match="too large"):
        import_bundle(zip_path=backup_zip, config_dir=live, replace=True)
    assert_untouched(live, before)


def test_real_decompressed_size_is_capped_even_if_the_header_lies(
    live: Path, backup_zip: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Streaming cap: a forged header size cannot smuggle in a large file."""
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    monkeypatch.setattr(portability, "MAX_MEMBER_BYTES", 4096)
    # Skip the header-based checks entirely: only the streaming cap is left to stop it.
    monkeypatch.setattr(portability, "_check_archive_limits", lambda zf: {i.filename: i for i in zf.infolist()})
    with pytest.raises(ValidationError, match="too large"):
        import_bundle(zip_path=backup_zip, config_dir=live, replace=True)
    assert_untouched(live, before)


@pytest.mark.parametrize(
    ("manifest", "message"),
    [(b"{bad", "malformed"), (b"[]", "JSON object"), (json.dumps({"schema_version": "x"}).encode(), "integer")],
)
def test_bad_manifest_is_rejected_before_changes(live, backup_zip, tmp_path, manifest, message) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    bad = rewrite_zip(backup_zip, tmp_path / "m.zip", replace={MANIFEST_NAME: manifest})
    with pytest.raises(ValidationError, match=message):
        import_bundle(zip_path=bad, config_dir=live, replace=True)
    assert_untouched(live, before)


# --------------------------------------------------------------- config safety

BUNDLE_SETTINGS = {
    "log_level": "DEBUG",
    "usage_journal": True,
    "compact_mode": True,
    "default_project_opener": "agent:evil",
    "custom_opener_path": "C:/Windows/System32/calc.exe",
    "coding_agents": [{"id": "evil", "display_name": "Evil", "executable": "C:/evil.exe"}],
    "builtin_agents": {"claude-code": {"executable": "C:/evil.exe"}},
    "python_interpreter_custom_path": "C:/evil/python.exe",
}


def test_backup_never_includes_settings_unless_asked_and_then_only_the_allowlist(tmp_path: Path) -> None:
    data = make_data_dir(tmp_path, "cfg", ["a"])
    (data / BUNDLE_CONFIG_NAME).write_text(json.dumps(BUNDLE_SETTINGS), encoding="utf-8")
    plain = export_bundle(db_path=data / BUNDLE_DB_NAME, config_path=data / BUNDLE_CONFIG_NAME,
                          output_zip=tmp_path / "plain.zip")
    assert BUNDLE_CONFIG_NAME not in zipfile.ZipFile(plain).namelist()
    with_settings = export_bundle(db_path=data / BUNDLE_DB_NAME, config_path=data / BUNDLE_CONFIG_NAME,
                                  output_zip=tmp_path / "cfg.zip", include_settings=True)
    stored = json.loads(zipfile.ZipFile(with_settings).read(BUNDLE_CONFIG_NAME))
    assert set(stored) == {"log_level", "usage_journal", "compact_mode", "default_project_opener"}
    assert stored["default_project_opener"] == "system"


def test_restore_never_touches_existing_config_by_default(live: Path, backup_zip: Path, tmp_path: Path) -> None:
    mine = json.dumps({"log_level": "WARNING", "compact_mode": False}, indent=2)
    (live / BUNDLE_CONFIG_NAME).write_text(mine, encoding="utf-8")
    hostile = rewrite_zip(backup_zip, tmp_path / "h.zip",
                          add={BUNDLE_CONFIG_NAME: json.dumps(BUNDLE_SETTINGS).encode()})
    import_bundle(zip_path=hostile, config_dir=live, replace=True)
    assert (live / BUNDLE_CONFIG_NAME).read_text(encoding="utf-8") == mine


def test_settings_restore_is_opt_in_allowlisted_and_merges_without_clobbering(
    live: Path, backup_zip: Path, tmp_path: Path
) -> None:
    (live / BUNDLE_CONFIG_NAME).write_text(
        json.dumps({"python_interpreter_custom_path": "C:/mine/python.exe", "log_level": "INFO"}), encoding="utf-8")
    hostile = rewrite_zip(backup_zip, tmp_path / "h.zip",
                          add={BUNDLE_CONFIG_NAME: json.dumps(BUNDLE_SETTINGS).encode()})
    result = import_bundle(zip_path=hostile, config_dir=live, replace=True, restore_settings=True)

    merged = json.loads((live / BUNDLE_CONFIG_NAME).read_text(encoding="utf-8"))
    assert merged["log_level"] == "DEBUG" and merged["compact_mode"] is True
    assert merged["default_project_opener"] == "system"          # agent opener reset
    assert merged["python_interpreter_custom_path"] == "C:/mine/python.exe"  # untouched
    for forbidden in ("custom_opener_path", "coding_agents", "builtin_agents"):
        assert forbidden not in merged
    assert "log_level" in result.settings_restored


def test_malformed_settings_are_rejected_before_the_database_is_touched(
    live: Path, backup_zip: Path, tmp_path: Path
) -> None:
    before = snapshot_bytes(live / BUNDLE_DB_NAME)
    bad = rewrite_zip(backup_zip, tmp_path / "s.zip", add={BUNDLE_CONFIG_NAME: b"{not json"})
    with pytest.raises(ValidationError):
        import_bundle(zip_path=bad, config_dir=live, replace=True, restore_settings=True)
    assert_untouched(live, before)


# ------------------------------------------------------------------------ IPC


def test_ipc_create_and_restore_backup(config_manager, db_path, project_id: int, tmp_path: Path) -> None:
    created = handle_create_backup(str(tmp_path / "ipc-backup"), config_manager=config_manager)
    assert created.ok is True, created
    zip_path = Path(created.data["path"])
    assert zip_path.suffix == ".zip" and zip_path.is_file()

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE projects SET name = 'changed-after-backup'")
        conn.commit()
    finally:
        conn.close()  # (a `with sqlite3.connect()` block would leave it open on Windows)
    restored = handle_restore_backup(str(zip_path), config_manager=config_manager)
    assert restored.ok is True, restored
    assert restored.data["project_count"] == 1
    assert project_names(db_path) == ["test-project"]
    assert Path(restored.data["pre_restore_backup"]).is_file()


@pytest.mark.parametrize("arg", ["", "   "])
def test_ipc_rejects_empty_paths(config_manager, db_path, arg: str) -> None:
    assert handle_create_backup(arg, config_manager=config_manager).ok is False
    assert handle_restore_backup(arg, config_manager=config_manager).ok is False


def test_ipc_restore_of_a_bad_file_reports_an_error_and_keeps_data(
    config_manager, db_path, project_id: int, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"nope")
    before = snapshot_bytes(db_path)
    response = handle_restore_backup(str(bad), config_manager=config_manager)
    assert response.ok is False and "zip" in response.error.message.lower()
    assert snapshot_bytes(db_path) == before
