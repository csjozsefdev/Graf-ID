"""IPC handlers for local usage insights (dogfooding, no telemetry)."""

from __future__ import annotations

from grafid.config.manager import ConfigManager
from grafid.core.exceptions import GrafIdError
from grafid.ipc.envelope import IpcResponse, success
from grafid.ipc.errors import failure_from
from grafid.observability.journal import summarize_journal
from grafid.observability.settings import debug_timing_enabled, usage_journal_enabled


def handle_usage_insights(config_manager: ConfigManager | None = None) -> IpcResponse:
    """Return aggregated local journal stats for personal workflow reflection."""
    try:
        manager = config_manager or ConfigManager()
        config = manager.load()
        summary = summarize_journal(config_dir=manager.config_dir)
        summary["usage_journal_enabled"] = usage_journal_enabled(config)
        summary["debug_timing_enabled"] = debug_timing_enabled(config)
        summary["config_dir"] = str(manager.config_dir)
        return success(summary)
    except GrafIdError as exc:
        return failure_from(exc)
