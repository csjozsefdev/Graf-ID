"""Emit base Python install path and version tag for build_runtime.ps1."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_RUNTIME_MARKERS = ("src-tauri", "runtime", "target", "embed")


def _strip_extended_prefix(path: str) -> str:
    text = path.strip()
    if text.startswith("\\\\?\\"):
        return text[4:]
    return text


def _looks_like_embedded_runtime(path: Path) -> bool:
    normalized = str(path).replace("\\", "/").lower()
    return any(marker in normalized for marker in _RUNTIME_MARKERS)


def _venv_home_from_cfg(venv_root: Path) -> Path | None:
    cfg = venv_root / "pyvenv.cfg"
    if not cfg.is_file():
        return None
    for line in cfg.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("home"):
            continue
        _, _, value = stripped.partition("=")
        candidate = Path(value.strip())
        if (candidate / "python.exe").is_file():
            return candidate
    return None


def resolve_python_base() -> Path:
    """Return the real Python install directory used to build the embedded runtime."""
    candidates: list[Path] = []

    base_prefix = Path(_strip_extended_prefix(sys.base_prefix))
    candidates.append(base_prefix)

    venv_home = _venv_home_from_cfg(Path(sys.prefix))
    if venv_home is not None:
        candidates.append(venv_home)

    executable = Path(sys.executable).resolve()
    if executable.parent.name.lower() == "scripts":
        candidates.append(executable.parent.parent)

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if not (candidate / "python.exe").is_file():
            continue
        if _looks_like_embedded_runtime(candidate):
            continue
        return candidate

    raise SystemExit(
        "Could not resolve a non-embedded Python install. "
        f"sys.base_prefix={sys.base_prefix!r}, sys.prefix={sys.prefix!r}, "
        f"sys.executable={sys.executable!r}. "
        "Recreate the repo .venv from a system Python install."
    )


def main() -> None:
    base = resolve_python_base()
    ver = f"{sys.version_info.major}{sys.version_info.minor}"
    full_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(json.dumps({"base": _strip_extended_prefix(str(base)), "ver": ver, "full_ver": full_ver}))


if __name__ == "__main__":
    main()
