"""IPC handlers for app settings (config.json)."""

from __future__ import annotations

import json

from grafid.config.coding_agents import (
    CODING_AGENTS_KEY,
    agent_id_from_opener_value,
    merged_agent_list,
    opener_value_for_agent,
    removed_builtin_agents,
    validate_builtin_agent_settings_payload,
    validate_custom_agents_payload,
    visible_agent_names,
)
from grafid.config.interpreter_preferences import (
    PYTHON_INTERPRETER_CUSTOM_PATH_KEY,
    PYTHON_INTERPRETER_MODE_KEY,
    detect_interpreter_hint,
    list_interpreter_options,
    normalize_python_interpreter_mode,
)
from grafid.config.editors import opener_options
from grafid.config.manager import AppConfig, ConfigManager
from grafid.config.preferences import (
    CUSTOM_OPENER_PATH_KEY,
    DEFAULT_PROJECT_OPENER_KEY,
    normalize_default_project_opener,
)
from grafid.utils.text import clean_optional_text
from grafid.core.exceptions import ConfigError, GrafIdError
from grafid.ipc.envelope import IpcResponse, failure, success
from grafid.ipc.errors import failure_from
from grafid.observability.settings import debug_timing_enabled, usage_journal_enabled


def _parse_bool_flag(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _default_settings_payload(
    manager: ConfigManager,
    config: AppConfig | None = None,
) -> dict[str, object]:
    """Stable settings shape with safe defaults when config is missing or invalid."""
    cfg = config or AppConfig()
    data_dir = manager.config_dir
    logs_dir = cfg.resolved_log_dir(data_dir)
    opener = getattr(cfg, "default_project_opener", None) or "system"
    extra = getattr(cfg, "extra", {}) or {}
    compact = bool(extra.get("compact_mode", False))
    try:
        interpreter_mode = normalize_python_interpreter_mode(
            extra.get(PYTHON_INTERPRETER_MODE_KEY, "auto")
        )
    except ConfigError:
        interpreter_mode = "auto"
    interpreter_custom_path = clean_optional_text(
        extra.get(PYTHON_INTERPRETER_CUSTOM_PATH_KEY)
    )
    custom_opener_path = clean_optional_text(extra.get(CUSTOM_OPENER_PATH_KEY))
    return {
        "data_dir": str(data_dir),
        "logs_dir": str(logs_dir),
        "config_dir": str(data_dir),
        "config_path": str(manager.config_path),
        DEFAULT_PROJECT_OPENER_KEY: opener,
        "usage_journal_enabled": usage_journal_enabled(cfg),
        "debug_timing_enabled": debug_timing_enabled(cfg),
        "compact_mode": compact,
        "opener_options": opener_options(),
        PYTHON_INTERPRETER_MODE_KEY: interpreter_mode,
        PYTHON_INTERPRETER_CUSTOM_PATH_KEY: interpreter_custom_path,
        CUSTOM_OPENER_PATH_KEY: custom_opener_path,
        "interpreter_options": list_interpreter_options(),
        "python_interpreter_hint": detect_interpreter_hint(
            interpreter_mode,
            custom_path=interpreter_custom_path,
        ),
        CODING_AGENTS_KEY: merged_agent_list(
            getattr(cfg, "coding_agents", []) or [],
            getattr(cfg, "builtin_agents", {}) or {},
        ),
        "removed_builtin_agents": removed_builtin_agents(
            getattr(cfg, "builtin_agents", {}) or {}
        ),
    }


def _parse_json_payload(value: str | list | dict, label: str) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{label} is not valid JSON: {exc}") from exc
    return value


def _reconcile_agent_openers(
    manager: ConfigManager,
    before: dict[str, str],
    after: dict[str, str],
    opener: str,
) -> tuple[str, list[str]]:
    """
    Keep opener references consistent after coding agents were removed.

    Returns (opener, notices). A removed agent must never leave a dangling
    reference: the default opener falls back to "system" (Auto Detect) and
    project-specific openers are reset to inherit the default, and the user
    is told about both.
    """
    removed = {aid: name for aid, name in before.items() if aid not in after}
    notices: list[str] = []
    default_agent_id = agent_id_from_opener_value(opener)
    if default_agent_id is not None and default_agent_id not in after:
        name = removed.get(default_agent_id, default_agent_id)
        opener = "system"
        notices.append(f"Default opener reset to Auto Detect because {name} was removed.")
    if removed:
        try:
            from grafid.services.runtime import prepare_runtime

            runtime = prepare_runtime(manager)
            affected = runtime.registry.clear_agent_openers(
                [opener_value_for_agent(aid) for aid in removed]
            )
        except Exception as exc:  # noqa: BLE001 — never fail the settings save over this
            notices.append(
                f"Could not reset project openers that used a removed agent ({exc}); "
                "those projects will show an error until you pick another opener."
            )
        else:
            if affected:
                names = ", ".join(sorted(record.name for record in affected))
                notices.append(
                    f"Opener reset to the default for {len(affected)} project(s) "
                    f"that used a removed agent: {names}."
                )
    return opener, notices


def _load_config_safe(manager: ConfigManager) -> AppConfig:
    try:
        return manager.load()
    except ConfigError:
        return AppConfig()


def handle_get_app_settings(
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Return user-facing settings for the desktop UI."""
    try:
        manager = config_manager or ConfigManager()
        config = _load_config_safe(manager)
        payload = _default_settings_payload(manager, config)
        return success(payload)
    except GrafIdError as exc:
        return failure_from(exc)


def handle_save_app_settings(
    opener: str,
    usage_journal: str | bool,
    debug_timing: str | bool,
    compact_mode: str | bool | None = None,
    python_interpreter_mode: str | None = None,
    python_interpreter_custom_path: str | None = None,
    custom_opener_path: str | None = None,
    coding_agents: str | list | None = None,
    builtin_agents: str | dict | None = None,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Persist app settings to config.json."""
    try:
        manager = config_manager or ConfigManager()
        normalized_opener = normalize_default_project_opener(opener)
        current = _load_config_safe(manager)
        extra = dict(current.extra)
        if compact_mode is not None:
            extra["compact_mode"] = _parse_bool_flag(compact_mode)
        if python_interpreter_mode is not None:
            extra[PYTHON_INTERPRETER_MODE_KEY] = normalize_python_interpreter_mode(
                python_interpreter_mode
            )
        if python_interpreter_custom_path is not None:
            extra[PYTHON_INTERPRETER_CUSTOM_PATH_KEY] = (
                clean_optional_text(python_interpreter_custom_path)
            )
        if custom_opener_path is not None:
            extra[CUSTOM_OPENER_PATH_KEY] = clean_optional_text(
                custom_opener_path
            )
        if coding_agents is not None:
            new_agents = validate_custom_agents_payload(
                _parse_json_payload(coding_agents, "coding_agents"),
                previous=current.coding_agents,
            )
        else:
            new_agents = current.coding_agents
        if builtin_agents is not None:
            new_builtin = validate_builtin_agent_settings_payload(
                _parse_json_payload(builtin_agents, "builtin_agents"),
                previous=current.builtin_agents,
            )
        else:
            new_builtin = current.builtin_agents

        before_names = visible_agent_names(current.coding_agents, current.builtin_agents)
        after_names = visible_agent_names(new_agents, new_builtin)
        normalized_opener, notices = _reconcile_agent_openers(
            manager, before_names, after_names, normalized_opener
        )
        updated = AppConfig(
            database_path=current.database_path,
            log_level=current.log_level,
            usage_journal=_parse_bool_flag(usage_journal),
            debug_timing=_parse_bool_flag(debug_timing),
            default_project_opener=normalized_opener,
            coding_agents=new_agents,
            builtin_agents=new_builtin,
            extra=extra,
        )
        manager.save(updated)
        payload = _default_settings_payload(manager, updated)
        payload["message"] = " ".join(["Settings saved.", *notices])
        return success(payload)
    except ConfigError as exc:
        return failure("config_error", str(exc))
    except GrafIdError as exc:
        return failure_from(exc)


def handle_reset_app_settings(
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Reset settings to application defaults."""
    try:
        manager = config_manager or ConfigManager()
        current = _load_config_safe(manager)
        _, notices = _reconcile_agent_openers(
            manager,
            visible_agent_names(current.coding_agents, current.builtin_agents),
            visible_agent_names([], {}),
            "system",
        )
        defaults = AppConfig(
            database_path=current.database_path,
            log_level="INFO",
            usage_journal=False,
            debug_timing=False,
            default_project_opener="system",
            extra={},
        )
        manager.save(defaults)
        payload = _default_settings_payload(manager, defaults)
        payload["message"] = " ".join(["Settings reset to defaults.", *notices])
        return success(payload)
    except ConfigError as exc:
        return failure("config_error", str(exc))
    except GrafIdError as exc:
        return failure_from(exc)


def handle_set_default_project_opener(
    opener: str,
    config_manager: ConfigManager | None = None,
) -> IpcResponse:
    """Persist default_project_opener only (legacy IPC)."""
    try:
        manager = config_manager or ConfigManager()
        current = _load_config_safe(manager)
        return handle_save_app_settings(
            opener,
            current.usage_journal,
            current.debug_timing,
            config_manager=manager,
        )
    except GrafIdError as exc:
        return failure_from(exc)
