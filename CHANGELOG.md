# Changelog

All notable changes to Graf-Id are documented in this file.

Versions before 1.0.0 (0.1.x) were development builds and were never published from this repository; their entries are kept below as project history.

## [1.0.0] — 2026-09-20

First public release.

### Added

- **Project Snapshot** — compact card under **Where you left off** (current focus, open issues / blockers, recent fixes, recent improvements, suggested next step) built from a backend `ProjectContext` (exit note, handoff documents, session fields, trusted commit subjects). Scanner code markers are not used as a source; technical material moved into a collapsed **Evidence & details**
- **Named exports** — **GrafiTalk handoff** (lean, compatible JSON), **JSON** (full context with the additive `graf_id` block), **Markdown** and **TXT**, all rendered from `ProjectContext` instead of scraping UI text. The GrafiTalk contract stays v0.1. See `docs/EXPORT_IMPORT.md`
- **Export all projects** (Settings > Data) — one GrafiTalk handoff file per project into a chosen folder; no absolute paths or database ids in the files or manifest
- **Backup and restore in the app** (Settings > Data) — consistent SQLite backup zip; restore verifies size/compression ratio/integrity, migrates a temporary copy, keeps a safety copy of the current data and swaps atomically. Settings are never overwritten unless explicitly requested, and then only an allowlist
- **Import context** — validate a handoff file, review a preview, and explicitly add it to (or replace) the project notes; refused if the notes changed since the preview
- **Handoff chain discovery** — follow markdown links from `HANDOVER.md` / `HANDOFF.md` to `PROJECT_CONTINUATION.md` and related allowlisted workflow files (bounded depth)
- **Refresh diagnostics** — richer `RefreshResult` / IPC payload for scan timing and source attribution
- **Coding Agent launcher** — a new, deliberately minimal "Open Project" path for interactive CLI tools (Claude Code and Codex CLI built in, plus user-defined custom agents), separate from the existing Editors path: no work session, no process-lifecycle tracking, no Exit Note. Settings gains an Editors/Coding Agents opener split and add/edit/remove with PATH- or explicit-path-based availability detection. The Claude Code / Codex CLI presets are optional: removable and restorable, and accept an explicit executable override that takes priority over PATH detection (an invalid override is reported, never silently replaced). Removing an agent resets any default/project opener that used it to Auto Detect / the default, with a notice. Imported bundles cannot supply agent definitions or overrides. See `docs/CODING_AGENTS.md`.
- **Clean Rust build cache** — detect and clean `target/` directories for registered Rust projects from the dashboard; the target directory is always passed explicitly, so a developer's own `CARGO_TARGET_DIR` override can never cause the wrong directory to be cleaned or sized
- **Dockerized, reproducible build/test environment** — a `Dockerfile` (`test` and `rust-check` targets) that runs the full Python suite, the frontend suite/build/typecheck, and `cargo check`/`cargo test` without any host setup; see `docs/DOCKER.md`
- **In-app version and license info** — Settings now shows the app version, license, and repository link

### Changed

- **Smaller, cleaner installers** — the embedded Python runtime no longer contains CPython's test suite, IDLE, Tkinter/turtle, ensurepip, lib2to3, venv, pydoc data, msilib, test extension modules, `grafid/tests`, third-party test folders or developer bytecode. Bytecode is compiled at build time with the pinned Python 3.12.10, and the build fails on any leftover. Stale `target/release/runtime` / `bundle` output is cleared by every release entry point (`build_release.ps1` and `npm run tauri:build`). `pytest .` no longer recurses into the bundled runtimes
- **Project wake transition** — overlay stays active until the selected IDE is ready; slow startups loop the intro video and show a longer-startup projector message; **Skip** dismisses overlay and runs pending post-fade actions
- **Wake transition hardening** — failed or skipped launch no longer leaves `openProjectBusy` stuck when the overlay was already dismissed
- **Grafi advisor** — priority-ranked briefs (missing path, blocker, refresh gap, dirty git, thin continuity)
- **Grafi Helping Mode tooltips** — hover/focus tips anchored to controls via `data-grafi-help`; critical alerts override help; **Critical alerts only** suppresses non-critical tooltips
- **Resume panel hierarchy** — **Where you left off**, then **Project Snapshot**, then collapsed **Evidence & details**
- **Git sidebar chip** — labels **Git: clean** / **Git: uncommitted** (was generic Clean/Dirty)
- **Frameless desktop shell** — custom close control, work-area layout, tray hide/quit policy
- Documentation refresh — README, HANDOVER, PROJECT_CONTINUATION, architecture summary
- Project wake transition loop behavior improved (smoother editor-readiness handling)
- Desktop UX polish: tray restore behavior, Windows subprocess hygiene
- Packaging docs clarified: venv requirement and embedded runtime layout

