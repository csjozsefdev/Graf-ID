"""Real-world workflow scenarios for personal usage validation."""

from __future__ import annotations

import json

import pytest

from grafid.config.manager import ConfigManager
from grafid.ipc.handlers import handle_bootstrap
from grafid.observability.journal import journal_path_for, record_event, summarize_journal
from grafid.services.session_service import SessionService


@pytest.fixture
def journal_enabled_config(temp_config_dir, monkeypatch):
    monkeypatch.setenv("GRAFID_DATA_DIR", str(temp_config_dir))
    monkeypatch.setenv("GRAFID_USAGE_JOURNAL", "1")
    mgr = ConfigManager(config_dir=temp_config_dir)
    config = mgr.load()
    config.usage_journal = True
    mgr.save(config)
    return mgr


def test_usage_journal_records_events(journal_enabled_config) -> None:
    record_event(
        "test.event",
        config_dir=journal_enabled_config.config_dir,
        config=journal_enabled_config.load(),
        sample=True,
    )
    path = journal_path_for(journal_enabled_config.config_dir)
    assert path.is_file()
    row = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["event"] == "test.event"
    assert row["sample"] is True


def test_usage_summary_friction_hints(journal_enabled_config) -> None:
    cfg = journal_enabled_config.load()
    for _ in range(4):
        record_event(
            "ipc.bootstrap",
            config_dir=journal_enabled_config.config_dir,
            config=cfg,
        )
    for _ in range(4):
        record_event(
            "ipc.dismiss_startup",
            config_dir=journal_enabled_config.config_dir,
            config=cfg,
            dismissed=True,
        )
    summary = summarize_journal(config_dir=journal_enabled_config.config_dir)
    assert summary["friction_hints"]


def test_night_skip_notes_next_day_bootstrap(
    db_path, config_manager, project_id: int, journal_enabled_config, monkeypatch
) -> None:
    """Late close without notes; next launch still boots and shows continuity hooks."""
    monkeypatch.setenv("GRAFID_DATA_DIR", str(config_manager.config_dir))
    sessions = SessionService(db_path)
    sessions.start_session(project_id)
    sessions.close_active_session_for_project(project_id, skip_notes=True)

    summary = summarize_journal(config_dir=config_manager.config_dir)
    assert summary["event_counts"].get("session.close_skip_notes", 0) >= 1

    response = handle_bootstrap(config_manager=config_manager)
    assert response.ok is True
    assert response.data is not None
    assert len(response.data["projects"]) >= 1


def test_bootstrap_debug_timings_when_enabled(config_manager, monkeypatch) -> None:
    monkeypatch.setenv("GRAFID_DEBUG_TIMING", "1")
    response = handle_bootstrap(config_manager=config_manager)
    assert response.ok is True
    assert response.data is not None
    timings = response.data.get("debug_timings")
    assert isinstance(timings, list)
    assert any(t["operation"] == "startup" for t in timings)
