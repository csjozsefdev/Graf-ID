"""UTC timestamp helpers."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now_iso() -> str:
    """Return current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp (``Z`` allowed); naive values are read as UTC."""
    if not value or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
