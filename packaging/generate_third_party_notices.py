"""Generate THIRD_PARTY_NOTICES.md: the licenses of everything Graf-Id ships or links.

What is covered (the parts that end up inside the installers):
  * CPython, the interpreter embedded in the runtime (its license text, from the base install)
  * the Python packages in the built runtime (Lib/site-packages/*.dist-info)
  * the npm packages the frontend depends on at run time (package-lock.json, non-dev)
  * the Rust crates linked into the desktop shell (cargo metadata, normal dependencies,
    Windows target)

Run from the repository root after `npm ci` and a runtime build (the venv Python is fine):

    .venv\\Scripts\\python.exe packaging\\generate_third_party_notices.py
    .venv\\Scripts\\python.exe packaging\\generate_third_party_notices.py --check

The output has no timestamps, so regenerating an unchanged dependency set produces no diff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "THIRD_PARTY_NOTICES.md"
DESKTOP = REPO / "desktop"
TAURI = DESKTOP / "src-tauri"
RUNTIME_SITE = TAURI / "runtime" / "Lib" / "site-packages"
RUST_TARGET = "x86_64-pc-windows-msvc"
LICENSE_FILE = re.compile(r"^(licen[cs]e|copying|unlicense|notice)([-_. ].*)?$", re.IGNORECASE)


@dataclass
class Component:
    name: str
    version: str
    license: str
    source: str = ""
    texts: list[str] = field(default_factory=list)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def license_texts(directory: Path, depth: int = 1) -> list[str]:
    """Contents of the license-like files directly in ``directory`` (and one level of ``licenses/``)."""
    found: list[str] = []
    if not directory.is_dir():
        return found
    for entry in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_file() and LICENSE_FILE.match(entry.name):
            found.append(read_text(entry))
        elif entry.is_dir() and entry.name.lower() in ("licenses", "license") and depth > 0:
            found.extend(license_texts(entry, depth - 1))
    return found


def cpython() -> Component:
    base = Path(sys.base_prefix)
    license_path = base / "LICENSE.txt"
    if not license_path.is_file():
        raise SystemExit(f"CPython license not found: {license_path}")
    version = ".".join(map(str, sys.version_info[:3]))
    return Component("CPython", version, "PSF-2.0", "https://www.python.org/", [read_text(license_path)])


def python_packages() -> list[Component]:
    if not RUNTIME_SITE.is_dir():
        raise SystemExit(f"Build the runtime first (missing {RUNTIME_SITE}); run packaging/build_runtime.ps1")
    components: list[Component] = []
    for dist_info in sorted(RUNTIME_SITE.glob("*.dist-info")):
        meta: dict[str, str] = {}
        classifiers: list[str] = []
        for line in read_text(dist_info / "METADATA").splitlines():
            if not line.strip():
                break
            key, _, value = line.partition(":")
            meta.setdefault(key.strip(), value.strip())
            if key.strip() == "Classifier" and value.strip().startswith("License ::"):
                classifiers.append(value.split("::")[-1].strip())
        name = meta.get("Name", dist_info.name.split("-")[0])
        if name.lower() == "graf-id":
            continue  # the project itself (MIT, see LICENSE)
        spdx = meta.get("License-Expression") or meta.get("License") or (classifiers[0] if classifiers else "") or "see license text"
        components.append(
            Component(name, meta.get("Version", "?"), spdx.splitlines()[0][:80], meta.get("Home-page", ""), license_texts(dist_info))
        )
    return components


def npm_packages() -> list[Component]:
    lock = json.loads(read_text(DESKTOP / "package-lock.json"))
    components: list[Component] = []
    for path, info in sorted(lock["packages"].items()):
        if not path or info.get("dev") or info.get("devOptional"):
            continue
        directory = DESKTOP / path
        if not directory.is_dir():
            if info.get("optional"):
                continue  # platform-specific binary that npm did not install here
            raise SystemExit(f"{path} is not installed; run `npm ci` in desktop/ first")
        name = path.split("node_modules/")[-1]
        components.append(Component(name, info.get("version", "?"), str(info.get("license", "see license text")), "", license_texts(directory)))
    return components


def rust_crates() -> list[Component]:
    raw = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--locked", "--filter-platform", RUST_TARGET,
         "--manifest-path", str(TAURI / "Cargo.toml")],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    meta = json.loads(raw)
    packages = {p["id"]: p for p in meta["packages"]}
    nodes = {n["id"]: n for n in meta["resolve"]["nodes"]}
    root = meta["resolve"]["root"]
    seen: set[str] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        for dep in nodes[current]["deps"]:
            if any(kind.get("kind") is None for kind in dep["dep_kinds"]) and dep["pkg"] not in seen:
                seen.add(dep["pkg"])
                stack.append(dep["pkg"])
    components: list[Component] = []
    for pkg_id in sorted(seen, key=lambda i: (packages[i]["name"], packages[i]["version"])):
        pkg = packages[pkg_id]
        directory = Path(pkg["manifest_path"]).parent
        components.append(
            Component(pkg["name"], pkg["version"], pkg.get("license") or "see license text", pkg.get("repository") or "", license_texts(directory))
        )
    return components


def normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def render(sections: list[tuple[str, str, list[Component]]]) -> str:
    groups: dict[str, dict] = {}
    missing: list[Component] = []
    for _, _, components in sections:
        for component in components:
            if not component.texts:
                missing.append(component)
            for text in component.texts:
                key = hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()
                group = groups.setdefault(key, {"text": normalize(text), "users": []})
                label = f"{component.name} {component.version}"
                if label not in group["users"]:
                    group["users"].append(label)

    out = [
        "# Third-party notices",
        "",
        "Graf-Id itself is MIT-licensed (see [LICENSE](LICENSE)). The installers also contain the third-party",
        "software listed below, each under its own license. This file is generated by",
        "`packaging/generate_third_party_notices.py`; do not edit it by hand.",
        "",
        "The Microsoft Visual C++ runtime libraries (`vcruntime140*.dll`) next to the embedded Python interpreter",
        "are redistributed under Microsoft's Visual C++ Redistributable license terms.",
        "",
    ]
    for title, blurb, components in sections:
        out += [f"## {title}", "", blurb, "", "| Package | Version | License |", "|---|---|---|"]
        for c in components:
            out.append(f"| {c.name} | {c.version} | {c.license.replace('|', '/')} |")
        out.append("")

    mpl = [c for _, _, components in sections for c in components if "MPL-2.0" in c.license]
    if mpl:
        out += [
            "## Source availability (MPL-2.0)",
            "",
            "The following crates are licensed under the Mozilla Public License 2.0. Graf-Id uses them unmodified;",
            "their complete source code is available from the addresses below and from https://crates.io/.",
            "",
        ]
        out += [f"- {c.name} {c.version} - {c.source or 'https://crates.io/crates/' + c.name}" for c in mpl]
        out.append("")

    out += ["## License texts", ""]
    ordered = sorted(groups.values(), key=lambda g: (g["users"][0].lower(), g["text"][:40]))
    for number, group in enumerate(ordered, 1):
        out += [f"### {number}. Used by: {', '.join(group['users'])}", "", "```text", group["text"], "```", ""]
    if missing:
        out += ["## Packages without a license file in their distribution", ""]
        out += ["Their license is the SPDX expression in the tables above; see the project's own repository.", ""]
        out += [f"- {c.name} {c.version} ({c.license}){' - ' + c.source if c.source else ''}" for c in missing]
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if THIRD_PARTY_NOTICES.md is out of date")
    args = parser.parse_args()

    sections = [
        ("Embedded Python interpreter", "Shipped in `runtime/` (its license is also copied to `runtime/LICENSE-PYTHON.txt`).", [cpython()]),
        ("Python packages", "Installed into the embedded runtime (`runtime/Lib/site-packages`).", python_packages()),
        ("JavaScript packages (desktop UI)", "Bundled into the desktop frontend.", npm_packages()),
        ("Rust crates (desktop shell)", f"Linked into `graf-id-desktop.exe` (normal dependencies, `{RUST_TARGET}`).", rust_crates()),
    ]
    text = render(sections)
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print("THIRD_PARTY_NOTICES.md is out of date; regenerate it.", file=sys.stderr)
            return 1
        print("THIRD_PARTY_NOTICES.md is up to date.")
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    counts = ", ".join(f"{len(c)} {t.split(' (')[0].lower()}" for t, _, c in sections)
    print(f"Wrote {OUTPUT.name}: {counts}; {len(text) // 1024} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
