# Graf-Id

**A project continuity tool for developers.**

Graf-Id helps you wake up a local codebase after time away. It answers three practical questions:

- **Where you left off** — last focus, handoff notes, or session context
- **What blocks you** — open blockers from exit notes or workflow files
- **What to do next** — suggested next step from your own sources

It is **local-first**, **deterministic**, and **explicit**: summaries are assembled from **raw materials on your machine** — handoff files, exit notes, git status, and task markers — when you ask. No cloud AI. No background watcher.

> **New here?** Read [docs/SOURCES.md](docs/SOURCES.md) for a plain list of what Graf-Id reads from your projects, or [docs/GUIDE.md](docs/GUIDE.md) for the full walkthrough.

---

## Raw materials (what Graf-Id reads)

Graf-Id builds your resume from **traces you already left**, not from generated guesses.

| Material | Examples |
|----------|----------|
| **Session exit notes** | “Shipped auth UI”, “Next: write tests” (stored locally when you close a session) |
| **Workflow files** | `HANDOFF.md`, `NEXT.md`, `README.md`, `CHANGELOG.md`, … (allowlisted names only) |
| **Code markers** | `TODO`, `FIXME`, `BUG`, `HACK`, `NEXT` in source files (bounded scan) |
| **Git snapshot** | Branch, dirty files, recent commits (read-only, if `git` is on PATH) |

**Priority:** exit notes and handoff docs beat git file lists. Same inputs → same summary every time.

Full list, limits, and tips: **[docs/SOURCES.md](docs/SOURCES.md)**.

---

## What problem it solves

Developers switch between projects. After days or weeks away, context is scattered across git status, half-written docs, TODO comments, and memory. Graf-Id collects those signals into one **resume view** so you can open your editor with confidence instead of re-reading folders blindly.

### Core concepts

| Concept | Meaning |
|---------|---------|
| **Where you left off** | Primary anchor line in the resume summary (exit note, handoff, docs, markers — in fixed priority) |
| **Project wake-up** | Opening Graf-Id, selecting a project, reading the Resume panel before continuing work |
| **Session continuity** | Work sessions with optional exit notes that persist into the next resume |
| **Context restoration** | Refresh context + summary generation from disk, git, and stored session fields |

---

## Who it is for

- Developers with **multiple local projects**
- People who already leave traces in **HANDOFF.md**, README, git, or exit notes
- Anyone who wants a **small on-demand utility** — not another always-open dashboard

---

## What Graf-Id is not

Graf-Id is **not**:

- a **project manager** (no kanban, sprints, or team workflows)
- a **task manager** (no task inbox or due dates as the product center)
- an **AI coding assistant** (no chat, no autonomous code changes)
- a **documentation platform** (it reads your docs; it does not replace them)

Graf-Id **is** a **project continuity tool**: bridge the gap between closing your laptop and opening the repo again.

---

## Philosophy

- **Local-first** — data stays on your machine (`%LOCALAPPDATA%\Graf-Id` by default)
- **Deterministic-first** — same inputs produce the same summary; sources are tagged
- **Explicit refresh** — scans run when you click Refresh context, not silently in the background
- **Human sources win** — exit notes and handoff docs outrank generic git file lists
- **Optional AI elsewhere** — the core engine does not require LLMs; ecosystem tools may consume exports

---

## What you get (desktop, v1.0.0)

### Layout

| Area | Purpose |
|------|---------|
| **Sidebar** | Project list (search, category, status filter, drag reorder), **Add project**, **Remove from Graf-Id** (⋯ menu, with confirmation), git chip (**Git: clean** / **Git: uncommitted**) |
| **Dashboard** | Selected project: header actions + **Resume panel** (Where you left off, Project Snapshot, folded detail) |
| **History** | Dedicated page — scan snapshot cards (read-only) |
| **Settings** | Python backend preset, default editor/coding agent, coding agent management, Grafi advisor + Helping Mode, compact mode, usage journal, debug timing, open data/logs folders, **Backup and export** (create backup, restore from backup, export all projects for GrafiTalk) |

### Primary actions (dashboard)

| Action | Location | What it does |
|--------|----------|--------------|
| **Open project** | Project header (under path) | Editor opener: wake transition (optional) → session + configured editor, Explorer fallback if unavailable. Coding agent opener: launches the agent in a visible terminal instead — no session, no wake transition, no Exit Note (see [docs/CODING_AGENTS.md](docs/CODING_AGENTS.md)) |
| **Refresh context** | Project header (top right) | Bounded scan + git snapshot + summary rebuild (manual, on demand) |
| **Export** | Project header — **GrafiTalk handoff** / JSON / Markdown / TXT | Save dialog → one file. *GrafiTalk handoff* is lean, GrafiTalk-compatible JSON; *JSON* is the full project context; Markdown and TXT use GrafiTalk's labelled sections. See [docs/EXPORT_IMPORT.md](docs/EXPORT_IMPORT.md) |
| **Import context…** | Project header | Pick a handoff `.json`, review a validated preview, then explicitly add it to (or replace) the project notes — nothing is written until you confirm |
| **More details** | Project header | Collapsed path, session, git, markers |

