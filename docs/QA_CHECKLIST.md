# Graf-Id manual QA checklist

Use before release or after significant changes. All steps are **manual** — no automated substitute for desktop smoke testing.

**Environment:** Windows, `npm run tauri:dev` from `desktop/`, or packaged `.exe`.

---

## Setup

- [ ] Repo `.venv` exists with `pip install -e ".[dev]"`
- [ ] `cd desktop && npm install`
- [ ] App launches without console errors

---

## Create project

- [ ] **Add project** (sidebar) registers a valid folder
- [ ] Project appears in sidebar with name and preview
- [ ] CLI `graf-id add <name> <path>` also works (optional cross-check)
- [ ] Invalid path shows clear error (not silent failure)

---

## Select project

- [ ] Clicking sidebar row selects project (highlight active)
- [ ] Main area shows project header + Resume panel
- [ ] Switching projects updates content without app restart
- [ ] Search / status filter / category tabs narrow list correctly
- [ ] Fast switching does not flash wrong project's resume

---

## Project header

- [ ] Project name and compact path shown
- [ ] **Open project** under path (primary action)
- [ ] **Refresh context**, **JSON / Markdown / TXT** export in top-right group
- [ ] **More details** collapsed by default; expands with path, session, git, markers
- [ ] Actions disable while refresh, export, or open is in progress

---

## Scan / refresh context

- [ ] **Refresh context** (project header) runs and shows refreshing state
- [ ] `last_refreshed_at` updates in Resume panel when scan succeeds
- [ ] Summary reflects project files (HANDOFF/README) when present
- [ ] With only dirty git and no docs, git fallback still appears (expected)
- [ ] With docs + dirty git, human docs win over git file list
- [ ] Refresh disabled with clear message when registered folder is missing

---

## Summary generation

- [ ] Resume panel shows structured MVP sections or primary context block
- [ ] Never-scanned project shows helpful empty state (not a crash)
- [ ] Sources listed match expected files (exit note, HANDOFF, git, etc.)
- [ ] Sidebar preview is short and readable (word-boundary truncation, not mid-word cut)
- [ ] **Activity & sources** and **Scan & git detail** folds work

---

## Open project

- [ ] **Open project** updates last opened and starts/resumes session
- [ ] Cursor or VS Code opens when configured (or clear fallback message)
- [ ] When editor does not launch, Explorer may open at project path (fallback only)
- [ ] Successful editor launch may hide app to system tray
- [ ] Open disabled when registered folder is missing

---

## Remove project

- [ ] Sidebar **⋯** menu shows **Remove from Graf-Id**
- [ ] Confirmation dialog required — no one-click delete
- [ ] Cancel leaves project unchanged
- [ ] Confirm removes from sidebar; files on disk remain
- [ ] If removed project was selected, another project is auto-selected

---

## Settings

- [ ] Settings page loads from bootstrap cache
- [ ] Python backend preset saves (including Custom Path + Browse)
- [ ] Editor preset saves (Cursor, VS Code, PyCharm, Custom Path, …)
- [ ] Usage journal / debug timing / compact mode toggles save
- [ ] `config.json` under `%LOCALAPPDATA%\Graf-Id` updates when settings change
- [ ] Open data/logs folder actions work

---

## History

- [ ] **History** nav page loads scan cards for selected project
- [ ] Each card: project name, date, summary preview, changed files, optional duration
- [ ] History is read-only (no delete in UI)
- [ ] Empty state mentions Refresh context
- [ ] Retry works if history fetch failed
- [ ] After Refresh context on dashboard, History shows updated scans

---

## Sessions, History, Export

Run after backend or Rust IPC changes. **Restart `tauri:dev`** when needed.

### Session and summary

- [ ] Open app → select project
- [ ] **Open project** starts or resumes a work session
- [ ] **Refresh context** — resume summary updates
- [ ] Resume panel shows readable work summary (not raw JSON)
- [ ] **Where you left off** shows up to ~320 characters without mid-word truncation

### History cards

- [ ] Open **History** for selected project
- [ ] Each entry shows **project name**, **readable date**, **summary preview**
- [ ] **Changed files** count when git snapshot exists
- [ ] **Duration** when session correlates (best effort); omitted otherwise
- [ ] Snapshot `#id` is secondary (muted)
- [ ] Long summary preview clamped without layout break

