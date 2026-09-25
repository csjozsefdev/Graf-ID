"""The shipped licenses: notices file, LICENSE and CPython's license must stay wired into the installer."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTICES = REPO_ROOT / "THIRD_PARTY_NOTICES.md"


def _pinned_runtime_packages() -> list[str]:
    lines = (REPO_ROOT / "packaging" / "runtime-requirements.txt").read_text(encoding="utf-8").splitlines()
    pins = [re.match(r"^([A-Za-z0-9_.-]+)==", line) for line in lines]
    return [match.group(1) for match in pins if match]


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def test_notices_file_covers_every_pinned_runtime_package() -> None:
    text = NOTICES.read_text(encoding="utf-8")
    listed = {_normalize(m) for m in re.findall(r"^\| ([^| ]+) \|", text, re.MULTILINE)}
    missing = [name for name in _pinned_runtime_packages() if _normalize(name) not in listed]
    assert _pinned_runtime_packages(), "runtime-requirements.txt has no pins?"
    assert not missing, f"THIRD_PARTY_NOTICES.md is missing runtime packages: {missing}"


def test_notices_file_has_the_core_license_texts() -> None:
    text = NOTICES.read_text(encoding="utf-8")
    assert "| CPython |" in text
    assert "PYTHON SOFTWARE FOUNDATION LICENSE" in text.upper()
    assert "Permission is hereby granted, free of charge" in text  # MIT text
    assert "Apache License" in text


def test_installer_ships_the_license_files() -> None:
    conf = json.loads((REPO_ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    resources = conf["bundle"]["resources"]
    assert resources["../../LICENSE"] == "LICENSE.txt"
    assert resources["../../THIRD_PARTY_NOTICES.md"] == "THIRD_PARTY_NOTICES.md"
    assert (REPO_ROOT / "LICENSE").is_file()


def test_runtime_build_ships_and_audits_the_cpython_license() -> None:
    script = (REPO_ROOT / "packaging" / "build_runtime.ps1").read_text(encoding="utf-8")
    assert script.count("LICENSE-PYTHON.txt") >= 2  # copied, and required by the payload audit