The **Resume panel** shows **Where you left off**, then a compact **Project Snapshot**, then technical material folded into **Evidence & details** and **Activity & sources**. Export, import and refresh live in the header, not the panel body.

### Project Snapshot

A quick re-orientation card directly under **Where you left off**. Every line comes from reliable local sources; sections with nothing reliable to say are simply not shown.

| Section | Source |
|---------|--------|
| **Current focus** | Exit note (first sentence) or a handoff document's focus area |
| **Open issues / blockers** | Session blocker, handoff blockers and unfinished items |
| **Recent fixes** | Recent git commits shaped like `fix: …` / `Fix …` |
| **Recent improvements** | Recent git commits shaped like `feat: …` / `Add …` |
| **Suggested next step** | Session next step, handoff next line, or resolving the blocker |

Built from the same backend `ProjectContext` that feeds every export — no LLM step. Scanner code markers are deliberately **not** used as issues or next steps (they read as noise on real projects); they stay visible under **Evidence & details**. Virtualenv folders (`.venv`, `venv`, `.venv-*`, `venv-*`, `site-packages`) are never scanned.

### Grafi advisor

Optional **local advisor** beside the sidebar (not a chat agent):

- **Status briefs** — ranked messages for missing path, blocker, stale refresh, dirty git, thin continuity
- **Helping Mode** — hover/focus **tooltips** anchored to dashboard controls (`data-grafi-help`); critical severity overrides help text
- **Settings** — enable/disable advisor, motion, **Critical alerts only** (suppresses non-critical tooltips and briefs)

### Wake flow

Two layers after time away:

1. **Wake panel** — short “Before you continue” card when absence exceeds threshold (dismissible)
2. **Project wake transition** — on **Open project**, optional full-screen MP4 intro until the editor process is ready; **Skip** closes overlay; reduced-motion path shows terminal lines without video

If launch fails or you skip early, pending actions (Explorer open, notices) still run — overlay dismiss no longer leaves the UI stuck busy.

### Sessions & exit notes

- **Open project** starts or resumes a work session and launches the editor from Settings
- When editor close is detected, Graf-Id restores from tray and opens an **Exit note** dialog (exit note, blocker, next step) — CLI/IPC still available
- **End session** has no separate header button; use the exit-note dialog or `graf-id session close`

### Coding agents

An **Open project** opener can be an editor (above) or a **Coding Agent** —
an interactive CLI tool (Claude Code and Codex CLI are optional presets you
can remove or point at an explicit executable path; add any other CLI tool as
a custom agent) launched in the project root in a visible
terminal. Coding agents are a deliberately separate, minimal path: no work
session, no process tracking, no Exit Note — Graf-Id starts the terminal and
does not track what happens in it afterward. See
[docs/CODING_AGENTS.md](docs/CODING_AGENTS.md) for the full Editors-vs-Coding-Agents
boundary, the custom agent executable/arguments model, and the security model
for the launch.

### Other behavior

- **Project removal** — sidebar ⋯ → **Remove from Graf-Id** → confirmation (registry only; files on disk unchanged)
- **Missing folder** — warning in header; Open/Refresh disabled; export still works from stored data
- **Packaged Windows installers** — embedded Python; no Python install for end users

CLI (`graf-id`) remains available for power users and automation.

---

## Installation (end users)

Install from a release build:

- `Graf-Id_1.0.0_x64-setup.exe` (NSIS), or
- `Graf-Id_1.0.0_x64_en-US.msi`, or
- run `graf-id-desktop.exe` directly

No separate Python, Node, or Rust install required. User data lives in `%LOCALAPPDATA%\Graf-Id\`.

---

## Development setup

**Requirements:** Windows, Python 3.12+, Node.js, npm, Rust ([rustup](https://rustup.rs/))

```powershell
cd Graf-ID
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

cd desktop
npm install
npm run tauri:dev
```

Use **`npm run tauri:dev`** (not `npm run dev` alone).

After testing a **packaged MSI**, run `packaging\clear_dev_env.ps1` and restart the terminal if bootstrap fails (`encodings` error). Full checklist: [docs/CLEANUP.md](docs/CLEANUP.md).

Add a project:

```powershell
graf-id add my-app C:\path\to\project
```

Or use **Add project** in the desktop UI.

---

## Build process

### Embedded Python runtime

Release builds bundle Python + `grafid` under `desktop/src-tauri/runtime/`:

```powershell
cd Graf-ID\desktop
npm run build:runtime
```

Requires a repo `.venv` created from a **system Python** (not the bundled runtime). See [packaging/README.md](packaging/README.md).

### Full installer build

```powershell
cd Graf-ID\desktop
npm run tauri:build
```

Or from repo root: `packaging\build_release.ps1`

Outputs: `.exe`, MSI, and NSIS under `desktop/src-tauri/target/release/bundle/`.

**Dev vs packaged:** `tauri dev` uses repo `.venv`; release uses `src-tauri/runtime/`. Rebuild runtime after Python backend changes.

---

## How summaries work

On **Refresh context**, Graf-Id:

1. Runs a **bounded filesystem scan** (allowlisted workflow files + markers)
2. Captures **git snapshot** if `git` is on PATH
3. Reads **session fields** (exit note, blocker, next step)
4. Composes a summary via **fixed priority** — human docs and exit notes beat git file fallback

See [docs/SOURCES.md](docs/SOURCES.md), [docs/WORKFLOW.md](docs/WORKFLOW.md), and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Architecture summary

```
React UI (desktop/src)
    ↕ Tauri invoke
