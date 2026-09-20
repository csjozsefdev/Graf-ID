"""Load, validate, and persist local application configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from grafid.config.coding_agents import (
    BUILTIN_AGENTS_KEY,
    CODING_AGENTS_KEY,
    BuiltinAgentSettings,
    CodingAgentConfig,
    builtin_settings_to_dict,
    parse_builtin_agent_settings,
    parse_custom_agents,
)
from grafid.config.paths import resolve_app_config_dir
from grafid.config.preferences import (
    DEFAULT_PROJECT_OPENER_KEY,
    normalize_default_project_opener,
)
from grafid.core.constants import CONFIG_FILENAME, DB_FILENAME, LOG_DIR_NAME
from grafid.core.exceptions import ConfigError, GrafPermissionError

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def normalize_log_level(value: str) -> str:
    """Validate and normalize log_level from config JSON."""
    level = str(value).strip().upper()
    if level not in _VALID_LOG_LEVELS:
        raise ConfigError(
            f"Invalid log_level '{value}'; use one of: {', '.join(sorted(_VALID_LOG_LEVELS))}"
        )
    return level


@dataclass
class AppConfig:
    """Serializable application configuration with safe defaults."""

    database_path: str | None = None
    log_level: str = "INFO"
    usage_journal: bool = False
    debug_timing: bool = False
    default_project_opener: str = "system"
    coding_agents: list[CodingAgentConfig] = field(default_factory=list)
    builtin_agents: dict[str, BuiltinAgentSettings] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def resolved_database_path(self, config_dir: Path) -> Path:
        if self.database_path:
            raw = Path(self.database_path).expanduser()
            if raw.is_absolute():
                return raw.resolve()
            return (config_dir / raw).resolve()
        return (config_dir / DB_FILENAME).resolve()

    def resolved_log_dir(self, config_dir: Path) -> Path:
        return (config_dir / LOG_DIR_NAME).resolve()


class ConfigManager:
    """Manages config directory layout and JSON config file lifecycle."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = (
            config_dir.expanduser().resolve()
            if config_dir is not None
            else resolve_app_config_dir()
        )
        self._config_path = self._config_dir / CONFIG_FILENAME

    @property
    def config_dir(self) -> Path:
        return self._config_dir

    @property
    def config_path(self) -> Path:
        return self._config_path

    def ensure_directories(self) -> None:
        """Create config and log directories if missing."""
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            (self._config_dir / LOG_DIR_NAME).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise GrafPermissionError(
                f"Cannot create config directory at {self._config_dir}: {exc}"
            ) from exc

    def load(self) -> AppConfig:
        """Load config from disk or return defaults if the file does not exist."""
        if not self._config_path.exists():
            return AppConfig()

        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid config JSON at {self._config_path}") from exc
        except OSError as exc:
            raise ConfigError(f"Cannot read config at {self._config_path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise ConfigError("Config root must be a JSON object")

        return self._parse_known_config(raw)

    @staticmethod
    def _parse_known_config(raw: dict[str, Any]) -> AppConfig:
        """Build an AppConfig from an already-parsed JSON object (no file I/O)."""
        known_keys = (
            "database_path",
            "log_level",
            "usage_journal",
            "debug_timing",
            DEFAULT_PROJECT_OPENER_KEY,
            "preferred_ide",
            CODING_AGENTS_KEY,
            BUILTIN_AGENTS_KEY,
        )
        known = {k: v for k, v in raw.items() if k in known_keys}
        extra = {k: v for k, v in raw.items() if k not in known_keys}
        raw_level = known.get("log_level", "INFO")
        opener_raw = known.get(DEFAULT_PROJECT_OPENER_KEY)
        if opener_raw is None and "preferred_ide" in known:
            opener_raw = known.get("preferred_ide")
        # Malformed coding_agents must not break config load entirely — fails
        # open to an empty list (see parse_custom_agents docstring).
        coding_agents = parse_custom_agents(known.get(CODING_AGENTS_KEY))
        builtin_agents = parse_builtin_agent_settings(known.get(BUILTIN_AGENTS_KEY))
        return AppConfig(
            database_path=known.get("database_path"),
            log_level=normalize_log_level(str(raw_level)),
            usage_journal=bool(known.get("usage_journal", False)),
            debug_timing=bool(known.get("debug_timing", False)),
            default_project_opener=normalize_default_project_opener(opener_raw),
            coding_agents=coding_agents,
            builtin_agents=builtin_agents,
            extra=extra,
        )

    def save(self, config: AppConfig) -> None:
        """Persist configuration to disk."""
        self.ensure_directories()
        payload: dict[str, Any] = {
            "database_path": config.database_path,
            "log_level": config.log_level,
            "usage_journal": config.usage_journal,
            "debug_timing": config.debug_timing,
            DEFAULT_PROJECT_OPENER_KEY: config.default_project_opener,
            CODING_AGENTS_KEY: [agent.to_dict() for agent in config.coding_agents],
            BUILTIN_AGENTS_KEY: builtin_settings_to_dict(config.builtin_agents),
            **config.extra,
        }
        try:
            self._config_path.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise GrafPermissionError(
                f"Cannot write config to {self._config_path}: {exc}"
            ) from exc

    def bootstrap_defaults(self) -> AppConfig:
        """Ensure directories exist and write default config if absent."""
        self.ensure_directories()
        config = self.load()
        if not self._config_path.exists():
            self.save(config)
        return config
