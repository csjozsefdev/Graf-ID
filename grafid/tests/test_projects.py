"""Tests for project registry."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from grafid.config.manager import ConfigManager
from grafid.core.constants import SCHEMA_VERSION
from grafid.core.exceptions import DuplicateProjectError, ProjectError, ValidationError
from grafid.db.schema import get_schema_version
from grafid.services.db_init import DatabaseInitService
from grafid.services.project_registry import ProjectRegistryService


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    project = tmp_path / "sample-project"
    project.mkdir()
    (project / "README.md").write_text("demo", encoding="utf-8")
    return project


@pytest.fixture
def registry(
    config_manager: ConfigManager, project_dir: Path
) -> ProjectRegistryService:
    config_manager.bootstrap_defaults()
    config = config_manager.load()
    db_path = config.resolved_database_path(config_manager.config_dir)
    DatabaseInitService(db_path).initialize()
    return ProjectRegistryService(db_path)


def test_schema_includes_projects_table(config_manager: ConfigManager) -> None:
    config_manager.bootstrap_defaults()
    config = config_manager.load()
    db_path = config.resolved_database_path(config_manager.config_dir)
    DatabaseInitService(db_path).initialize()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        version = get_schema_version(conn)
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(projects)").fetchall()
        }

    assert "projects" in tables
    assert version == SCHEMA_VERSION
    assert columns == {
        "id",
        "name",
        "path",
        "created_at",
        "updated_at",
        "last_opened_at",
        "preferred_ide",
        "is_active",
        "category",
        "status",
        "notes",
        "last_refreshed_at",
        "sidebar_order",
    }


def test_add_project(registry: ProjectRegistryService, project_dir: Path) -> None:
    record = registry.add("demo", str(project_dir), preferred_ide="vscode")

    assert record.id == 1
    assert record.name == "demo"
    assert Path(record.path) == project_dir.resolve()
    assert record.preferred_ide == "vscode"
    assert record.last_opened_at is None
    assert record.is_active is False
    assert record.status == "active"
    assert record.notes is None


def test_duplicate_path_rejected(
    registry: ProjectRegistryService, project_dir: Path
) -> None:
    registry.add("first", str(project_dir))

    with pytest.raises(DuplicateProjectError, match="path"):
        registry.add("second", str(project_dir))


def test_duplicate_name_rejected(
    registry: ProjectRegistryService, project_dir: Path, tmp_path: Path
) -> None:
    other = tmp_path / "other-project"
    other.mkdir()
    registry.add("demo", str(project_dir))

    with pytest.raises(DuplicateProjectError, match="name"):
        registry.add("demo", str(other))


def test_invalid_path_rejected(registry: ProjectRegistryService, tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(ValidationError, match="does not exist"):
        registry.add("demo", str(missing))


def test_empty_name_rejected(
    registry: ProjectRegistryService, project_dir: Path
) -> None:
    with pytest.raises(ValidationError, match="name"):
        registry.add("   ", str(project_dir))


def test_add_project_with_category(registry: ProjectRegistryService, project_dir: Path) -> None:
    record = registry.add("demo", str(project_dir), category="Freelance Work")
    assert record.category == "Freelance Work"


def test_add_project_defaults_category(registry: ProjectRegistryService, project_dir: Path) -> None:
    record = registry.add("demo", str(project_dir))
    assert record.category == "Personal Projects"


def test_remove_project(registry: ProjectRegistryService, project_dir: Path) -> None:
    record = registry.add("demo", str(project_dir))
    removed = registry.remove(str(record.id))

    assert removed.id == record.id
    assert registry.list_projects() == []


def test_reorder_projects(registry: ProjectRegistryService, tmp_path: Path) -> None:
    ids = []
    for name in ("alpha", "beta", "gamma"):
        project_dir = tmp_path / name
        project_dir.mkdir()
        record = registry.add(name, str(project_dir))
        ids.append(record.id)

    records = registry.reorder_projects([ids[2], ids[0], ids[1]])
    assert [record.id for record in records] == [ids[2], ids[0], ids[1]]
    assert [record.sidebar_order for record in records] == [1, 2, 3]


def test_add_project_assigns_sidebar_order(
    registry: ProjectRegistryService, project_dir: Path, tmp_path: Path
) -> None:
    first = registry.add("first", str(project_dir))
    other = tmp_path / "other"
    other.mkdir()
    second = registry.add("second", str(other))
    assert first.sidebar_order == 1
    assert second.sidebar_order == 2


def test_open_updates_last_opened_at(
    registry: ProjectRegistryService, project_dir: Path
) -> None:
    record = registry.add("demo", str(project_dir))
    assert record.last_opened_at is None

    opened = registry.open_project("demo")

    assert opened.last_opened_at is not None
    assert opened.updated_at == opened.last_opened_at


def test_open_by_id(registry: ProjectRegistryService, project_dir: Path) -> None:
    record = registry.add("demo", str(project_dir))
    opened = registry.open_project(str(record.id))
    assert opened.last_opened_at is not None


def test_get_info_not_found(registry: ProjectRegistryService) -> None:
    with pytest.raises(ProjectError, match="not found"):
        registry.get_info("missing")


def test_inaccessible_folder_rejected(
    registry: ProjectRegistryService, project_dir: Path
) -> None:
    with patch("grafid.services.project_validation.os.listdir") as listdir:
        listdir.side_effect = PermissionError("access denied")
        with pytest.raises(ValidationError, match="Cannot access directory"):
            registry.add("demo", str(project_dir))


def test_schema_upgrade_from_v1_database(config_manager: ConfigManager) -> None:
    """Legacy 1A databases gain the projects table on re-initialization."""
    config_manager.bootstrap_defaults()
    config = config_manager.load()
    db_path = config.resolved_database_path(config_manager.config_dir)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                value TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO schema_meta (key, value) VALUES ('version', '1')"
        )
        conn.commit()

    DatabaseInitService(db_path).initialize()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        version = get_schema_version(conn)

    assert "projects" in tables
    assert version == SCHEMA_VERSION
