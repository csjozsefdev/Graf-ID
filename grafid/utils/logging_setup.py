"""Lightweight local file logging."""

from __future__ import annotations

import logging
from pathlib import Path

from grafid.core.constants import LOG_FILENAME

_CONFIGURED = False


def configure_logging(log_dir: Path, level: str = "INFO") -> logging.Logger:
    """
    Configure a single file handler on the root 'grafid' logger.

    Idempotent: repeated calls update the level but do not add duplicate handlers.
    """
    global _CONFIGURED

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILENAME

    logger = logging.getLogger("grafid")
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    if not _CONFIGURED:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        _CONFIGURED = True
    else:
        for handler in logger.handlers:
            handler.setLevel(numeric_level)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the grafid namespace."""
    return logging.getLogger(f"grafid.{name}")


def reset_logging_for_tests() -> None:
    """Clear handlers and reset state (tests only)."""
    global _CONFIGURED
    logger = logging.getLogger("grafid")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    _CONFIGURED = False