### Removed

- **Legacy startup card / Grafi-bubble pipeline** — the backend built and persisted a startup summary on every launch that the desktop UI never showed. Gone: the `startup_card`, `startup_summary` and `passive_runtime` bootstrap keys, the `startup-card`, `dismiss-startup` and `resume-preview` IPC commands, their Tauri wrappers, and the summary printout of `graf-id startup` (it still initialises config/DB and checks integrity). The `startup_summaries` table stays in the schema for existing databases but is no longer read or written
- **Unused desktop commands** — Tauri wrappers no UI code called (`ipc_health`, `ipc_dashboard`, `ipc_open_folder`, `ipc_usage_insights`, `ipc_start_session`, `ipc_session_timeline`, `ipc_set_default_project_opener`, `ipc_update_project`, `open_project_terminal`); the Python IPC/CLI commands behind them remain
- **Old Pretty Print export builder**, the never-read `source_weights` config module, a duplicate `open_explorer` launch field, unfinished Scan Health UI leftovers, and other dead code, orphan assets, committed logs and one-off scripts
- Icons for Android, iOS and Store packaging that no build uses

### Fixed

- **Scanner noise** — virtualenv variants such as `.venv-314-dev` were scanned (257 of 258 findings of one project came from third-party code); `.venv-*`, `venv-*`, `site-packages` and any folder with a `pyvenv.cfg` are now skipped, and stale findings are filtered at read time
- **Restore could destroy data** — a corrupt backup restored with `--replace` turned a healthy database into unreadable garbage, a 200 MB "zip bomb" was written unconditionally and `config.json` was silently overwritten; restore is now verified, size-limited, transactional in effect and never touches settings by default
- **Exports leaked out-of-project content** — a parent-folder document could end up in an exported focus; parent-folder documents are now UI-only and never exported
- **GrafiTalk handoff quality** — `next_steps` was always empty while "Suggested next step" and scanner junk landed in `changes`; the handoff is now built from structured context
- **GrafiTalk inbox** — no longer defaults to the source checkout (unwritable in an installed app), and its manifest no longer contains absolute user paths
- `grafid.__version__` still reported 0.1.0

### Security and reliability

A full internal security and reliability audit was completed and closed out before this release:

