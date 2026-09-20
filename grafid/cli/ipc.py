"""`graf-id ipc <command> [args]` - the desktop command table on the terminal.

A passthrough: argv goes unchanged to ``grafid.ipc.desktop_entry.main``, so the
terminal and the desktop shell always speak the same commands and flags.
"""

from __future__ import annotations

import typer

from grafid.ipc import desktop_entry

# Typer must not parse (or answer --help for) the command's own arguments.
IPC_COMMAND_SETTINGS = {
    "allow_extra_args": True,
    "ignore_unknown_options": True,
    "help_option_names": [],
}


def ipc_cmd(ctx: typer.Context) -> None:
    """Run one IPC command; prints one JSON object on stdout (`graf-id ipc --help` lists them)."""
    raise typer.Exit(desktop_entry.main(list(ctx.args)))
