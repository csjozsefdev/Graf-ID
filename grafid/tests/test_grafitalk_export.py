"""GrafiTalk inbox export (Settings > Data > Export all projects)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grafid.core.exceptions import ValidationError
from grafid.handoff.validate import parse_handoff_bytes
from grafid.tests.grafitalk_contract import check_grafitalk_compatibility
from grafid.ipc.export_handlers import handle_export_grafitalk_inbox
from grafid.services.grafitalk_export import default_grafitalk_dir, export_grafitalk_inbox
from grafid.services.project_registry import ProjectRegistryService


def test_export_grafitalk_inbox_layout_and_contract(tmp_path: Path, db_path, project_id: int) -> None:
    out = tmp_path / "inbox"
    inbox = export_grafitalk_inbox(db_path=db_path, output_dir=out, config_dir=tmp_path)
    assert inbox == out.resolve()

    manifest = json.loads((inbox / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 1 and manifest["project_count"] == 1
    assert manifest["handoff_schema_version"] == "0.1"
    assert manifest["projects"][0]["file"] == "projects/test-project.json"
    assert (inbox / "README.md").is_file()

    body = json.loads((inbox / "projects" / "test-project.json").read_text(encoding="utf-8"))
    assert check_grafitalk_compatibility(body) == []
    assert parse_handoff_bytes((inbox / "projects" / "test-project.json").read_bytes()).data["project_name"] == "test-project"
    assert "graf_id" not in body  # inbox files are the lean contract


def test_manifest_and_files_contain_no_absolute_user_paths_or_database_ids(
    tmp_path: Path, db_path, project_id: int
) -> None:
    inbox = export_grafitalk_inbox(db_path=db_path, output_dir=tmp_path / "inbox", config_dir=tmp_path)
    everything = "".join(p.read_text(encoding="utf-8") for p in inbox.rglob("*") if p.is_file())
    project_path = str(tmp_path / "test-project")
    for needle in (project_path, project_path.replace("\\", "/"), str(db_path.parent), '"project_id"', '"path"'):
        assert needle not in everything
    assert not any(part.name[0].isdigit() and part.name.split("-")[0].isdigit() for part in (inbox / "projects").iterdir())


def test_colliding_project_names_get_distinct_files(tmp_path: Path, db_path, project_id: int) -> None:
    other = tmp_path / "other"
    other.mkdir()
    ProjectRegistryService(db_path).add("Test Project", str(other))  # same slug as "test-project"
    inbox = export_grafitalk_inbox(db_path=db_path, output_dir=tmp_path / "inbox", config_dir=tmp_path)
    names = sorted(p.name for p in (inbox / "projects").iterdir())
    assert names == ["test-project-2.json", "test-project.json"]


def test_output_folder_that_is_a_file_is_rejected(tmp_path: Path, db_path, project_id: int) -> None:
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(ValidationError, match="not a directory"):
        export_grafitalk_inbox(db_path=db_path, output_dir=blocker, config_dir=tmp_path)


def test_default_inbox_lives_in_the_data_folder_not_the_source_checkout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GRAFID_GRAFITALK_DIR", raising=False)
    assert default_grafitalk_dir(tmp_path) == tmp_path / "grafitalk-inbox"
    monkeypatch.setenv("GRAFID_GRAFITALK_DIR", str(tmp_path / "custom"))
    assert default_grafitalk_dir(tmp_path) == (tmp_path / "custom").resolve()


def test_ipc_handler_exports_to_the_chosen_folder(config_manager, db_path, project_id: int, tmp_path: Path) -> None:
    from grafid.services.runtime import reset_runtime_cache

    reset_runtime_cache()
    response = handle_export_grafitalk_inbox(str(tmp_path / "picked"), config_manager=config_manager)
    assert response.ok is True, response
    assert response.data["project_count"] == 1
    assert (tmp_path / "picked" / "projects" / "test-project.json").is_file()


def test_ipc_handler_rejects_an_empty_or_unwritable_target(config_manager, db_path, project_id: int, tmp_path: Path) -> None:
    from grafid.services.runtime import reset_runtime_cache

    reset_runtime_cache()
    assert handle_export_grafitalk_inbox("  ", config_manager=config_manager).ok is False
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert handle_export_grafitalk_inbox(str(blocker), config_manager=config_manager).ok is False
