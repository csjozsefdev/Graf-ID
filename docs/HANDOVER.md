# Graf-Id handover

## Where we left off (September 2026)

**v1.0.0** is the first public release: security/reliability audit (Milestones 1–9), a Dockerized reproducible test environment, and this version bump. Feature scope also includes the **Project Snapshot** (backend `ProjectContext`), named exports with the GrafiTalk-compatible handoff, in-app backup/restore, context import, wake transition hardening, handoff chain discovery and the coding-agent launcher.

**Next:** post-launch — see [CHANGELOG.md](../CHANGELOG.md) for what shipped in 1.0.0 vs what stayed unreleased.

*Read this if you are opening the repo six months from now — or onboarding cold.*

**Time to read:** under 10 minutes.

---

## What this project is

**Graf-Id** is a **project continuity tool for developers**. It helps you remember where you left off on local code projects.

It is **not** a task manager, PM tool, AI coding assistant, or documentation platform.

When you return to a repo after a break, Graf-Id shows a **resume summary** built from:

- Your **exit notes** (best signal — exit-note dialog after editor close, or CLI/IPC)
- **Handoff / continuation docs** — `HANDOFF.md`, `HANDOVER.md`, `PROJECT_CONTINUATION.md` and similar allowlisted names in the project
- **Git status** and modified files (fallback only)
- **TODO/FIXME markers** from a bounded scan

Everything is **local** (`%LOCALAPPDATA%\Graf-Id`). No cloud. No background watcher. You click **Refresh context** when you want an update.

---

## v1.0 desktop UI (current)

| Area | What lives there |
|------|------------------|
| **Sidebar** | Project list, filters, drag reorder, **Add project**, **⋯ → Remove from Graf-Id**, git chip |
| **Dashboard** | Project **header** (Open project, Refresh, Export) + **Resume panel** |
| **Resume panel** | **Where you left off** → **Project Snapshot** → supporting sections → folded Activity & sources |
| **History** | Separate page — scan snapshot cards |
| **Settings** | Python backend, editor, Grafi advisor + Helping Mode tooltips, journal, debug timing |

**Not on the dashboard:** manual **End session** header button, Open folder button, Remove in main panel. Removal is sidebar-only with confirmation.

**Open project** is the primary workflow action. **Refresh context**, **Export** (GrafiTalk handoff / JSON / Markdown / TXT) and **Import context…** are in the project header.

---

## Project Snapshot

Compact card below **Where you left off**, rendered from the backend `ProjectContext`:

- Current focus · Open issues / blockers · Recent fixes · Recent improvements · Suggested next step

The same object feeds every export (GrafiTalk handoff / JSON / Markdown / TXT). Scanner markers are evidence only, never a source.

**Code:** `grafid/resume/project_context.py` (domain), `human_context.py` (wiring), `grafid/handoff/` (contract, builder, renderers, validator, importer), `desktop/src/components/ProjectSnapshotCard.tsx`

---

## Grafi advisor & tooltips

- **GrafiAdvisorHost** — bottom-left briefs from `grafiAdvisorRules.ts` (path, blocker, refresh, git, continuity)
- **Helping Mode** — `GrafiHelpProvider` + `GrafiContextHelpTooltip`; topics in `grafiHelpRegistry.ts`
- Critical severity overrides help; **Critical alerts only** in Settings suppresses non-critical tooltips

---

## Wake transition

On **Open project**, `ProjectWakeTransition` may show until the editor is ready:

- MP4 intro + terminal-style projector lines (Skip available)
- Editor readiness probe in `AppShell.tsx`
- `completeWakeIfOverlayDismissed()` — failed/skipped launch must not leave `openProjectBusy` stuck

Long absence still uses the separate **Wake panel** (“Before you continue”) before the dashboard.

---

## How it works (60 seconds)

```
React desktop UI  →  Tauri (Rust)  →  Python IPC  →  SQLite + disk scan
```

1. Register project folders (**Add project** or CLI)
2. Select a project → read **Resume panel** (WYLO + Snapshot)
3. **Refresh context** (header) when files on disk may have changed
4. **Open project** → optional wake transition → session + editor
5. Close editor → **Exit note** dialog (or CLI `graf-id session close`)
6. **Export** (GrafiTalk handoff / JSON / Markdown / TXT) or **Import context…** - see [EXPORT_IMPORT.md](EXPORT_IMPORT.md)

Full journey: [WORKFLOW.md](WORKFLOW.md)

---

## Where important files are

