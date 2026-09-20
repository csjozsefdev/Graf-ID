"""Safe text reading with size limits and encoding fallback."""

from __future__ import annotations

from pathlib import Path

from grafid.utils.logging_setup import get_logger

logger = get_logger("scanner.reader")

ENCODING_CANDIDATES = ("utf-8", "utf-8-sig", "cp1252", "latin-1")


def read_file_text(
    path: Path,
    *,
    max_file_size_bytes: int,
) -> tuple[str | None, str | None]:
    """
    Read full decoded text from a file within the size limit.

    Returns (text, warning). When warning is set, text may be None.
    """
    raw, warning = _read_bytes_within_limit(path, max_file_size_bytes)
    if warning is not None:
        return None, warning
    if raw is None:
        return "", None
    return _decode_bytes(raw, path)


def _read_bytes_within_limit(
    path: Path, max_file_size_bytes: int
) -> tuple[bytes | None, str | None]:
    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        warning = f"Cannot stat file: {path} ({exc})"
        logger.warning(warning)
        return None, warning

    if size_bytes > max_file_size_bytes:
        warning = f"Skipped large file ({size_bytes} bytes): {path}"
        logger.warning(warning)
        return None, warning

    try:
        return path.read_bytes(), None
    except PermissionError:
        warning = f"Permission denied reading file: {path}"
        logger.warning(warning)
        return None, warning
    except OSError as exc:
        warning = f"Cannot read file: {path} ({exc})"
        logger.warning(warning)
        return None, warning


def _decode_bytes(raw: bytes, path: Path) -> tuple[str | None, str | None]:
    if not raw:
        return "", None

    for encoding in ENCODING_CANDIDATES:
        try:
            return raw.decode(encoding), None
        except UnicodeDecodeError:
            continue

    warning = f"Could not decode file with fallback encodings: {path}"
    logger.warning(warning)
    return None, warning


def normalize_text_preview(text: str, max_chars: int) -> str:
    """Collapse whitespace for compact CLI and log output."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3] + "..."
