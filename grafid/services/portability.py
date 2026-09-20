"""Backup (export) and restore (import) of the Graf-Id database.

Restore is transactional in effect: nothing the user has is touched until the
incoming database has been fully extracted, size/ratio-checked, integrity
checked and migrated on a temporary copy, and a safety backup of the current
database exists. The switch itself is one atomic file replace.

Settings (config.json) are NEVER overwritten by a restore unless the caller
explicitly opts in, and then only an allowlist of harmless keys is merged.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from grafid import __version__
from grafid.config.coding_agents import (
    BUILTIN_AGENTS_KEY,
    CODING_AGENTS_KEY,
    is_agent_opener_value,
)
from grafid.config.manager import ConfigManager
from grafid.config.preferences import CUSTOM_OPENER_PATH_KEY, DEFAULT_PROJECT_OPENER_KEY
from grafid.core.constants import SCHEMA_VERSION
from grafid.core.exceptions import ConfigError, DatabaseError, ValidationError
from grafid.db.schema import get_schema_version
from grafid.utils.logging_setup import get_logger

logger = get_logger("portability")

EXPORT_SPEC_VERSION = 1
MANIFEST_NAME = "grafid-export.json"
BUNDLE_DB_NAME = "graf-id.db"
BUNDLE_CONFIG_NAME = "config.json"
BUNDLE_README_NAME = "README.md"
ALLOWED_BUNDLE_MEMBERS = frozenset(
    {MANIFEST_NAME, BUNDLE_DB_NAME, BUNDLE_CONFIG_NAME, BUNDLE_README_NAME}
)
# L2: oldest schema version this codebase's migration chain still recognizes
# (grafid.db.schema._migrate_mvp_v9's baseline) — a manifest claiming an
# older version predates any migration path this app can run.
MIN_SUPPORTED_SCHEMA_VERSION = 9

# Resource limits (a backup is untrusted input: it can come from another machine).
MAX_MEMBER_BYTES = 1024 * 1024 * 1024  # 1 GiB per member, enforced while streaming
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200  # only checked for members above RATIO_MIN_BYTES
RATIO_MIN_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_CONFIG_BYTES = 256 * 1024
_CHUNK = 1024 * 1024

# Settings a restore may bring back when explicitly asked to. Everything else in
# the bundled config (custom editor paths, coding agents, interpreter paths...)
# is dropped: it can point at executables and is reviewed in Settings instead.
SETTINGS_ALLOWLIST: tuple[str, ...] = (
    "log_level",
    "usage_journal",
    "debug_timing",
    "compact_mode",
    DEFAULT_PROJECT_OPENER_KEY,
)
PRE_RESTORE_DIRNAME = "backups"


@dataclass(frozen=True)
class RestoreResult:
    database_path: Path
    pre_restore_backup: Path | None
    project_count: int
    settings_restored: tuple[str, ...]


def _export_manifest(*, project_count: int, contains_settings: bool) -> dict[str, object]:
    return {
        "spec_version": EXPORT_SPEC_VERSION,
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "app": "Graf-Id",
        "app_version": __version__,
        "project_count": project_count,
        "contains_settings": contains_settings,
    }


def _sqlite_backup(source: Path, destination: Path) -> None:
    """Consistent copy of a live SQLite database via the online backup API."""
    src = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _allowlisted_settings(text: str) -> dict[str, object]:
    """Validate a bundled config.json and keep only SETTINGS_ALLOWLIST keys."""
    cleaned = json.loads(_sanitized_config_json(text))
    picked = {key: cleaned[key] for key in SETTINGS_ALLOWLIST if key in cleaned}
    opener = picked.get(DEFAULT_PROJECT_OPENER_KEY)
    if isinstance(opener, str) and (opener == "custom" or is_agent_opener_value(opener)):
        picked[DEFAULT_PROJECT_OPENER_KEY] = "system"
    return picked


def export_bundle(
    *,
    db_path: Path,
    config_path: Path,
    output_zip: Path,
    include_settings: bool = False,
) -> Path:
    """
    Create a backup zip: a consistent database snapshot, manifest and readme.

    The database is copied with SQLite's online backup API (safe while the app
    writes). Settings are left out unless ``include_settings`` is set, and then
    only the allowlisted keys are written.
    """
    if not db_path.is_file():
        raise ValidationError(f"Database not found: {db_path}")
    output_zip = output_zip.expanduser().resolve()
    if output_zip.is_dir():
        raise ValidationError(f"Backup path is a directory: {output_zip}")
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="graf-id-backup-", dir=output_zip.parent) as tmp:
        snapshot = Path(tmp) / BUNDLE_DB_NAME
        try:
            _sqlite_backup(db_path, snapshot)
        except sqlite3.Error as exc:
            raise DatabaseError(f"Could not read the database for backup: {exc}") from exc
        with DatabaseConnection_ro(snapshot) as conn:
            version = get_schema_version(conn)
            if version is None or version > SCHEMA_VERSION:
                raise DatabaseError(f"Unsupported schema version in database: {version}")
            project_count = int(conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0])

        settings_json: str | None = None
        if include_settings and config_path.is_file():
            allowed = _allowlisted_settings(config_path.read_text(encoding="utf-8"))
            settings_json = json.dumps(allowed, indent=2) + "\n"

        manifest = _export_manifest(
            project_count=project_count, contains_settings=settings_json is not None
        )
        readme = (
            "# Graf-Id backup\n\n"
            "Restore from Graf-Id: Settings > Data > Restore from backup...\n"
            f"Schema version: {SCHEMA_VERSION}\n"
        )
        staged_zip = Path(tmp) / "backup.zip"
        with zipfile.ZipFile(staged_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(snapshot, BUNDLE_DB_NAME)
            if settings_json is not None:
                zf.writestr(BUNDLE_CONFIG_NAME, settings_json)
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
            zf.writestr(BUNDLE_README_NAME, readme)
        os.replace(staged_zip, output_zip)

    logger.info("Exported backup to %s", output_zip)
    return output_zip


def _read_member_bounded(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    """Read a member while enforcing ``limit`` on the REAL decompressed size."""
    chunks: list[bytes] = []
    total = 0
    with zf.open(info) as handle:
        while True:
            block = handle.read(_CHUNK)
            if not block:
                break
            total += len(block)
            if total > limit:
                raise ValidationError(f"Invalid backup: {info.filename} is too large.")
            chunks.append(block)
    return b"".join(chunks)


def _check_archive_limits(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    members: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in zf.infolist():
        name = info.filename
        if info.is_dir() or name not in ALLOWED_BUNDLE_MEMBERS or name in members:
            raise ValidationError(f"Invalid backup: unexpected entry {name!r}.")
        if info.file_size > MAX_MEMBER_BYTES:
            raise ValidationError(f"Invalid backup: {name} is too large.")
        if (
            info.file_size > RATIO_MIN_BYTES
            and info.file_size > max(info.compress_size, 1) * MAX_COMPRESSION_RATIO
        ):
            raise ValidationError(
                f"Invalid backup: {name} has a suspicious compression ratio."
            )
        total += info.file_size
        members[name] = info
    if total > MAX_TOTAL_BYTES:
        raise ValidationError("Invalid backup: contents are too large.")
    return members


def _extract_database(zf: zipfile.ZipFile, info: zipfile.ZipInfo, destination: Path) -> None:
    written = 0
    with zf.open(info) as src, open(destination, "wb") as dst:
        while True:
            block = src.read(_CHUNK)
            if not block:
                break
            written += len(block)
            if written > MAX_MEMBER_BYTES:
                raise ValidationError("Invalid backup: database is too large.")
            dst.write(block)


def _verify_and_migrate(candidate: Path) -> int:
    """Integrity-check the extracted database and migrate it (on the temp copy). Returns project count."""
    from grafid.services.db_init import DatabaseInitService

    try:
        conn = sqlite3.connect(candidate)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            if row is None or str(row[0]).lower() != "ok":
                raise DatabaseError(f"Backup database failed its integrity check: {row[0] if row else 'no result'}")
            version = get_schema_version(conn)
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise DatabaseError(f"The backup does not contain a valid database: {exc}") from exc
    if version is not None and version > SCHEMA_VERSION:
        raise ValidationError(f"Backup schema {version} is newer than this app ({SCHEMA_VERSION}).")

    DatabaseInitService(candidate).initialize(verify=True)
    with DatabaseConnection_ro(candidate) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0])


def _write_settings_merge(config_path: Path, allowed: dict[str, object]) -> tuple[str, ...]:
    """Merge allowlisted settings into config.json atomically, preserving everything else."""
    existing: dict[str, object] = {}
    if config_path.is_file():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}
    merged = {**existing, **allowed}
    fd, tmp_name = tempfile.mkstemp(prefix=".config.", suffix=".tmp", dir=config_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(merged, indent=2) + "\n")
        os.replace(tmp_name, config_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return tuple(sorted(allowed))


def _make_pre_restore_backup(live_db: Path, config_dir: Path) -> Path:
    backups = config_dir / PRE_RESTORE_DIRNAME
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = backups / f"graf-id.pre-restore-{stamp}.db"
    counter = 2
    while target.exists():
        target = backups / f"graf-id.pre-restore-{stamp}-{counter}.db"
        counter += 1
    try:
        _sqlite_backup(live_db, target)
    except sqlite3.Error:
        # The live database may itself be damaged (that is often why someone
        # restores). A raw copy still preserves whatever is recoverable.
        target.unlink(missing_ok=True)
        shutil.copy2(live_db, target)
    return target


def import_bundle(
    *,
    zip_path: Path,
    config_dir: Path,
    replace: bool = False,
    restore_settings: bool = False,
) -> RestoreResult:
    """
    Restore the database from a backup zip.

    Order of operations (nothing the user has is modified before step 6):
    1 validate the archive (members, sizes, compression ratio, manifest schema),
    2 stream the database into a temp file beside the target (byte-capped),
    3 SQLite integrity check, 4 migrate the TEMP copy, 5 validate settings (if
    requested), 6 safety-backup the current database with the SQLite backup API,
    7 atomically replace. Any failure earlier leaves the live database and
    config untouched.
    """
    zip_path = zip_path.expanduser().resolve()
    if not zip_path.is_file():
        raise ValidationError(f"Backup file not found: {zip_path}")

    config_dir.mkdir(parents=True, exist_ok=True)
    db_dest = config_dir / BUNDLE_DB_NAME
    config_dest = config_dir / BUNDLE_CONFIG_NAME

    if db_dest.exists() and not replace:
        raise ValidationError(
            f"Database already exists at {db_dest}. Use --replace to overwrite."
        )

    try:
        archive = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        raise ValidationError("Invalid backup: the file is not a valid zip archive.") from exc

    with archive as zf:
        members = _check_archive_limits(zf)
        if MANIFEST_NAME not in members:
            raise ValidationError(f"Invalid backup: missing {MANIFEST_NAME}")
        try:
            manifest = json.loads(
                _read_member_bounded(zf, members[MANIFEST_NAME], MAX_MANIFEST_BYTES).decode("utf-8")
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValidationError(f"Invalid backup: malformed {MANIFEST_NAME} ({exc})") from exc
        if not isinstance(manifest, dict):
            raise ValidationError("Invalid backup: manifest must be a JSON object")
        _validate_manifest_schema_version(manifest)
        if BUNDLE_DB_NAME not in members:
            raise ValidationError(f"Invalid backup: missing {BUNDLE_DB_NAME}")

        allowed_settings: dict[str, object] = {}
        if restore_settings and BUNDLE_CONFIG_NAME in members:
            try:
                text = _read_member_bounded(zf, members[BUNDLE_CONFIG_NAME], MAX_CONFIG_BYTES).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValidationError("Invalid backup: settings are not valid UTF-8.") from exc
            allowed_settings = _allowlisted_settings(text)

        staging = Path(tempfile.mkdtemp(prefix=".graf-id-restore-", dir=config_dir))
        try:
            candidate = staging / BUNDLE_DB_NAME
            _extract_database(zf, members[BUNDLE_DB_NAME], candidate)
            project_count = _verify_and_migrate(candidate)

            pre_restore: Path | None = None
            if db_dest.exists():
                pre_restore = _make_pre_restore_backup(db_dest, config_dir)
                for suffix in ("-journal", "-wal", "-shm"):
                    Path(f"{db_dest}{suffix}").unlink(missing_ok=True)
            try:
                os.replace(candidate, db_dest)
            except OSError as exc:
                raise ValidationError(
                    "Graf-Id could not replace the database (is another Graf-Id "
                    f"window using it?): {exc}"
                ) from exc

            restored_keys: tuple[str, ...] = ()
            if allowed_settings:
                restored_keys = _write_settings_merge(config_dest, allowed_settings)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    logger.info("Restored backup into %s (%s projects)", config_dir, project_count)
    return RestoreResult(
        database_path=db_dest,
        pre_restore_backup=pre_restore,
        project_count=project_count,
        settings_restored=restored_keys,
    )


def _validate_manifest_schema_version(manifest: dict[str, object]) -> int:
    """
    L2: explicit, deterministic manifest schema_version validation.

    Previously `isinstance(schema, int) and schema > SCHEMA_VERSION` silently
    let a MISSING or non-integer schema_version (None, a string like "12", a
    float, a bool) through unchecked — `isinstance(x, int)` being False just
    skipped the whole check instead of rejecting the bundle. A negative or
    unrealistically old integer also passed, since only the upper bound was
    ever checked. Every one of those cases must now reject the import with a
    clear reason instead of proceeding on an unverified assumption.
    """
    if "schema_version" not in manifest:
        raise ValidationError("Invalid bundle: manifest is missing schema_version")
    schema = manifest["schema_version"]
    # bool is a subclass of int in Python — exclude it explicitly, or
    # schema_version: true/false would silently pass as 1/0.
    if isinstance(schema, bool) or not isinstance(schema, int):
        raise ValidationError(
            f"Invalid bundle: schema_version must be an integer, got {schema!r}"
        )
    if schema < MIN_SUPPORTED_SCHEMA_VERSION:
        raise ValidationError(
            f"Bundle schema {schema} is older than the minimum supported "
            f"version ({MIN_SUPPORTED_SCHEMA_VERSION})"
        )
    if schema > SCHEMA_VERSION:
        raise ValidationError(
            f"Bundle schema {schema} is newer than this app ({SCHEMA_VERSION})"
        )
    return schema


def _sanitized_config_json(text: str) -> str:
    """
    Validate an imported config.json and strip launch-affecting fields.

    An export bundle can come from another machine or user and is not fully
    trusted. Without this, a crafted ``config.json`` could silently set
    ``custom_opener_path`` to an executable already present on this machine
    and flip ``default_project_opener``/``preferred_ide`` to "custom" so it
    gets launched automatically on the next "Open Project" — with no review
    by the user. Those fields are always dropped/reset on import; the user
    must reconfigure a custom opener explicitly in Settings afterward. The
    same applies to coding agent definitions/overrides (see below).

    Raises ValidationError for malformed JSON/shape so a bad bundle is
    rejected loudly instead of silently corrupting the live config directory.
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid config.json in export bundle: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValidationError("config.json in export bundle must be a JSON object")

    raw.pop(CUSTOM_OPENER_PATH_KEY, None)
    if raw.get(DEFAULT_PROJECT_OPENER_KEY) == "custom":
        raw[DEFAULT_PROJECT_OPENER_KEY] = "system"
    if raw.get("preferred_ide") == "custom":
        raw["preferred_ide"] = "system"

    # Same threat as custom_opener_path: a coding agent is an arbitrary
    # executable + args launched on "Open Project". Imported agent definitions
    # and executable overrides are never trusted; the user re-adds them in
    # Settings, and any opener pointing at an agent falls back to "system".
    raw.pop(CODING_AGENTS_KEY, None)
    raw.pop(BUILTIN_AGENTS_KEY, None)
    for opener_key in (DEFAULT_PROJECT_OPENER_KEY, "preferred_ide"):
        if isinstance(raw.get(opener_key), str) and is_agent_opener_value(raw[opener_key]):
            raw[opener_key] = "system"

    # Re-validate the remaining fields through the normal, known-key load
    # path (log_level, usage_journal, etc.) so any other malformed value
    # also fails the import loudly rather than being written to disk.
    try:
        ConfigManager._parse_known_config(raw)  # noqa: SLF001 — shared validation, no I/O
    except ConfigError as exc:
        raise ValidationError(f"Invalid config.json in export bundle: {exc}") from exc

    return json.dumps(raw, indent=2) + "\n"


class DatabaseConnection_ro:
    """Minimal read-only connection for export."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        return self._conn

    def __exit__(self, *args: object) -> None:
        if self._conn:
            self._conn.close()


def vacuum_database(db_path: Path) -> None:
    """Run SQLite VACUUM maintenance."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()
