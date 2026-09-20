"""Persist scan results as historical snapshots."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from grafid.core.exceptions import SnapshotError
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.git_snapshot_repository import GitSnapshotRepository
from grafid.db.repositories.scan_finding_repository import ScanFindingRepository
from grafid.db.repositories.snapshot_repository import SnapshotRepository
from grafid.git.models import GitState
from grafid.models.snapshot import GitSnapshotRecord, ScanSnapshotRecord, SnapshotHistoryEntry
from grafid.scanner.models import ScanResult
from grafid.utils.datetime_utils import utc_now_iso
from grafid.utils.logging_setup import get_logger

logger = get_logger("snapshot_persistence")


class SnapshotPersistenceService:
    """
    Store scan summaries and findings without coupling to scanner traversal.

    Uses a single transaction per snapshot so partial writes roll back safely.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def save_snapshot(
        self,
        project_id: int,
        scan_result: ScanResult,
        *,
        git_state: GitState | None = None,
    ) -> ScanSnapshotRecord:
        """
        Persist one completed scan and all findings atomically (owns its own transaction).

        Raises SnapshotError when the database write fails or is interrupted.
        """
        logger.info(
            "Persisting snapshot for project_id=%s findings=%s",
            project_id,
            scan_result.findings_count,
        )

        try:
            with DatabaseConnection(self._db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    snapshot = self._insert_snapshot_row(
                        conn, project_id, scan_result, git_state=git_state
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        except SnapshotError:
            raise
        except sqlite3.Error as exc:
            logger.error("Snapshot persistence failed: %s", exc)
            raise SnapshotError(f"Failed to persist scan snapshot: {exc}") from exc
        except Exception as exc:
            logger.error("Unexpected snapshot persistence error: %s", exc)
            raise SnapshotError(f"Failed to persist scan snapshot: {exc}") from exc

        logger.info("Snapshot saved id=%s for project_id=%s", snapshot.id, project_id)
        return snapshot

    def insert_snapshot_in_transaction(
        self,
        conn: sqlite3.Connection,
        project_id: int,
        scan_result: ScanResult,
        *,
        git_state: GitState | None = None,
    ) -> ScanSnapshotRecord:
        """
        Insert a snapshot + findings + git state on an already-open transaction.

        The caller owns BEGIN/COMMIT/ROLLBACK — use this to fold the snapshot
        write into a larger atomic operation (H4: refresh_project_scan folds
        this together with retention pruning and the project's
        last_refreshed_at update into one transaction).
        """
        return self._insert_snapshot_row(conn, project_id, scan_result, git_state=git_state)

    def _insert_snapshot_row(
        self,
        conn: sqlite3.Connection,
        project_id: int,
        scan_result: ScanResult,
        *,
        git_state: GitState | None = None,
    ) -> ScanSnapshotRecord:
        scanned_at = utc_now_iso()
        snapshot_repo = SnapshotRepository(conn)
        finding_repo = ScanFindingRepository(conn)

        snapshot = snapshot_repo.insert(
            project_id,
            scanned_at=scanned_at,
            scanned_files_count=scan_result.scanned_count,
            skipped_files_count=scan_result.skipped_count,
            findings_count=scan_result.findings_count,
            duration_seconds=scan_result.duration_seconds,
            warnings_count=len(scan_result.warnings),
        )

        inserted = finding_repo.insert_many(snapshot.id, scan_result.findings)
        if inserted != scan_result.findings_count:
            raise SnapshotError(
                "Finding persistence count mismatch during snapshot save"
            )

        if git_state is not None:
            GitSnapshotRepository(conn).insert(snapshot.id, git_state)

        return snapshot

    def list_history(self, project_id: int, *, limit: int = 50) -> list[SnapshotHistoryEntry]:
        """Return previous snapshots for one project, newest first."""
        try:
            with DatabaseConnection(self._db_path) as conn:
                entries = SnapshotRepository(conn).list_history_for_project(
                    project_id, limit=limit
                )
        except sqlite3.Error as exc:
            raise SnapshotError(f"Failed to load snapshot history: {exc}") from exc

        return _validate_history_entries(entries)

    def get_latest_git_snapshot(self, project_id: int) -> GitSnapshotRecord | None:
        """Return Git metadata from the newest scan snapshot for a project."""
        try:
            with DatabaseConnection(self._db_path) as conn:
                return GitSnapshotRepository(conn).get_latest_for_project(project_id)
        except (sqlite3.Error, json.JSONDecodeError, ValueError) as exc:
            raise SnapshotError(f"Failed to load git snapshot: {exc}") from exc


def _validate_history_entries(
    entries: list[SnapshotHistoryEntry],
) -> list[SnapshotHistoryEntry]:
    valid: list[SnapshotHistoryEntry] = []
    for entry in entries:
        if entry.findings_count < 0 or entry.scanned_files_count < 0:
            logger.warning(
                "Skipping malformed history row for snapshot %s",
                entry.snapshot_id,
            )
            continue
        if entry.duration_seconds < 0:
            logger.warning(
                "Skipping malformed duration in snapshot %s",
                entry.snapshot_id,
            )
            continue
        valid.append(entry)
    return valid
