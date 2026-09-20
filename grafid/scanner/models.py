"""Structured scan result models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScannedFile:
    """Metadata for one scanned file."""

    path: str
    file_type: str
    modified_at: str
    size_bytes: int
    preview: str | None = None


@dataclass(frozen=True)
class TaskFinding:
    """One TODO/FIXME-style marker found in a source file."""

    file_path: str
    line_number: int
    marker: str
    text: str
    severity: str
    created_at: str


@dataclass
class ScanResult:
    """Complete result of scanning one registered project."""

    project_name: str
    project_path: str
    scanned_files: list[ScannedFile] = field(default_factory=list)
    findings: list[TaskFinding] = field(default_factory=list)
    skipped_count: int = 0
    ignored_dirs_count: int = 0
    warnings: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def scanned_count(self) -> int:
        return len(self.scanned_files)

    @property
    def findings_count(self) -> int:
        return len(self.findings)
