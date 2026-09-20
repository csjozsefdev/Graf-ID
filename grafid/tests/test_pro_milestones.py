"""PRO milestone regression tests."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path


from grafid.core.constants import SCHEMA_VERSION
from grafid.db.connection import DatabaseConnection
from grafid.db.schema import apply_schema, get_schema_version
from grafid.scanner.grafidignore import load_grafidignore
from grafid.services.snapshot_retention import DEFAULT_POLICY


def test_schema_version_is_twelve() -> None:
    assert SCHEMA_VERSION == 12


def test_migration_runner_reaches_v12(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    with DatabaseConnection(db) as conn:
        apply_schema(conn)
        version = get_schema_version(conn)
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(projects)").fetchall()
        }
        index_names = {
            row[1]
            for row in conn.execute("PRAGMA index_list(work_sessions)").fetchall()
        }
    assert version == 12
    assert "sidebar_order" in columns
    assert "idx_one_active_session_per_project" in index_names


def test_retention_policy_enabled_by_default() -> None:
    assert DEFAULT_POLICY.cleanup_enabled() is True


def test_grafidignore_loads_patterns(tmp_path: Path) -> None:
    (tmp_path / ".grafidignore").write_text("# comment\n.next\ndist\n", encoding="utf-8")
    names = load_grafidignore(tmp_path)
    assert "dist" in names or ".next" in names


def test_export_bundle_manifest(tmp_path: Path, config_manager) -> None:
    from grafid.services.db_init import DatabaseInitService
    from grafid.services.portability import export_bundle

    config = config_manager.load()
    db_path = config.resolved_database_path(config_manager.config_dir)
    DatabaseInitService(db_path).initialize(verify=False)
    zip_path = tmp_path / "bundle.zip"
    export_bundle(db_path=db_path, config_path=config_manager.config_path, output_zip=zip_path)
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as zf:
        assert "grafid-export.json" in zf.namelist()
        manifest = json.loads(zf.read("grafid-export.json"))
        assert manifest["schema_version"] == SCHEMA_VERSION


def test_summary_engine_away_label() -> None:
    from grafid.resume.summary_engine import compute_away_label

    label = compute_away_label(
        last_opened_at="2020-01-01T12:00:00+00:00",
        last_session_ended_at=None,
    )
    assert label is not None
    assert "Away" in label


# --- Freshness/staleness regressions: a stuck-open work session (no auto-close
# exists) must not be able to hide how long a project's data has actually been
# stale. Found in real use: a session opened months ago and never closed made
# an otherwise months-stale project look current. ---


def test_away_label_prioritizes_last_refreshed_at_over_session_times() -> None:
    from grafid.resume.summary_engine import compute_away_label

    ninety_days_ago = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    label = compute_away_label(
        last_opened_at=None,
        last_session_ended_at=None,
        last_refreshed_at=ninety_days_ago,
    )
    assert label is not None
    assert "90 day" in label


def test_away_label_none_for_a_freshly_refreshed_project() -> None:
    from grafid.resume.summary_engine import compute_away_label

    label = compute_away_label(
        last_opened_at=None,
        last_session_ended_at=None,
        last_refreshed_at=datetime.now(UTC).isoformat(),
    )
    assert label is None


def test_away_label_falls_back_to_session_times_when_never_refreshed() -> None:
    """A brand-new project has no last_refreshed_at yet — fall back to
    session/open times rather than showing nothing."""
    from grafid.resume.summary_engine import compute_away_label

    thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    label = compute_away_label(
        last_opened_at=thirty_days_ago,
        last_session_ended_at=None,
        last_refreshed_at=None,
    )
    assert label is not None
    assert "30 day" in label


def test_away_label_shown_for_closed_session_on_an_old_project() -> None:
    from grafid.resume.summary_engine import compute_away_label

    sixty_days_ago = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    label = compute_away_label(
        last_opened_at=None,
        last_session_ended_at=sixty_days_ago,
        last_refreshed_at=None,
    )
    assert label is not None
    assert "60 day" in label


def test_away_label_is_deterministic_across_repeated_calls() -> None:
    """Same stored timestamps must yield the same label every time — the
    label is a pure function of stored data, not in-memory app state, so an
    app restart cannot change the result on its own."""
    from grafid.resume.summary_engine import compute_away_label

    anchor = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    first = compute_away_label(
        last_opened_at=None, last_session_ended_at=None, last_refreshed_at=anchor
    )
    second = compute_away_label(
        last_opened_at=None, last_session_ended_at=None, last_refreshed_at=anchor
    )
    assert first == second


def test_build_dashboard_away_label_not_suppressed_by_active_session() -> None:
    """Regression: build_dashboard used to gate the away-label prefix on
    `not has_active_session`, so a session left open for months hid a
    90-day-stale project completely. It must show now regardless."""
    from grafid.resume.summary_engine import SummaryEngine

    stale = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    engine = SummaryEngine()
    result = engine.build_dashboard(
        project_name="test-project",
        exit_note=None,
        blocker=None,
        next_step=None,
        has_active_session=True,
        artifacts=(),
        open_task_count=None,
        has_scan=False,
        git_label=None,
        last_refreshed_at=stale,
    )
    assert result.away_label is not None
    assert "90 day" in result.away_label
    assert result.headline.startswith("Away for 90 days")
