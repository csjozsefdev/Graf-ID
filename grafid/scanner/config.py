"""Scanner configuration with safe defaults."""

from __future__ import annotations

from dataclasses import dataclass, field

from grafid.core.constants import (
    SCAN_MAX_DEPTH,
    SCAN_MAX_FILE_SIZE_BYTES,
    SCAN_MAX_FILES,
    SCAN_MAX_SECONDS,
    SCAN_MAX_WARNINGS,
    SCAN_PREVIEW_MAX_CHARS,
)
from grafid.scanner.ignore import (
    DEFAULT_IGNORED_DIR_NAMES,
    DEFAULT_IGNORED_RELATIVE_PREFIXES,
)


@dataclass(frozen=True)
class ScanConfig:
    """Limits and ignore rules for a single scan run."""

    max_file_size_bytes: int = SCAN_MAX_FILE_SIZE_BYTES
    max_depth: int = SCAN_MAX_DEPTH
    preview_max_chars: int = SCAN_PREVIEW_MAX_CHARS
    max_files: int = SCAN_MAX_FILES
    max_scan_seconds: float = SCAN_MAX_SECONDS
    max_warnings: int = SCAN_MAX_WARNINGS
    ignored_dir_names: frozenset[str] = field(default_factory=lambda: DEFAULT_IGNORED_DIR_NAMES)
    ignored_relative_prefixes: frozenset[str] = field(
        default_factory=lambda: DEFAULT_IGNORED_RELATIVE_PREFIXES
    )
    extra_ignored_dir_names: frozenset[str] = field(default_factory=frozenset)
    include_preview: bool = True
