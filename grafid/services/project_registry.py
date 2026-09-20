"""Project registry business logic."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from grafid.core.exceptions import DuplicateProjectError, ProjectError, ValidationError
from grafid.db.connection import DatabaseConnection
from grafid.db.transactions import commit_write
from grafid.db.repositories.project_repository import ProjectRepository
from grafid.models.project import ProjectRecord
from grafid.services.project_validation import (
    find_duplicate_physical_path,
    normalize_category,
    normalize_name,
    normalize_notes,
    normalize_project_path,
    normalize_status,
    path_storage_value,
)
from grafid.utils.logging_setup import get_logger

logger = get_logger("project_registry")


class ProjectRegistryService:
    """Add, list, remove, inspect, and open registered projects."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def add(
        self,
        name: str,
        raw_path: str,
        *,
        preferred_ide: str | None = None,
        category: str | None = None,
    ) -> ProjectRecord:
        """Register a new project after validation."""
        clean_name = normalize_name(name)
        clean_category = normalize_category(category)
        resolved = normalize_project_path(raw_path)
        stored_path = path_storage_value(resolved)

        # H6: BEGIN IMMEDIATE closes the check-then-insert race between two
        # concurrent "add project" calls; the sqlite3.IntegrityError catch below
        # is defense-in-depth for any residual race the lock doesn't cover, so a
        # duplicate never leaks as a raw, unhandled sqlite3 error through IPC.
        try:
            with DatabaseConnection(self._db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    repo = ProjectRepository(conn)
                    if repo.get_by_name(clean_name):
                        raise DuplicateProjectError(
                            f"Project name already registered: {clean_name}"
                        )
                    if repo.get_by_path(stored_path):
                        raise DuplicateProjectError(
                            f"Project path already registered: {stored_path}"
                        )
                    dup_id = find_duplicate_physical_path(
                        resolved, [(p.id, p.path) for p in repo.list_all()]
                    )
                    if dup_id is not None:
                        raise DuplicateProjectError(
                            "This folder is already registered under a different "
                            f"path (project id={dup_id}): {stored_path}"
                        )
                    record = repo.insert(
                        clean_name,
                        stored_path,
                        preferred_ide=preferred_ide,
                        category=clean_category,
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        except DuplicateProjectError:
            logger.warning(
                "Duplicate project rejected: name=%s path=%s", clean_name, stored_path
            )
            raise
        except sqlite3.IntegrityError as exc:
            logger.warning(
                "Duplicate project rejected by DB constraint: name=%s path=%s (%s)",
                clean_name,
                stored_path,
                exc,
            )
            raise DuplicateProjectError(
                f"Project name or path already registered: {clean_name} / {stored_path}"
            ) from exc

        logger.info(
            "Project added: id=%s name=%s path=%s category=%s",
            record.id,
            record.name,
            record.path,
            record.category,
        )
        return record

    def list_projects(self) -> list[ProjectRecord]:
        """Return all registered projects sorted by name."""
        with DatabaseConnection(self._db_path) as conn:
            return ProjectRepository(conn).list_all()

    def remove(self, identifier: str) -> ProjectRecord:
        """Remove a project by numeric id or name."""
        record = self._resolve(identifier)
        with DatabaseConnection(self._db_path) as conn:
            deleted = ProjectRepository(conn).delete_by_id(record.id)
            if deleted:
                commit_write(conn)
        if not deleted:
            raise ProjectError(f"Project not found: {identifier}")
        logger.info("Project removed: id=%s name=%s", record.id, record.name)
        return record

    def get_info(self, identifier: str) -> ProjectRecord:
        """Return one project by id or name."""
        return self._resolve(identifier)

    def open_project(self, identifier: str) -> ProjectRecord:
        """Mark a project as opened (updates last_opened_at)."""
        record = self._resolve(identifier)
        with DatabaseConnection(self._db_path) as conn:
            updated = ProjectRepository(conn).update_last_opened(record.id)
            if updated is not None:
                commit_write(conn)
        if updated is None:
            raise ProjectError(f"Project not found: {identifier}")

        logger.info(
            "Project last_opened updated: id=%s name=%s path=%s",
            updated.id,
            updated.name,
            updated.path,
        )
        return updated

    def update(
        self,
        project_id: int,
        *,
        name: str | None = None,
        raw_path: str | None = None,
        category: str | None = None,
        status: str | None = None,
        notes: str | None = None,
        preferred_ide: str | None = None,
    ) -> ProjectRecord:
        """Update editable project metadata."""
        record = self._resolve(str(project_id))
        clean_name = normalize_name(name) if name is not None else None
        stored_path = (
            path_storage_value(normalize_project_path(raw_path))
            if raw_path is not None
            else None
        )
        clean_category = normalize_category(category) if category is not None else None
        clean_status = normalize_status(status) if status is not None else None
        clean_notes = normalize_notes(notes)

        try:
            with DatabaseConnection(self._db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    repo = ProjectRepository(conn)
                    if clean_name and clean_name != record.name:
                        if repo.get_by_name(clean_name):
                            raise DuplicateProjectError(
                                f"Project name already registered: {clean_name}"
                            )
                    if stored_path and stored_path != record.path:
                        existing = repo.get_by_path(stored_path)
                        if existing is not None and existing.id != record.id:
                            raise DuplicateProjectError(
                                f"Project path already registered: {stored_path}"
                            )
                        dup_id = find_duplicate_physical_path(
                            Path(stored_path),
                            [(p.id, p.path) for p in repo.list_all() if p.id != record.id],
                        )
                        if dup_id is not None:
                            raise DuplicateProjectError(
                                "This folder is already registered under a "
                                f"different path (project id={dup_id}): {stored_path}"
                            )
                    updated = repo.update_metadata(
                        record.id,
                        name=clean_name,
                        path=stored_path,
                        category=clean_category,
                        status=clean_status,
                        notes=clean_notes if notes is not None else None,
                        preferred_ide=preferred_ide,
                    )
                    if updated is None:
                        raise ProjectError(f"Project not found: {project_id}")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        except (DuplicateProjectError, ProjectError):
            raise
        except sqlite3.IntegrityError as exc:
            logger.warning(
                "Duplicate project update rejected by DB constraint: id=%s (%s)",
                project_id,
                exc,
            )
            raise DuplicateProjectError(
                f"Project name or path already registered: {exc}"
            ) from exc
        logger.info("Project updated: id=%s name=%s status=%s", updated.id, updated.name, updated.status)
        return updated

    def reorder_projects(self, ordered_ids: list[int]) -> list[ProjectRecord]:
        """Persist sidebar order for all registered projects."""
        if not ordered_ids:
            raise ValidationError("Project order cannot be empty")
        with DatabaseConnection(self._db_path) as conn:
            repo = ProjectRepository(conn)
            try:
                repo.reorder(ordered_ids)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            commit_write(conn)
            records = repo.list_all()
        logger.info("Project sidebar order updated (%s projects)", len(records))
        return records

    def clear_agent_openers(self, opener_values: list[str]) -> list[ProjectRecord]:
        """Reset any project opener that points at a removed coding agent."""
        with DatabaseConnection(self._db_path) as conn:
            repo = ProjectRepository(conn)
            affected = repo.clear_preferred_ide(opener_values)
            if affected:
                commit_write(conn)
        if affected:
            logger.info("Reset opener for %s project(s) after coding agent removal", len(affected))
        return affected

    def _resolve(self, identifier: str) -> ProjectRecord:
        if not identifier or not identifier.strip():
            raise ValidationError("Project identifier cannot be empty")

        token = identifier.strip()
        with DatabaseConnection(self._db_path) as conn:
            repo = ProjectRepository(conn)
            record: ProjectRecord | None
            if token.isdigit():
                record = repo.get_by_id(int(token))
            else:
                try:
                    clean_name = normalize_name(token)
                except ValidationError:
                    clean_name = token
                record = repo.get_by_name(clean_name)

        if record is None:
            raise ProjectError(f"Project not found: {token}")
        return record
