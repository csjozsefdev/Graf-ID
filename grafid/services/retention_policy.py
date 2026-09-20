"""Snapshot retention rules (applied by SnapshotRetentionService)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetentionPolicy:
    """Caps scan snapshots per project by count and/or age (None disables a rule)."""

    max_snapshots_per_project: int | None = None
    max_age_days: int | None = None

    def cleanup_enabled(self) -> bool:
        """True when at least one retention rule is configured."""
        return bool(
            (self.max_snapshots_per_project and self.max_snapshots_per_project > 0)
            or (self.max_age_days and self.max_age_days > 0)
        )
