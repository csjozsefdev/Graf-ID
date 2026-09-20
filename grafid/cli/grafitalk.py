"""CLI: export summaries for GrafiTalk."""

from __future__ import annotations

from pathlib import Path

import typer

from grafid.cli.portability import _paths
from grafid.core.exceptions import ConfigError, DatabaseError, GrafIdError, ValidationError
from grafid.core.exceptions import GrafPermissionError
from grafid.services.grafitalk_export import default_grafitalk_dir, export_grafitalk_inbox


def export_grafitalk_cmd(
    output: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Output folder (default: <Graf-Id data folder>/grafitalk-inbox).",
    ),
) -> None:
    """Export every project as a GrafiTalk handoff file into an inbox folder."""
    try:
        config_dir, db_path, _ = _paths()
        inbox = export_grafitalk_inbox(
            db_path=db_path,
            output_dir=output,
            config_dir=config_dir,
        )
    except (ValidationError, DatabaseError, ConfigError, GrafPermissionError, GrafIdError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"GrafiTalk inbox: {inbox}")
    typer.echo(f"  manifest: {inbox / 'manifest.json'}")
    typer.echo(f"  projects: {inbox / 'projects'}/")


def grafitalk_status_cmd() -> None:
    """Show default GrafiTalk inbox path and whether it exists."""
    try:
        config_dir, _, _ = _paths()
    except (ConfigError, GrafPermissionError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    inbox = default_grafitalk_dir(config_dir)
    typer.echo(f"Default inbox: {inbox}")
    if inbox.is_dir():
        manifest = inbox / "manifest.json"
        if manifest.is_file():
            typer.echo(f"  manifest: present ({manifest})")
        else:
            typer.echo("  manifest: missing (run export-grafitalk)")
    else:
        typer.echo("  (not created yet — run graf-id export-grafitalk)")
