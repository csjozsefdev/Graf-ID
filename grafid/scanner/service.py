"""Project filesystem scanner service."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from grafid.core.exceptions import ScanError, ValidationError
from grafid.scanner.config import ScanConfig
from grafid.scanner.filters import classify_file_type, is_scannable_file
from grafid.scanner.ignore import (
    build_ignore_lookup,
    build_prefix_lookup,
    should_ignore_dir,
)
from grafid.scanner.models import ScanResult, ScannedFile
from grafid.scanner.reader import normalize_text_preview, read_file_text
from grafid.scanner.marker_quality import should_skip_marker_scan_file
from grafid.scanner.task_parser import parse_task_markers
from grafid.services.project_validation import normalize_project_path
from grafid.utils.logging_setup import get_logger
from grafid.utils.safe_path import is_unsafe_symlink

logger = get_logger("scanner")


class ProjectScannerService:
    """Walk a project tree and collect metadata for target text files."""

    def __init__(self, config: ScanConfig | None = None) -> None:
        self._config = config or ScanConfig()
        merged_dirs = self._config.ignored_dir_names | self._config.extra_ignored_dir_names
        self._ignore_lookup = build_ignore_lookup(merged_dirs)
        self._prefix_lookup = build_prefix_lookup(self._config.ignored_relative_prefixes)
        self._entries_processed = 0
        self._deadline = 0.0
        self._limit_hit = False

    def scan_project(
        self,
        project_path: Path | str,
        *,
        project_name: str = "",
    ) -> ScanResult:
        """
        Scan one project directory deterministically.

        Does not write to the database or spawn background workers.
        """
        started = time.perf_counter()
        root = normalize_project_path(str(project_path))
        display_name = project_name or root.name

        # M7: bound total work for a pathological tree (extreme file count or
        # a directory that is slow to enumerate/read) — reset per scan since
        # a scanner instance may be reused across scans.
        self._entries_processed = 0
        self._deadline = started + self._config.max_scan_seconds
        self._limit_hit = False

        from grafid.scanner.grafidignore import load_grafidignore, merge_ignore_names

        extra = load_grafidignore(root)
        if extra:
            merged = merge_ignore_names(self._config.ignored_dir_names, extra)
            self._ignore_lookup = build_ignore_lookup(
                merged | self._config.extra_ignored_dir_names
            )

        logger.info("Scan started for project '%s' at %s", display_name, root)

        result = ScanResult(
            project_name=display_name,
            project_path=str(root),
        )

        try:
            self._walk(root, root, depth=0, result=result)
        except ValidationError as exc:
            raise ScanError(str(exc)) from exc

        result.duration_seconds = time.perf_counter() - started
        logger.info(
            "Scan finished for '%s': scanned=%s ignored_dirs=%s skipped=%s findings=%s warnings=%s duration=%.3fs",
            display_name,
            result.scanned_count,
            result.ignored_dirs_count,
            result.skipped_count,
            result.findings_count,
            len(result.warnings),
            result.duration_seconds,
        )
        return result

    def _walk(
        self,
        root: Path,
        current: Path,
        *,
        depth: int,
        result: ScanResult,
    ) -> None:
        if depth > self._config.max_depth:
            result.skipped_count += 1
            logger.debug("Max depth reached, skipping: %s", current)
            return

        if self._scan_limit_reached(result):
            return

        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except PermissionError:
            warning = f"Permission denied accessing directory: {current}"
            self._warn(result, warning)
            result.skipped_count += 1
            logger.warning(warning)
            return
        except OSError as exc:
            warning = f"Cannot list directory: {current} ({exc})"
            self._warn(result, warning)
            result.skipped_count += 1
            logger.warning(warning)
            return

        for entry in entries:
            if self._scan_limit_reached(result):
                return

            self._entries_processed += 1

            if is_unsafe_symlink(entry):
                # Symlinks/junctions are never followed — a registered project is
                # not fully trusted content and a crafted link could otherwise
                # read files outside the project root (or loop via a cycle).
                result.skipped_count += 1
                logger.debug("Skipped symlink/reparse point: %s", entry)
                continue

            if entry.is_dir():
                if should_ignore_dir(
                    entry,
                    self._ignore_lookup,
                    root=root,
                    ignored_prefix_lookup=self._prefix_lookup,
                ):
                    result.ignored_dirs_count += 1
                    result.skipped_count += 1
                    logger.debug("Ignored directory: %s", entry)
                    continue
                self._walk(root, entry, depth=depth + 1, result=result)
                continue

            if not entry.is_file():
                result.skipped_count += 1
                continue

            if not is_scannable_file(entry):
                result.skipped_count += 1
                continue

            scanned = self._scan_file(root, entry, result)
            if scanned is not None:
                result.scanned_files.append(scanned)

    def _scan_limit_reached(self, result: ScanResult) -> bool:
        """
        M7: stop walking once the file-count cap or wall-clock budget is hit.

        The file-count check keeps ordinary runs fully deterministic (same
        stopping point every time for a given tree); the time budget is a
        safety net for a pathologically slow-to-enumerate/read tree and is
        the only source of run-to-run variance, and only for scans large
        enough to hit it.
        """
        if self._limit_hit:
            return True
        if self._entries_processed >= self._config.max_files:
            self._limit_hit = True
        elif time.perf_counter() >= self._deadline:
            self._limit_hit = True
        if self._limit_hit:
            self._warn(
                result,
                "Scan resource limit reached "
                f"(max_files={self._config.max_files}, "
                f"max_seconds={self._config.max_scan_seconds:.0f}); "
                "stopping early",
            )
        return self._limit_hit

    def _warn(self, result: ScanResult, message: str) -> None:
        """L1: cap warning list growth so a pathological tree can't exhaust memory."""
        if len(result.warnings) < self._config.max_warnings:
            result.warnings.append(message)
        elif len(result.warnings) == self._config.max_warnings:
            result.warnings.append(
                f"Further warnings suppressed after {self._config.max_warnings} "
                "(see logs for full detail)"
            )

    def _scan_file(
        self, root: Path, path: Path, result: ScanResult
    ) -> ScannedFile | None:
        try:
            stat = path.stat()
            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC).replace(
                microsecond=0
            ).isoformat()
            size_bytes = stat.st_size
        except OSError as exc:
            warning = f"Cannot stat file: {path} ({exc})"
            self._warn(result, warning)
            result.skipped_count += 1
            logger.warning(warning)
            return None

        text, read_warning = read_file_text(
            path,
            max_file_size_bytes=self._config.max_file_size_bytes,
        )
        if read_warning:
            self._warn(result, read_warning)
            result.skipped_count += 1
            if text is None:
                return None

        relative = path.relative_to(root).as_posix()

        if text is not None and not should_skip_marker_scan_file(relative):
            file_findings = parse_task_markers(
                text,
                file_path=relative,
                created_at=modified_at,
            )
            if file_findings:
                result.findings.extend(file_findings)
                logger.debug(
                    "Found %s task markers in %s", len(file_findings), relative
                )

        preview: str | None = None
        if self._config.include_preview and text is not None:
            preview = normalize_text_preview(text, self._config.preview_max_chars)

        return ScannedFile(
            path=relative,
            file_type=classify_file_type(path),
            modified_at=modified_at,
            size_bytes=size_bytes,
            preview=preview,
        )
