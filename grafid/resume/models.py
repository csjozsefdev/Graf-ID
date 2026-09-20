"""Resume engine data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from grafid.models.session import WorkSessionRecord
from grafid.models.snapshot import GitSnapshotRecord, PersistedFindingRecord, ScanSnapshotRecord
from grafid.resume.workflow_artifacts import WorkflowArtifact

ResumeMode = Literal["short", "detailed"]


@dataclass(frozen=True)
class ResumeBundle:
    """All persisted inputs used to build a resume summary."""

    project_id: int
    project_name: str
    project_path: str
    session: WorkSessionRecord | None
    snapshot: ScanSnapshotRecord | None
    findings: tuple[PersistedFindingRecord, ...]
    git: GitSnapshotRecord | None
    using_active_session: bool
    workflow_artifacts: tuple[WorkflowArtifact, ...] = ()


@dataclass(frozen=True)
class ResumeSection:
    """One labeled block in a resume summary."""

    priority: int
    title: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class ResumeSummary:
    """Generated deterministic resume output."""

    project_name: str
    mode: ResumeMode
    sections: tuple[ResumeSection, ...]
    body: str
    snapshot_id: int | None
    session_id: int | None
    resume_id: int | None = None


@dataclass(frozen=True)
class ResumeSummaryRecord:
    """One persisted resume summary for history comparison."""

    id: int
    project_id: int
    session_id: int | None
    snapshot_id: int | None
    mode: str
    summary_body: str
    generated_at: str