### Export

- [ ] Project header → **GrafiTalk handoff** / **JSON** / **Markdown** / **TXT** → save dialog → file written (content checks: see *Export, import, backup* below)
- [ ] Suggested filename sensible (project slug + label + date + extension)
- [ ] Cancel save dialog — no error shown
- [ ] Invalid/unwritable path shows clear error in status line
- [ ] Export works when folder missing (from stored DB data)

### Edge cases

- [ ] Missing registered folder — warning banner; Open/Refresh disabled; no crash
- [ ] Corrupt/partial data — placeholders, no crash
- [ ] Long summary — full text in export; UI preview clamped only
- [ ] Confirm **no AI** and **no network** for summary, history, or export

---

## Exit note (CLI / IPC only in v1.0)

- [ ] No **End session** button on dashboard (by design)
- [ ] Exit notes via CLI (`graf-id session close`) appear in summary after refresh
- [ ] Backend `ipc close-session` still works (optional CLI check)

---

## Restart app / persistence

- [ ] Quit and relaunch — projects still listed
- [ ] Session state persisted in SQLite
- [ ] Exit note from previous session still in summary after restart
- [ ] User data remains in `%LOCALAPPDATA%\Graf-Id` (not install dir)

---

## Packaged build (release QA)

- [ ] `npm run build:runtime` succeeds
- [ ] `npm run tauri:build` produces `.exe` + installers
- [ ] Packaged app runs **without** repo `.venv`
- [ ] Refresh context works in packaged build
- [ ] `packaging\verify_release_bundle.ps1` passes (optional)

---

## Export, import, backup (see docs/EXPORT_IMPORT.md)

- [ ] Project header shows **GrafiTalk handoff / JSON / Markdown / TXT / Import context…**
- [ ] *GrafiTalk handoff* file has `source`, `schema_version` `"0.1"`, `project_name`; no absolute paths, no `.venv` files, no scanner marker text
- [ ] *JSON* export additionally contains a `graf_id` block
- [ ] Settings → Data → **Export all projects…** writes `manifest.json` + `projects/*.json` into the chosen folder; manifest has no absolute path
- [ ] **Import context…** shows a preview and writes nothing until confirmed; Add keeps existing notes, Replace warns first
- [ ] **Create backup…** produces a `.zip`; **Restore from backup…** asks for confirmation, keeps a safety copy in `backups/`, then reloads
- [ ] Restoring a corrupt or non-Graf-Id zip fails with a clear message and leaves current data intact
- [ ] `graf-id export-grafitalk` still writes the inbox from the CLI

---

## Audit campaign fixes (release/grafid-v1-audit, M1–M9)

Manual verification for the 2026 audit-driven fix campaign (commits `a9ef3ddc`
through `c3492118`). Automated tests cover the code paths directly, but these
items are either genuinely hard to automate (races, real editor processes,
real Rust builds) or were never exercised in a live Tauri window during the
campaign itself — run this section before calling the release done.

### Clean Rust build cache (new feature, M7) — never manually verified live

- [ ] Register a real Rust/Cargo project (or this repo itself, `desktop/src-tauri`)
      that has a `target/` directory with real build output
- [ ] Open that project — a **Build cache detected** card appears below the
      Resume panel, showing a plausible size (compare to `du`/Explorer
      properties on the real `target/` folder)
- [ ] A project with **no** `Cargo.toml` shows no card at all (no false positive)
- [ ] Click **Clean build cache…** → confirmation dialog names the correct
      crate directory and an estimated size
- [ ] **Cancel** — dialog closes, `target/` untouched, no IPC call made
- [ ] **Clean now** — `target/` is actually removed; a "Freed X" notice
      appears; `Cargo.toml`/`src/` are untouched
- [ ] Immediately after cleaning, `cargo check`/`cargo build` in that project
      still works (nothing beyond `target/` was touched)
