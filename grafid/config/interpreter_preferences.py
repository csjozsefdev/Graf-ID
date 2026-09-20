"""Python interpreter preset keys and validation for config.json."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from grafid.core.exceptions import ConfigError

PYTHON_INTERPRETER_MODE_KEY = "python_interpreter_mode"
PYTHON_INTERPRETER_CUSTOM_PATH_KEY = "python_interpreter_custom_path"

_VALID_INTERPRETER_MODES = frozenset(
    {
        "auto",
        "system",
        "venv",
        "conda",
        "poetry",
        "uv",
        "custom",
    }
)

_UI_INTERPRETER_OPTIONS: tuple[tuple[str, str], ...] = (
    ("auto", "Auto Detect"),
    ("system", "System Python"),
    ("venv", ".venv (Virtual Environment)"),
    ("conda", "Conda"),
    ("poetry", "Poetry"),
    ("uv", "uv"),
    ("custom", "Custom Path"),
)


def list_interpreter_options() -> list[dict[str, str]]:
    """Options for the Settings UI."""
    return [{"id": token, "label": label} for token, label in _UI_INTERPRETER_OPTIONS]


def normalize_python_interpreter_mode(value: Any) -> str:
    """Normalize stored interpreter preset."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "auto"
    token = str(value).strip().lower()
    aliases = {
        "auto detect": "auto",
        "autodetect": "auto",
        "system python": "system",
        "python": "system",
        "virtual environment": "venv",
        ".venv": "venv",
        "custom path": "custom",
    }
    normalized = aliases.get(token, token)
    if normalized not in _VALID_INTERPRETER_MODES:
        raise ConfigError(
            f"Invalid {PYTHON_INTERPRETER_MODE_KEY} '{value}'. "
            "Use auto, system, venv, conda, poetry, uv, or custom."
        )
    return normalized


def detect_interpreter_hint(
    mode: str,
    *,
    repo_root: Path | None = None,
    custom_path: str | None = None,
) -> str | None:
    """Best-effort path hint for the Settings UI (display only)."""
    normalized = normalize_python_interpreter_mode(mode)
    if normalized == "auto":
        return "Uses bundled runtime in release builds; dev prefers repo .venv or GRAFID_PYTHON."
    if normalized == "custom":
        if custom_path:
            path = Path(custom_path).expanduser()
            if path.is_file():
                return str(path.resolve())
            return f"Custom path not found: {path}"
        return "Choose a python.exe path below."

    resolved = resolve_interpreter_path(
        normalized,
        custom_path=custom_path,
        repo_root=repo_root,
    )
    if resolved:
        return str(resolved)
    return _missing_hint(normalized)


def resolve_interpreter_path(
    mode: str,
    *,
    custom_path: str | None = None,
    repo_root: Path | None = None,
) -> Path | None:
    """Resolve a preset to an executable path when possible."""
    normalized = normalize_python_interpreter_mode(mode)
    if normalized == "auto":
        return None
    if normalized == "custom":
        if not custom_path:
            return None
        path = Path(custom_path).expanduser()
        return path.resolve() if path.is_file() else None
    if normalized == "venv":
        return _find_venv_python(repo_root)
    if normalized == "system":
        return _find_on_path(["python", "python3", "py"])
    if normalized == "conda":
        prefix = os.environ.get("CONDA_PREFIX")
        if prefix:
            candidate = Path(prefix) / "python.exe"
            if candidate.is_file():
                return candidate
            candidate = Path(prefix) / "bin" / "python"
            if candidate.is_file():
                return candidate
        return _find_on_path(["conda"])
    if normalized == "poetry":
        return _find_on_path(["poetry"])
    if normalized == "uv":
        return _find_on_path(["uv"])
    return None


def _find_venv_python(repo_root: Path | None) -> Path | None:
    roots: list[Path] = []
    if repo_root is not None:
        roots.append(repo_root)
    cwd = Path.cwd()
    if cwd not in roots:
        roots.append(cwd)
    for root in roots:
        for relative in (
            (".venv", "Scripts", "python.exe"),
            (".venv", "bin", "python"),
        ):
            candidate = root.joinpath(*relative)
            if candidate.is_file():
                return candidate.resolve()
    return None


def _find_on_path(names: list[str]) -> Path | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found).resolve()
    return None


def _missing_hint(mode: str) -> str:
    hints = {
        "system": "System Python not found on PATH.",
        "venv": "No .venv found in the repo or current directory.",
        "conda": "Conda environment not detected (CONDA_PREFIX or conda on PATH).",
        "poetry": "Poetry not found on PATH.",
        "uv": "uv not found on PATH.",
    }
    return hints.get(mode, "Interpreter not detected for this preset.")