Rust bridge (src-tauri) → Python IPC subprocess
    ↕
grafid services: scan · git · resume · sessions · export
    ↕
SQLite (%LOCALAPPDATA%\Graf-Id) + read-only project folders
```

**Refresh path:** `Refresh context` → bounded scan + git snapshot → `compose_workflow_summary` + backend **`ProjectContext`** → `resume_panel` (Where you left off + Project Snapshot) → React Resume panel + Grafi briefs.

**Export path:** `ProjectContext` → GrafiTalk handoff (flat contract v0.1) → JSON / Markdown / TXT, plus the additive `graf_id` block in the full JSON. **Import path:** handoff file → validator → preview → confirmed write into the project notes. **Backup path:** SQLite online backup → zip; restore verifies and migrates a temp copy, keeps a safety copy, then swaps atomically. Detail: [docs/EXPORT_IMPORT.md](docs/EXPORT_IMPORT.md).

Detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Known limitations (v1.0.0)

- **Windows-first** for packaged desktop today
- **Git** requires `git` on PATH for git snapshots
- **Refresh is manual** — no continuous file watcher
- **History** is scan-centric; session duration and notes are **best-effort** correlations, not guaranteed links
- **No header “End session” button** — exit note dialog after editor close, or CLI (`graf-id session close`)
- **No in-app project edit** — add/remove in UI; rename/path/category via CLI (`graf-id ipc update-project`)
- **No in-app per-project opener override** — Settings sets the global default editor/coding agent; a project-specific opener (editor or agent) can be set via CLI/DB only, same as before coding agents existed
- **Context import fills the project notes only** — a handoff file's file list, `graf_id` block and any configuration are never applied
- **Installers unsigned** — possible AV false positives
- **Rust `target/` cache** can grow to several GB during dev — see [docs/CLEANUP.md](docs/CLEANUP.md)
- **No cloud sync, accounts, or auto-update**
- **Uninstalling does not delete your data** — the MSI/NSIS uninstaller removes the app only; your projects registry, sessions, exit notes, and history stay in `%LOCALAPPDATA%\Graf-Id\` until you delete that folder yourself (handy for reinstalling without losing history; delete it manually for a full removal)

---

## Documentation index

| Document | Purpose |
|----------|---------|
| [docs/SOURCES.md](docs/SOURCES.md) | **What Graf-Id reads** — raw materials, priority, tips |
| [docs/HANDOVER.md](docs/HANDOVER.md) | **Start here** if returning after months |
| [docs/GUIDE.md](docs/GUIDE.md) | Full program guide (plain language) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and data flow |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | User journey step by step |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Why we built it this way |
| [docs/QA_CHECKLIST.md](docs/QA_CHECKLIST.md) | Manual test checklist |
| [docs/CLEANUP.md](docs/CLEANUP.md) | Dev env reset, git Clean/Dirty chip, disk cleanup, tray |
| [docs/GRAFITALK_INTEGRATION.md](docs/GRAFITALK_INTEGRATION.md) | Export to GrafiTalk (no DB coupling) |
| [docs/EXPORT_IMPORT.md](docs/EXPORT_IMPORT.md) | Export formats, GrafiTalk handoff contract, backup/restore, context import |
| [docs/CODING_AGENTS.md](docs/CODING_AGENTS.md) | Coding Agent launcher — Editors vs Coding Agents, custom agents, security model |
| [desktop/README.md](desktop/README.md) | Desktop dev details and IPC commands |
| [docs/PACKAGED_USAGE.md](docs/PACKAGED_USAGE.md) | Running the packaged app |
| [docs/RELEASE_VERIFICATION.md](docs/RELEASE_VERIFICATION.md) | What the automated release-bundle checks cover |
| [docs/RELEASE_VERIFICATION_1.0.0.md](docs/RELEASE_VERIFICATION_1.0.0.md) | Results and checksums of the 1.0.0 release build |
| [docs/UNINSTALL_REINSTALL_CHECKLIST_1.0.0.md](docs/UNINSTALL_REINSTALL_CHECKLIST_1.0.0.md) | Manual uninstall/reinstall and data-persistence checklist |

---

## Tests

```powershell
.venv\Scripts\pytest grafid\tests -q
cd desktop && npm test
```

---

## License

MIT — see [LICENSE](LICENSE).
