"""Feature flags for local observation and optional debug timing."""

from __future__ import annotations

import os

from grafid.config.manager import AppConfig


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def usage_journal_enabled(config: AppConfig | None = None) -> bool:
    """Local JSONL journal for dogfooding (never sent off-device)."""
    if _env_flag("GRAFID_USAGE_JOURNAL"):
        return True
    if config is not None and bool(getattr(config, "usage_journal", False)):
        return True
    if config is not None and config.extra.get("usage_journal") in (True, "true", 1):
        return True
    return False


def debug_timing_enabled(config: AppConfig | None = None) -> bool:
    """Include operation timings in logs and optional IPC payloads."""
    if _env_flag("GRAFID_DEBUG_TIMING"):
        return True
    if config is not None and bool(getattr(config, "debug_timing", False)):
        return True
    if config is not None and config.extra.get("debug_timing") in (True, "true", 1):
        return True
    return False
