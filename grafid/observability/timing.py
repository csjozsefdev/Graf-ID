"""Optional local timing collection for development."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from grafid.observability.settings import debug_timing_enabled
from grafid.utils.logging_setup import get_logger

logger = get_logger("timing")


@dataclass
class TimingCollector:
    """Collect named operation durations (milliseconds)."""

    enabled: bool = False
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, operation: str, duration_ms: float, **meta: Any) -> None:
        if not self.enabled:
            return
        row: dict[str, Any] = {
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
        }
        row.update({k: v for k, v in meta.items() if v is not None})
        self.entries.append(row)
        logger.debug("timing %s %.2fms", operation, duration_ms)

    def as_list(self) -> list[dict[str, Any]]:
        return list(self.entries)


@contextmanager
def timed_block(
    operation: str,
    collector: TimingCollector | None,
    **meta: Any,
) -> Iterator[None]:
    """Measure a block when debug timing is enabled."""
    if collector is None or not collector.enabled:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        collector.add(operation, elapsed_ms, **meta)


def new_timing_collector(config: Any | None = None) -> TimingCollector:
    """Create a collector respecting config and GRAFID_DEBUG_TIMING."""
    return TimingCollector(enabled=debug_timing_enabled(config))