| What | Where |
|------|-------|
| Python core | `grafid/` |
| Desktop UI | `desktop/src/` |
| Tauri / Rust bridge | `desktop/src-tauri/` |
| Embedded Python (release) | `desktop/src-tauri/runtime/` (gitignored — rebuild) |
| Rust build cache (huge) | `desktop/src-tauri/target/` (gitignored — `cargo clean`) |
| Packaging scripts | `packaging/` |
| User database (runtime) | `%LOCALAPPDATA%\Graf-Id\graf-id.db` |
| User config | `%LOCALAPPDATA%\Graf-Id\config.json` |
| GrafiTalk export inbox | `%LOCALAPPDATA%\Graf-Id\grafitalk-inbox\` or a folder you choose (optional) |
| Tests | `grafid/tests/`, `desktop/src/**/*.test.ts` |

**Do not confuse with GrafiTalk** — separate product; integration is JSON export only.

---

## How to run it (dev)

```powershell
cd <repo>
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

cd desktop
npm install
npm run tauri:dev
```

Use **`tauri:dev`**, not `npm run dev` alone.

---

## How to build installers

```powershell
cd <repo>\desktop
npm run build:runtime
npm run tauri:build
```

Or from repo root: `packaging\build_release.ps1`

`build:runtime` (also tauri's `beforeBuildCommand`) clears `target\release\runtime` and `target\release\bundle` before rebuilding the runtime, so both entry points start clean. The runtime excludes CPython's test suite, IDLE, Tk, ensurepip and other dev-only parts; see [packaging/README.md](../packaging/README.md).

If `build:runtime` fails about base Python: recreate `.venv` from system Python (not bundled runtime). See [CLEANUP.md](CLEANUP.md).

---

## How to test

```powershell
.venv\Scripts\pytest grafid\tests -q
cd desktop && npm test && npm run build
```

Manual smoke: [QA_CHECKLIST.md](QA_CHECKLIST.md)  

---

## Where NOT to touch things

| Avoid | Reason |
|-------|--------|
| GrafiTalk repository (external) | Separate product |
| Coupling GrafiTalk to SQLite | Use export JSON only |
| Adding background file watchers | Against explicit-refresh philosophy |
| LLM inside `summary_composition.py` | Deterministic core decision |
| Committing `target/` or `runtime/` | Large generated artifacts — gitignored |
| Deleting `runtime/` before release build | Rebuild with `npm run build:runtime` |

Safe to delete: **`desktop/src-tauri/target/`** via `cargo clean` (~GB recovered). See [CLEANUP.md](CLEANUP.md).

---

## Key code paths (if you need to debug)

| Feature | Start here |
|---------|------------|
| Refresh context | `grafid/ipc/dashboard_handlers.py` → `handle_refresh_resume`, then `grafid/services/project_overview.py` |
| Project Snapshot | `grafid/resume/project_context.py` → `build_project_context` |
| Export / handoff / import | `grafid/handoff/`, `grafid/services/project_export.py` (see docs/EXPORT_IMPORT.md) |
| Backup / restore | `grafid/services/portability.py`, `grafid/ipc/backup_handlers.py` |
| Handoff chain | `grafid/resume/workflow_artifacts.py` |
| Summary / WYLO | `grafid/resume/summary_composition.py` |
| Grafi briefs | `desktop/src/utils/grafiAdvisorRules.ts`, `GrafiAdvisorHost.tsx` |
| Helping tooltips | `GrafiHelpProvider.tsx`, `grafiHelpRegistry.ts` |
| Wake transition | `AppShell.tsx`, `ProjectWakeTransition.tsx` |
| Context import | `grafid/handoff/importer.py`, `grafid/ipc/import_handlers.py` |
| Project header UI | `desktop/src/components/ProjectDetailHeader.tsx` |
| Resume panel UI | `desktop/src/components/ResumePanel.tsx` |
| IPC spawn | `desktop/src-tauri/src/python.rs` |
| Bootstrap cache | `grafid/ipc/handlers.py` → `handle_bootstrap` |
| IPC command table / error codes | `grafid/ipc/desktop_entry.py` (`COMMANDS`), `grafid/ipc/errors.py` |
| Composition root | `grafid/services/runtime.py` → `prepare_runtime` |
| Editor presets | `grafid/config/editors.py` |

---

## Project status

**v1.0 complete** — UI polish, snapshot layer, hardening, and cleaning done. Suitable for release audit and maintenance. New features should be scoped as explicit milestones.

---

## Documentation map

| Doc | Use when |
|-----|----------|
| [README.md](../README.md) | Overview + quick start |
| [EXPORT_IMPORT.md](EXPORT_IMPORT.md) | Export formats, import, backup/restore |
| [GUIDE.md](GUIDE.md) | Long-form user guide |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design |
| [DECISIONS.md](DECISIONS.md) | Why we chose X |
| [GRAFITALK_INTEGRATION.md](GRAFITALK_INTEGRATION.md) | Export format |
| [QA_CHECKLIST.md](QA_CHECKLIST.md) | Before release |

---

## One-line summary

**Graf-Id is a local Windows desktop utility that scans your project folders on demand and shows a deterministic “where you left off” resume plus a structured Project Snapshot — then gets out of your way so you can code.**
