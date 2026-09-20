"""Local usage journal commands (dogfooding, no telemetry)."""

from __future__ import annotations

import json

import typer

from grafid.cli.common import exit_with_error

from grafid.config.manager import ConfigManager
from grafid.core.exceptions import ConfigError, GrafIdError
from grafid.core.exceptions import GrafPermissionError
from grafid.observability.journal import journal_path_for, summarize_journal
from grafid.observability.settings import debug_timing_enabled, usage_journal_enabled

usage_app = typer.Typer(
    help="Local-only usage observation for personal workflow validation.",
    no_args_is_help=True,
)


@usage_app.command("status")
def usage_status_cmd() -> None:
    """Show whether local journal and debug timing are enabled."""
    try:
        mgr = ConfigManager()
        config = mgr.load()
    except (ConfigError, GrafPermissionError) as exc:
        exit_with_error(str(exc))

    typer.echo(f"usage_journal: {usage_journal_enabled(config)}")
    typer.echo(f"debug_timing: {debug_timing_enabled(config)}")
    typer.echo(f"journal_path: {journal_path_for(mgr.config_dir)}")
    typer.echo("Enable journal: set usage_journal=true in config.json or GRAFID_USAGE_JOURNAL=1")


@usage_app.command("summary")
def usage_summary_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Summarize recent local usage events and friction hints."""
    try:
        mgr = ConfigManager()
        summary = summarize_journal(config_dir=mgr.config_dir)
        summary["usage_journal_enabled"] = usage_journal_enabled(mgr.load())
    except (ConfigError, GrafPermissionError) as exc:
        exit_with_error(str(exc))
    except GrafIdError as exc:
        exit_with_error(str(exc))

    if json_output:
        typer.echo(json.dumps(summary, indent=2))
        return

    if not summary.get("journal_exists"):
        typer.echo("No usage journal yet. Enable usage_journal and use Graf-Id normally.")
        return

    typer.echo("--- Local usage summary (this device only) ---")
    counts = summary.get("event_counts") or {}
    if counts:
        typer.echo("Event counts:")
        for name, count in counts.items():
            typer.echo(f"  {name}: {count}")
    hints = summary.get("friction_hints") or []
    if hints:
        typer.echo("")
        typer.echo("Friction hints:")
        for hint in hints:
            typer.echo(f"  - {hint}")
    else:
        typer.echo("")
        typer.echo("No friction hints yet (keep using the app).")
