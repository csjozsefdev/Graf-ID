# Release verification — Graf-Id 1.0.0

Measured results of the 1.0.0 release build (Windows, x64). The build procedure itself is described in [RELEASE_VERIFICATION.md](RELEASE_VERIFICATION.md).

This file is part of the release commit, so it cannot contain that commit's own hash; the `v1.0.0` tag identifies the commit. The installers were built from this tree with only this file absent (documentation is not a bundle input: Tauri bundles `runtime/` plus the built frontend and the Rust binary).

## Build environment

| Item | Value |
|------|-------|
| OS | Windows 11 Pro 10.0.26200 |
| Python (build venv and embedded runtime) | 3.12.10 (pinned in `packaging/build_runtime.ps1`) |
| Node.js / npm | 24.16.0 / 11.17.0 |
| Rust / Cargo | 1.95.0 |
| tauri-cli | 2.11.2 |

## How it was built

From a clean checkout (no `node_modules`, `target/`, `.venv` or runtime output):

1. `python -m venv .venv` and `pip install -e ".[dev]"`
2. `npm ci` in `desktop/`
3. `packaging\build_release.ps1` (icons, embedded runtime, `verify_packaged_runtime.ps1`, `tauri build`, bundled-runtime manifest comparison, `verify_release_bundle.ps1`)

The Rust build ran with `RUSTFLAGS` set to `--remap-path-prefix` for the cargo home, the rustup home and the checkout directory, so the shipped binary does not embed the builder's Windows account name or checkout path.

## Artifacts

| File | Size (bytes) | SHA-256 |
|------|-------------:|---------|
| `Graf-Id_1.0.0_x64-setup.exe` (NSIS) | 15,227,352 | `e56957f91adde31edf73d83d47e016da6ac6b0ae2281d610a39b8ffceaeb9c47` |
| `Graf-Id_1.0.0_x64_en-US.msi` (MSI) | 23,180,040 | `d976f7a2a5e3c7a80ab7ff7f93f05a08b39697c43d21505e71595e8d48bc9b6e` |
| `graf-id-desktop.exe` (binary inside both) | 10,515,456 | `0e531dec88f314663188f75f097f063c7cad33b38f8ac632c3d89cd8aebd3d09` |

Verify a download with `Get-FileHash <file> -Algorithm SHA256`.

The installers are **not code-signed** (`Get-AuthenticodeSignature` reports `NotSigned`); Windows SmartScreen may warn on first run.

## Test results (on the exact release tree)

| Check | Result |
|-------|--------|
| Python suite (`pytest`) | 825 passed |
| Frontend suite (`vitest`) | 196 passed in 35 files |
| TypeScript (`tsc --noEmit`) | clean |
| Frontend production build | OK |
| `knip` (unused code) | clean |
| `npm audit --audit-level=high` | 0 vulnerabilities |
| `cargo test --locked` | 23 passed |
| `cargo check --locked` | OK |
| Version consistency test | passed (pyproject, `grafid.__version__`, `package.json`, `package-lock.json`, `tauri.conf.json`, `Cargo.toml`, `Cargo.lock`) |
| Command-surface contract test (TypeScript client / Rust handlers / Python table) | passed |

## Release bundle checks

| Check | Result |
|-------|--------|
| Bundled runtime equals the freshly built runtime | 2,523 files, no differences |
| Packaged runtime smoke (`health`, `runtime-check`, `bootstrap`, `dashboard`) | ok |
| Release binary launch with an isolated data folder | ok, database created |
| Runtime bytecode | 1,207 `.pyc`, all `cpython-312` |
| CPython `Lib/test`, `idlelib`, `tkinter`, `ensurepip`, `grafid/tests` in the runtime | absent |
| Builder account name / checkout path in the binary | 0 occurrences |
| Builder account name / checkout path in the bundled runtime | 0 occurrences |

## Real-world smoke

40 of 40 checks passed against a scratch copy of a populated database (never the live one): open project with a custom editor, session start and Exit Note, *Where you left off* and Project Snapshot, git clean/dirty detection, coding-agent resolution, all four export formats for four projects with GrafiTalk-contract validation and path/venv leak checks, inbox export, context import, and backup / restore round trip with an integrity check.

## Not verified

- The installers were not installed on a separate clean machine; the uninstall/reinstall checklist is [UNINSTALL_REINSTALL_CHECKLIST_1.0.0.md](UNINSTALL_REINSTALL_CHECKLIST_1.0.0.md).
- The Docker test environment (`docs/DOCKER.md`) was not run for this release.
- CI runs on `windows-latest` only.