- **Path safety** — the project scanner and workflow-artifact reader no longer follow symlinks or NTFS junctions outside a registered project's root; imported config bundles are treated as untrusted input (a restored bundle can no longer silently redirect the "Open Project" editor launch)
- **Data integrity** — refresh/session/registry writes are now atomic; snapshot retention can no longer prune an active session's data
- **Scanner hardening** — workflow-artifact reads are bounded, a quadratic-time markdown-link regex was fixed, and scan/git resource growth is capped
- **IPC hardening** — IPC waits are timeout-bound, editor lifecycle is tracked per project instead of globally, and PID-liveness checks were hardened (including a POSIX-specific fix so `pid 0` correctly reports as not-alive, matching existing Windows behavior)
- **Frontend** — per-project state is now isolated (no cross-project cache mutation), and lifecycle races around session/editor close were hardened
- **Terminal launch (Rust)** — removed a theoretical shell-injection-shaped pattern from Windows terminal-launch command construction (not reachable in practice — NTFS paths can't contain the character it depended on — but the safer pattern is kept)
- Free-text field length limits, and import-manifest `schema_version` validation
- Test suite hardened so a test can no longer launch a real external editor process
- One risk reviewed and accepted as documented, not code-changed: raw-path Open Folder/Terminal commands (see `SECURITY.md`)
- Known npm dev-dependency advisories resolved via non-breaking updates (build/test tooling only; none reach the packaged app)

## [0.1.2] — 2026-06-08

### Added

- **Grafi Helping Mode** — hover and keyboard focus tips on dashboard controls; critical warnings override normal help
- **Project wake transition** — MP4 intro with editor-readiness probe, Skip control, and reduced-motion fast path
- **Sidebar project reorder** — drag-and-drop order persisted in SQLite (schema v11, `sidebar_order`)
- **System tray** — double-click tray icon restores main window; single click opens menu only
- GrafiTalk handoff export contract v0.1 (JSON/Markdown/TXT)
- `docs/CLEANUP.md` — dev env reset, git Clean/Dirty chip, tray, WebView2 shutdown note

### Changed

- Grafi advisor positioned beside the sidebar (no overlap with project list or navigation)
- Helping Mode tooltips anchor to UI controls; status messages stay in the bottom-left advisor
- Resume panel hierarchy: only the first primary block uses strong green styling; notes and metadata are secondary
- Export buttons visually de-emphasized relative to Open project and Refresh context
- History page shows encouraging copy when only one snapshot exists
- Startup splash uses dark background (`#0a0a0a`) to avoid white flash

### Fixed

- Windows console flash during editor lifecycle polling — Win32 process probe instead of `tasklist` subprocess
- Hidden subprocess windows on Windows (`CREATE_NO_WINDOW` for IPC, explorer, editor launch)
- Dev bootstrap failure after packaged install — strip inherited `PYTHONHOME` in IPC subprocess env
- Backend regression tests aligned with schema v11 and GrafiTalk export shape
- Grafi fully hidden when “Show Grafi advisor” is disabled (removed duplicate static helper)
- Open Project Explorer fallback uses wake snapshot `projectPath` (registered root, at most once)
- IDE normalization contract documented; unknown tokens raise `ValidationError`

### Removed

- Experimental Grafi image previews and intermediate packaging assets from the release tree
- Redundant Settings hint text under Grafi advisor section

## [0.1.1] — 2026-06-08

### Added

- **Settings — Python backend presets:** Auto Detect, System Python, `.venv`, Conda, Poetry, uv, Custom Path (with Browse)
- **Settings — editor presets:** Cursor, VS Code, PyCharm, IntelliJ IDEA, Visual Studio, Notepad++, Explorer, Custom Path
- `docs/SOURCES.md` — plain-language guide to what Refresh context reads from projects
- `NEXT.md` — maintainer continuity note at repo root

### Changed

- **Where you left off** preview length increased to **320 characters**, truncated on word boundaries (not mid-word)
- **Dashboard hierarchy:** Session and Code Markers sections use secondary styling; Where You Left Off stays primary
- Sidebar summary preview uses word-boundary truncation (up to ~280 characters)

### Fixed

- Refresh Context crash on projects with `CHANGELOG.md` (`workflow_changelog` KeyError in resume generator)
- Packaged builds prefer bundled Python over stale `GRAFID_PYTHON` from the environment
- Clearer desktop error when backend commands fail (`backend_command_failed` vs misleading `.venv` hint)

## [0.1.0] — 2026-05-22

### Added

- Desktop app (Tauri 2 + React) with sidebar project list, dashboard, History page, and Settings
- Add Project dialog, Remove project (⋯ menu), Open project, Refresh context, Export (JSON/MD/TXT)
- Deterministic resume engine from local files, git snapshots, and session notes
- Python IPC backend with SQLite persistence (schema v10)
- Embedded Python runtime packaging for Windows (MSI + NSIS)
- GrafiTalk inbox export and zip backup/import
- Git read-only integration with porcelain status parsing
- CI workflow (pytest, npm test/build/audit, cargo check/test)
- LICENSE (MIT), SECURITY.md, and release documentation

### Fixed

- Git porcelain parsing: preserve leading whitespace from `git status`; handle untracked (`??`) and rename lines
- Bootstrap per-project isolation, history row skip, path accessibility checks
- Frontend dependency audit (Vite 6 / Vitest 4.1.8 — zero high/critical npm audit findings)
- Deterministic packaged runtime via locked `packaging/runtime-requirements.txt`
- Documentation sync: schema 10, Graf-Id naming, Add Project UI, functional Settings

### Security

- Minimal Content-Security-Policy for Tauri shell (replaces `csp: null`)
- Documented Tauri capability permissions in SECURITY.md

### Known limitations

- End session: CLI/IPC only (no desktop modal in v1.0)
- Project metadata edit: CLI/IPC only
- Windows-first packaged release; unsigned installers
- Git features require `git` on system PATH
