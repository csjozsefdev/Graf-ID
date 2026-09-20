"""File type detection for scanner targets."""

from __future__ import annotations

from pathlib import Path

# Safe text/code suffixes for scan + task marker parsing (Milestone 2B).
SCANNABLE_SUFFIXES = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
    }
)
SPECIAL_NAME_PREFIXES = ("readme", "notes", "todo")


def is_scannable_file(path: Path) -> bool:
    """
    Return True for README/NOTES/TODO-style files, .md, and .txt files.

    Matching is case-insensitive on file names.
    """
    suffix = path.suffix.lower()
    if suffix in SCANNABLE_SUFFIXES:
        return True

    stem = path.stem.lower()
    if stem in SPECIAL_NAME_PREFIXES:
        return True

    name_lower = path.name.lower()
    return any(name_lower.startswith(prefix) for prefix in SPECIAL_NAME_PREFIXES)


def classify_file_type(path: Path) -> str:
    """Classify a scannable file into a stable type label."""
    name_lower = path.name.lower()
    stem_lower = path.stem.lower()
    suffix = path.suffix.lower()

    if name_lower.startswith("readme") or stem_lower == "readme":
        return "readme"
    if name_lower.startswith("notes") or stem_lower == "notes":
        return "notes"
    if name_lower.startswith("todo") and suffix != ".md":
        return "todo"
    suffix_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".md": "markdown",
        ".txt": "text",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
    }
    return suffix_map.get(suffix, "text")
