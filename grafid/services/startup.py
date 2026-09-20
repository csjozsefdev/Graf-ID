"""Application startup orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from grafid.config.manager import AppConfig, ConfigManager
from grafid.core.exceptions import StartupError
from grafid.services.db_init import DatabaseInitService
from grafid.utils.logging_setup import configure_logging, get_logger

logger = get_logger("startup")


@dataclass(frozen=True)
class StartupResult:
    """Summary of a successful startup run."""

    config_dir: Path
    config_path: Path
    database_path: Path
    config: AppConfig


class StartupService:
    """Coordinates config bootstrap, logging, and database initialization."""

    def __init__(self, config_manager: ConfigManager | None = None) -> None:
        self._config_manager = config_manager or ConfigManager()

    def run(self) -> StartupResult:
        """
        Full startup: directories, config file, logging, DB init, integrity check.
        """
        try:
            config = self._config_manager.bootstrap_defaults()
            config_dir = self._config_manager.config_dir
            db_path = config.resolved_database_path(config_dir)
            log = logger.debug if db_path.exists() else logger.info
            log("Starting Graf-Id runtime")
            log_dir = config.resolved_log_dir(config_dir)

            configure_logging(log_dir, config.log_level)
            DatabaseInitService(db_path).initialize(verify=True)

            log("Startup completed successfully")
            return StartupResult(
                config_dir=config_dir,
                config_path=self._config_manager.config_path,
                database_path=db_path,
                config=config,
            )
        except Exception as exc:
            logger.error("Startup failed: %s", exc)
            if isinstance(exc, StartupError):
                raise
            raise StartupError(str(exc)) from exc