- [ ] If you have `CARGO_TARGET_DIR` set in your shell environment, confirm
      Clean now still removes *this project's* `target/` — not the
      `CARGO_TARGET_DIR` location (this was a Critical bug found and fixed
      during the campaign's own final re-audit)
- [ ] Switch to a different project **while** a clean is still running (use a
      large `target/` to give yourself time) — the eventual "Freed X" notice
      must land on the project that was actually cleaned, not whatever
      project is on screen when it finishes
- [ ] If `cargo` is not on PATH, the card still detects the cache and shows a
      clear "cargo was not found" error on clean, not a crash

### Cross-project races (C2, H9/H14, H10, M8, M10)

- [ ] Click **Refresh context** on project A, then immediately switch to
      project B before it finishes — B's Resume panel/history/scan-health
      must stay B's, never flash stale A data
- [ ] Start **Export** on project A, immediately switch to B — the eventual
      completion notice names project A, not B
- [ ] With an editor open for project A, click **Open project** on B while A's
      open is still resolving — both projects end up in a consistent state
      (no crash, no stuck spinner on either)
- [ ] While A is mid-refresh/export/open (its row shows a busy state), you
      **can** still click into and act on a different project — busy state is
      per-project, not a global lock
- [ ] Add a project while another project's async action (refresh/export) is
      in flight — both complete correctly, sidebar shows the new project
- [ ] Remove a project while a *different* project's refresh is in flight —
      no crash, the in-flight refresh still completes for the surviving project

### Symlink / junction safety (C1)

- [ ] Create an NTFS junction inside a registered project's root pointing
      **outside** the project (`mklink /J`) — Refresh context / resume must
      **not** read through it (no unexpected content from outside the project
      appears in the summary or export)
- [ ] A registered project containing an ordinary (non-symlinked) `HANDOFF.md`,
      `README.md`, etc. still works exactly as before

### Editor lifecycle across two projects (H11)

- [ ] Open project A in your editor, then — without closing A's editor
      window — open project B in the same editor
- [ ] Close **A**'s editor window/tab only — Graf-Id's exit-note prompt fires
      for A specifically (this used to silently drop tracking of A)
- [ ] Then close B's editor window — exit-note prompt fires for B too

### `--git-only` refresh actually updates git state (H1)

- [ ] Refresh a project once normally (full scan) so a snapshot exists
- [ ] Make a git change (new commit, or edit a tracked file) in that project
- [ ] Trigger a git-only refresh (`graf-id refresh <project> --git-only` or
      the equivalent fast-refresh path) — the sidebar/dashboard git chip
      (branch, dirty/clean) reflects the **new** state, not the old snapshot

### Import / export hardening (M4, L1, L2)

- [ ] Export a project, edit the zip's `grafid-export.json` to remove
      `schema_version` entirely, then import — import is rejected with a
      clear error, not silently accepted
- [ ] Import a normal, unmodified export bundle — still works end to end
- [ ] Try saving a very long exit note (several thousand characters) on
      session close — either accepted up to the limit or rejected with a
      clear message, never silently truncated

### Duplicate project detection (H6, M11)

- [ ] Try adding the same folder twice — clear "already registered" error,
      not a raw exception
- [ ] If you have a mapped network drive, try registering the same folder via
      both its UNC path and the mapped drive letter — second one is rejected
      as a duplicate

### Session/window lifecycle (H7, H8, L7)

- [ ] Close the app via the titlebar **×** shortly after a refresh/open — no
      stuck state, app actually closes or hides to tray as expected
- [ ] Click the titlebar close button rapidly twice in a row — no double
      dialog, no crash

---

## Regression spots

- [ ] Sidebar selection does not break History or Settings nav
- [ ] `cargo clean` + rebuild — app still runs (see [CLEANUP.md](CLEANUP.md))
- [ ] No GrafiTalk repo files modified from Graf-Id work

---

## v1.0 Release smoke (manual)

- [ ] NSIS installer on clean machine / VM
- [ ] MSI installer smoke
- [ ] App starts without separate Python install
- [ ] Add Project (UI dialog)
- [ ] Refresh context
- [ ] Open project (editor + Explorer fallback)
- [ ] Export JSON / Markdown / TXT
- [ ] History page
- [ ] Settings (save, open data/logs folders)
- [ ] Remove project without data loss (files remain on disk)
- [ ] Missing project folder — warning, Open/Refresh disabled
- [ ] Projects persist after restart

---

## Sign-off

| Field | Value |
|-------|-------|
| Tester | |
| Date | |
| Build | dev / packaged version |
| Result | PASS / FAIL |
| Notes | |

