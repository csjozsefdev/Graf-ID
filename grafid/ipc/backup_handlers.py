"""IPC handlers for backup and restore (Settings > Data)."""

from __future__ import annotations

from pathlib import Path

from grafid.config.manager import ConfigManager
from grafid.core.exceptions import ConfigError, DatabaseError, GrafIdError, ValidationError
from grafid.ipc.envelope import IpcResponse, failure, success
from grafid.ipc.errors import failure_from
from grafid.services.portability import export_bundle, import_bundle


def _paths(manager: ConfigManager) -> tuple[Path, Path, Path]:
    config = manager.load()
    config_dir = manager.config_dir
    return config_dir, config.resolved_database_path(config_dir), manager.config_path


def handle_create_backup(
    output_path: str,
    *,
    include_settings: bool = False,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Write a consistent backup zip of the local database to a user-chosen path."""
    try:
        if not output_path or not output_path.strip():
            raise ValidationError("Choose where to save the backup.")
        manager = config_manager or ConfigManager()
        _, db_path, config_path = _paths(manager)
        target = Path(output_path)
        if target.suffix.lower() != ".zip":
            target = target.with_suffix(".zip")
        written = export_bundle(
            db_path=db_path,
            config_path=config_path,
            output_zip=target,
            include_settings=include_settings,
        )
        return success(
            {
                "path": str(written),
                "bytes_written": written.stat().st_size,
                "message": "Backup created.",
            }
        )
    except ValidationError as exc:
        return failure("validation_error", str(exc))
    except OSError as exc:
        return failure("validation_error", f"Could not write the backup: {exc}")
    except (DatabaseError, ConfigError, GrafIdError) as exc:
        return failure_from(exc)


def handle_restore_backup(
    backup_path: str,
    *,
    restore_settings: bool = False,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """
    Restore the database from a backup zip. The caller (desktop UI) has already
    asked the user to confirm; a safety copy of the current database is kept.
    """
    try:
        if not backup_path or not backup_path.strip():
            raise ValidationError("Choose a backup file to restore.")
        manager = config_manager or ConfigManager()
        config_dir, _, _ = _paths(manager)
        result = import_bundle(
            zip_path=Path(backup_path),
            config_dir=config_dir,
            replace=True,
            restore_settings=restore_settings,
        )
        return success(
            {
                "project_count": result.project_count,
                "pre_restore_backup": (
                    str(result.pre_restore_backup) if result.pre_restore_backup else None
                ),
                "settings_restored": list(result.settings_restored),
                "message": f"Restored {result.project_count} project(s).",
            }
        )
    except ValidationError as exc:
        return failure("validation_error", str(exc))
    except OSError as exc:
        return failure("validation_error", f"Could not restore the backup: {exc}")
    except (DatabaseError, ConfigError, GrafIdError) as exc:
        return failure_from(exc)
