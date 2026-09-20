"""Export, import, and maintenance CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from grafid.config.manager import ConfigManager
from grafid.core.exceptions import ConfigError, DatabaseError, ValidationError
from grafid.core.exceptions import GrafPermissionError
from grafid.services.portability import export_bundle, import_bundle, vacuum_database
from grafid.services.snapshot_retention import SnapshotRetentionService

def _paths() -> tuple[Path, Path, Path]:
    manager = ConfigManager()
    config = manager.load()
    config_dir = manager.config_dir
    db_path = config.resolved_database_path(config_dir)
    return config_dir, db_path, manager.config_path


def export_cmd(
    output: Path = typer.Argument(help="Output .zip path."),
    include_settings: bool = typer.Option(
        False,
        "--include-settings",
        help="Also store the harmless settings allowlist (never paths or agents).",
    ),
) -> None:
    """Create a backup zip (consistent database snapshot)."""
    try:
        config_dir, db_path, config_path = _paths()
        out = output if output.suffix else output.with_suffix(".zip")
        path = export_bundle(
            db_path=db_path,
            config_path=config_path,
            output_zip=out,
            include_settings=include_settings,
        )
    except (ValidationError, DatabaseError, ConfigError, GrafPermissionError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Exported to {path}")


def import_cmd(
    bundle: Path = typer.Argument(help="Path to export .zip."),
    replace: bool = typer.Option(False, "--replace", help="Replace the existing database."),
    restore_settings: bool = typer.Option(
        False,
        "--restore-settings",
        help="Also merge the backup's allowlisted settings (config is otherwise never touched).",
    ),
) -> None:
    """Restore a backup zip into the local data folder (a safety copy is kept)."""
    try:
        config_dir, _, _ = _paths()
        result = import_bundle(
            zip_path=bundle,
            config_dir=config_dir,
            replace=replace,
            restore_settings=restore_settings,
        )
    except (ValidationError, DatabaseError, ConfigError, GrafPermissionError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Restored database: {result.database_path} ({result.project_count} projects)")
    if result.pre_restore_backup:
        typer.echo(f"Previous database saved to: {result.pre_restore_backup}")
    if result.settings_restored:
        typer.echo(f"Settings restored: {', '.join(result.settings_restored)}")


maintenance_app = typer.Typer(help="Local database maintenance.")


@maintenance_app.command("vacuum")
def vacuum_cmd() -> None:
    """Run SQLite VACUUM on the local database."""
    try:
        _, db_path, _ = _paths()
        vacuum_database(db_path)
    except (ConfigError, GrafPermissionError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Vacuum complete: {db_path}")


@maintenance_app.command("prune-snapshots")
def prune_snapshots_cmd() -> None:
    """Apply snapshot retention policy for all projects."""
    try:
        _, db_path, _ = _paths()
        removed = SnapshotRetentionService(db_path).apply_all()
    except (ConfigError, DatabaseError, GrafPermissionError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Pruned {removed} snapshot(s)")
