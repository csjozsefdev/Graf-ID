"""Typer CLI entrypoint for Graf-Id."""

from __future__ import annotations

import typer

from grafid.cli.common import exit_with_error

from grafid import __version__
from grafid.config.manager import ConfigManager
from grafid.core.exceptions import ConfigError, DatabaseError, GrafIdError, StartupError
from grafid.core.exceptions import GrafPermissionError
from grafid.cli import projects as project_commands
from grafid.cli import history as history_commands
from grafid.cli import scan as scan_commands
from grafid.cli import resume as resume_commands
from grafid.cli import ipc as ipc_commands
from grafid.cli import session as session_commands
from grafid.cli import usage as usage_commands
from grafid.cli.grafitalk import export_grafitalk_cmd, grafitalk_status_cmd
from grafid.cli.portability import export_cmd, import_cmd, maintenance_app
from grafid.services.db_init import DatabaseInitService
from grafid.services.startup import StartupService

app = typer.Typer(
    name="graf-id",
    help="Graf-Id local workflow continuity utility.",
    no_args_is_help=True,
)


@app.callback()
def main_callback() -> None:
    """Graf-Id CLI root."""


app.command("add")(project_commands.add_cmd)
app.command("list")(project_commands.list_cmd)
app.command("remove")(project_commands.remove_cmd)
app.command("info")(project_commands.info_cmd)
app.command("open")(project_commands.open_cmd)
app.command("scan")(scan_commands.scan_cmd)
app.command("history")(history_commands.history_cmd)

session_app = typer.Typer(help="Work session continuity.")
session_app.command("start")(session_commands.session_start_cmd)
session_app.command("end")(session_commands.session_end_cmd)
session_app.command("status")(session_commands.session_status_cmd)
session_app.command("close")(session_commands.session_close_cmd)
app.add_typer(session_app, name="session")
app.command("resume")(resume_commands.resume_cmd)
app.command("resume-latest")(resume_commands.resume_latest_cmd)
app.command("ipc", context_settings=ipc_commands.IPC_COMMAND_SETTINGS)(ipc_commands.ipc_cmd)
app.add_typer(usage_commands.usage_app, name="usage")
app.command("export")(export_cmd)
app.command("import")(import_cmd)
app.command("export-grafitalk")(export_grafitalk_cmd)
app.add_typer(maintenance_app, name="maintenance")

grafitalk_app = typer.Typer(help="GrafiTalk summary inbox.")
grafitalk_app.command("status")(grafitalk_status_cmd)
app.add_typer(grafitalk_app, name="grafitalk")


@app.command("startup")
def startup_cmd() -> None:
    """Initialize config, database, and run startup integrity check."""
    try:
        result = StartupService().run()
    except (StartupError, ConfigError, DatabaseError, GrafPermissionError) as exc:
        exit_with_error(str(exc))
    except GrafIdError as exc:
        exit_with_error(str(exc))

    typer.echo("Graf-Id startup completed successfully.")
    typer.echo(f"Config directory: {result.config_dir}")
    typer.echo(f"Database: {result.database_path}")


db_app = typer.Typer(help="Database operations.")
app.add_typer(db_app, name="db")


@db_app.command("check")
def db_check_cmd() -> None:
    """Verify database file exists and passes integrity check."""
    try:
        config_manager = ConfigManager()
        config = config_manager.load()
        db_path = config.resolved_database_path(config_manager.config_dir)
        DatabaseInitService(db_path).check_integrity()
    except (ConfigError, DatabaseError, GrafPermissionError) as exc:
        exit_with_error(str(exc))
    except GrafIdError as exc:
        exit_with_error(str(exc))

    typer.echo(f"Database integrity check passed: {db_path}")


config_app = typer.Typer(help="Configuration paths.")
app.add_typer(config_app, name="config")


@config_app.command("path")
def config_path_cmd() -> None:
    """Print local config directory, config file, and database paths."""
    try:
        config_manager = ConfigManager()
        config = config_manager.load()
        config_dir = config_manager.config_dir
        db_path = config.resolved_database_path(config_dir)
        log_dir = config.resolved_log_dir(config_dir)
    except (ConfigError, GrafPermissionError) as exc:
        exit_with_error(str(exc))

    typer.echo(f"Config directory: {config_dir}")
    typer.echo(f"Config file: {config_manager.config_path}")
    typer.echo(f"Database path: {db_path}")
    typer.echo(f"Log directory: {log_dir}")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"graf-id {__version__}")
        raise typer.Exit()


@app.command("version", hidden=True)
def version_cmd() -> None:
    """Print package version."""
    typer.echo(f"graf-id {__version__}")


def main() -> None:
    """Console script entry used by setuptools."""
    app(prog_name="graf-id")


if __name__ == "__main__":
    main()
