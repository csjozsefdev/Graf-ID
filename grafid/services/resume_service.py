"""Orchestrate deterministic resume generation and persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from grafid.core.exceptions import ResumeError
from grafid.db.connection import DatabaseConnection
from grafid.db.repositories.resume_repository import ResumeRepository
from grafid.resume.models import ResumeSummaryRecord
from grafid.resume.generator import ResumeSummaryGenerator
from grafid.resume.loader import ResumeDataLoader
from grafid.resume.models import ResumeBundle, ResumeMode, ResumeSummary
from grafid.resume.workflow_artifacts import load_workflow_artifacts
from grafid.utils.logging_setup import get_logger

logger = get_logger("resume")


class ResumeService:
    """Generate and store explainable resume summaries."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._loader = ResumeDataLoader(db_path)
        self._generator = ResumeSummaryGenerator()

    def generate_resume(
        self,
        project_id: int,
        *,
        mode: ResumeMode = "short",
        persist: bool = True,
        replace_latest_short: bool = False,
    ) -> ResumeSummary:
        """
        Build a resume summary from stored project state.

        Does not call scanner or git subprocesses.
        """
        logger.info("Generating resume for project_id=%s mode=%s", project_id, mode)
        bundle = self._loader.load(project_id)
        artifacts = load_workflow_artifacts(bundle.project_path)
        bundle = ResumeBundle(
            project_id=bundle.project_id,
            project_name=bundle.project_name,
            project_path=bundle.project_path,
            session=bundle.session,
            snapshot=bundle.snapshot,
            findings=bundle.findings,
            git=bundle.git,
            using_active_session=bundle.using_active_session,
            workflow_artifacts=artifacts,
        )
        summary = self._generator.generate(bundle, mode=mode)

        if persist:
            trim_keep = 5 if (replace_latest_short and mode == "short") else None
            stored = self._persist_summary(project_id, summary, trim_short_keep=trim_keep)
            return ResumeSummary(
                project_name=summary.project_name,
                mode=summary.mode,
                sections=summary.sections,
                body=summary.body,
                snapshot_id=summary.snapshot_id,
                session_id=summary.session_id,
                resume_id=stored.id,
            )

        return summary

    def get_latest_stored_summary(
        self, project_id: int, *, mode: ResumeMode | None = None
    ) -> ResumeSummaryRecord | None:
        """Return the most recently persisted resume for comparison."""
        try:
            with DatabaseConnection(self._db_path) as conn:
                return ResumeRepository(conn).get_latest_for_project(
                    project_id, mode=mode
                )
        except sqlite3.Error as exc:
            raise ResumeError(f"Failed to load resume history: {exc}") from exc

    def get_previous_stored_summary(
        self, project_id: int, *, mode: ResumeMode | None = None
    ) -> ResumeSummaryRecord | None:
        """Return the summary before the most recent one (for drift detection)."""
        try:
            with DatabaseConnection(self._db_path) as conn:
                return ResumeRepository(conn).get_previous_for_project(
                    project_id, mode=mode
                )
        except sqlite3.Error as exc:
            raise ResumeError(f"Failed to load resume history: {exc}") from exc

    def _persist_summary(
        self,
        project_id: int,
        summary: ResumeSummary,
        *,
        trim_short_keep: int | None = None,
    ) -> ResumeSummaryRecord:
        """
        Persist one resume summary, optionally trimming old "short" rows first.

        Trim + insert run in one transaction (L4) — previously each used its own
        connection/commit, so a crash between them could leave the history
        trimmed to `keep` rows with the newest summary never inserted (a real,
        if narrow, data-loss window on every refresh).
        """
        try:
            with DatabaseConnection(self._db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    if trim_short_keep is not None:
                        self._trim_short_summaries_in_transaction(
                            conn, project_id, keep=trim_short_keep
                        )
                    record = ResumeRepository(conn).insert(
                        project_id,
                        session_id=summary.session_id,
                        snapshot_id=summary.snapshot_id,
                        mode=summary.mode,
                        summary_body=summary.body,
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        except sqlite3.Error as exc:
            raise ResumeError(f"Failed to persist resume summary: {exc}") from exc

        logger.info(
            "Resume summary persisted id=%s project_id=%s",
            record.id,
            project_id,
        )
        return record

    def _trim_short_summaries_in_transaction(
        self, conn: sqlite3.Connection, project_id: int, *, keep: int
    ) -> None:
        """Keep only the newest N short resume rows per project (caller owns the transaction)."""
        rows = conn.execute(
            """
            SELECT id FROM resume_summaries
            WHERE project_id = ? AND mode = 'short'
            ORDER BY generated_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
        if len(rows) <= keep:
            return
        drop_ids = [int(r["id"]) for r in rows[keep:]]
        placeholders = ",".join("?" * len(drop_ids))
        conn.execute(
            f"DELETE FROM resume_summaries WHERE id IN ({placeholders})",
            drop_ids,
        )
