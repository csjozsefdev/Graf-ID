"""Project registry row model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectRecord:
    """Represents one row in the projects table."""

    id: int
    name: str
    path: str
    created_at: str
    updated_at: str
    last_opened_at: str | None
    preferred_ide: str | None
    is_active: bool
    category: str
    status: str
    notes: str | None
    last_refreshed_at: str | None
    sidebar_order: int | None = None
