"""User preference keys and validation for config.json."""

from __future__ import annotations

from typing import Any

from grafid.config.coding_agents import is_agent_opener_value
from grafid.config.editors import (
    SYSTEM_OPENER,
    canonical_token,
    opener_token_list,
    opener_tokens,
)
from grafid.core.exceptions import ConfigError

DEFAULT_PROJECT_OPENER_KEY = "default_project_opener"
CUSTOM_OPENER_PATH_KEY = "custom_opener_path"

def normalize_default_project_opener(value: Any) -> str:
    """
    Normalize stored opener preference.

    Returns ``system``, an editor preset id (see config/editors.py) or an
    ``agent:<id>`` opener. Invalid values raise ConfigError.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return SYSTEM_OPENER
    token = str(value).strip()
    # Coding agent openers are namespaced ("agent:<id>") and validated by
    # resolving them at launch time (grafid/services/coding_agent_launch.py),
    # not against a fixed token set here — agent ids are user-defined and
    # dynamic (built-ins plus whatever custom agents exist), so they can't be
    # enumerated ahead of time the way editor tokens can.
    if is_agent_opener_value(token):
        return token
    normalized = canonical_token(token)
    if normalized not in opener_tokens():
        raise ConfigError(
            f"Invalid {DEFAULT_PROJECT_OPENER_KEY} '{value}'. Use {opener_token_list()}."
        )
    return normalized


def opener_to_ide_token(stored: str | None) -> str | None:
    """
    Map settings value to workflow IDE token (cursor, vscode, explorer, pycharm, ...).

    system -> None (workflow picks editor if on PATH, else Explorer).
    custom -> "custom" (resolved via custom_opener_path in workflow_launch).
    """
    if stored is None:
        return None
    token = normalize_default_project_opener(stored)
    if token == "system":
        return None
    if token == "explorer":
        return "explorer"
    return token
