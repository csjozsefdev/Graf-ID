"""The app version is declared in several manifests; a release must not ship them out of step."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import grafid

REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP = REPO_ROOT / "desktop"


def _toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _declared_versions() -> dict[str, str]:
    package_lock = _json(DESKTOP / "package-lock.json")
    cargo_lock = (DESKTOP / "src-tauri" / "Cargo.lock").read_text(encoding="utf-8")
    locked = re.search(r'name = "graf-id-desktop"\s+version = "([^"]+)"', cargo_lock)
    versions = {
        "grafid.__version__": grafid.__version__,
        "pyproject.toml": _toml(REPO_ROOT / "pyproject.toml")["project"]["version"],
        "desktop/package.json": _json(DESKTOP / "package.json")["version"],
        "desktop/package-lock.json": package_lock["version"],
        "desktop/package-lock.json (root package)": package_lock["packages"][""]["version"],
        "desktop/src-tauri/tauri.conf.json": _json(DESKTOP / "src-tauri" / "tauri.conf.json")["version"],
        "desktop/src-tauri/Cargo.toml": _toml(DESKTOP / "src-tauri" / "Cargo.toml")["package"]["version"],
    }
    if locked:
        versions["desktop/src-tauri/Cargo.lock"] = locked.group(1)
    return versions


def test_every_manifest_declares_the_same_version() -> None:
    versions = _declared_versions()
    assert len(set(versions.values())) == 1, f"version drift: {versions}"


def test_version_is_plain_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", grafid.__version__), grafid.__version__
