"""Bounded project context scan for refresh (no background daemon)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from grafid.core.exceptions import ProjectError, ScanError, SnapshotError
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.project_repository import ProjectRepository
from grafid.git import GitReadService
from grafid.scanner import ProjectScannerService
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.refresh_result import RefreshResult
from grafid.services.snapshot_persistence import SnapshotPersistenceService
from grafid.services.snapshot_retention import SnapshotRetentionService
from grafid.utils.datetime_utils import utc_now_iso
from grafid.utils.logging_setup import get_logger

logger = get_logger("context_refresh")


def refresh_project_scan(
    db_path: Path,
    project_id: int,
    *,
    git_only: bool = False,
) -> RefreshResult:
    """
    Run bounded filesystem scan and/or git snapshot for one project.

    When git_only=True, skips filesystem walk and only persists git state
    against the latest snapshot when possible.
    """
    registry = ProjectRegistryService(db_path)
    record = registry.get_info(str(project_id))
    project_path = Path(record.path)
    if not project_path.is_dir():
        raise ProjectError(f"Project path is not accessible: {record.path}")

    git_ok = True
    git_error: str | None = None
    git_state = None
    try:
        git_state = GitReadService().collect(project_path)
    except Exception as exc:  # noqa: BLE001 — git optional
        git_ok = False
        git_error = str(exc)
        logger.warning("Git collection failed for %s: %s", project_path, exc)

    if git_only:
        from grafid.db.repositories.git_snapshot_repository import GitSnapshotRepository
        from grafid.db.repositories.snapshot_repository import SnapshotRepository

        # H1: git-only previously only bumped last_refreshed_at (and found the
        # latest snapshot id) without ever persisting the freshly collected
        # git_state — the dashboard's git chip stayed stale after a git-only
        # refresh. It now upserts the git row for that same snapshot, so a
        # branch switch/new commit/dirty-state change is reflected without
        # requiring a full file rescan.
        snapshot_id: int | None = None
        refreshed_at = utc_now_iso()
        try:
            with DatabaseConnection(db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    latest = SnapshotRepository(conn).list_history_for_project(
                        project_id, limit=1
                    )
                    if latest and git_state is not None:
                        snapshot_id = latest[0].snapshot_id
                        GitSnapshotRepository(conn).upsert(snapshot_id, git_state)
                    ProjectRepository(conn).set_last_refreshed(project_id, refreshed_at)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        except sqlite3.Error as exc:
            raise SnapshotError(f"Failed to persist git-only refresh: {exc}") from exc

        return RefreshResult(
            scan_ok=True,
            snapshot_id=snapshot_id,
            git_ok=git_ok,
            git_error=git_error,
            mode="git_only",
            last_refreshed_at=refreshed_at,
        )

    scanner = ProjectScannerService()
    scan_started_at = utc_now_iso()
    try:
        scan_result = scanner.scan_project(project_path)

        warnings_count = len(scan_result.warnings)
        skipped_files_count = scan_result.skipped_count
        scanned_files_count = scan_result.scanned_count
        findings_count = scan_result.findings_count
        duration_seconds = scan_result.duration_seconds
        scan_finished_at = utc_now_iso()

    except ScanError as exc:
        scan_error = str(exc)
        logger.warning("Scan failed for project_id=%s: %s", project_id, exc)
        return RefreshResult(
            scan_ok=False,
            scan_error=scan_error,
            git_ok=git_ok,
            git_error=git_error,
            mode="full",
        )

    # H4: snapshot insert + findings + git state + retention pruning + the
    # project's last_refreshed_at update are one business operation — all of it
    # happens in a single transaction, so a crash partway through (process
    # killed, OOM, forced quit) can no longer leave a new snapshot committed
    # while last_refreshed_at silently stays stale, or a pruned/un-pruned
    # mismatch between separately-committed steps.
    persistence = SnapshotPersistenceService(db_path)
    retention = SnapshotRetentionService(db_path)
    refreshed_at = utc_now_iso()
    pruned = 0
    try:
        with DatabaseConnection(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                snapshot = persistence.insert_snapshot_in_transaction(
                    conn, project_id, scan_result, git_state=git_state
                )
                pruned = retention.apply_for_project(project_id, connection=conn)
                ProjectRepository(conn).set_last_refreshed(project_id, refreshed_at)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    except SnapshotError:
        raise
    except sqlite3.Error as exc:
        raise SnapshotError(f"Failed to persist context refresh: {exc}") from exc

    snapshot_id = snapshot.id
    logger.info(
        "Context refresh scan persisted snapshot_id=%s project_id=%s",
        snapshot.id,
        project_id,
    )

    return RefreshResult(
        scan_ok=True,
        snapshot_id=snapshot_id,
        git_ok=git_ok,
        git_error=git_error,
        warnings_count=warnings_count,
        skipped_files_count=skipped_files_count,
        scanned_files_count=scanned_files_count,
        findings_count=findings_count,
        duration_seconds=duration_seconds,
        snapshots_pruned=pruned,
        scan_started_at=scan_started_at,
        scan_finished_at=scan_finished_at,
        files_considered=scanned_files_count + skipped_files_count,
        files_scanned=scanned_files_count,
        files_skipped=skipped_files_count,
        cache_used=False,
        mode="full",
        last_refreshed_at=refreshed_at,
    )
