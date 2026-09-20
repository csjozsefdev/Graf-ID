# Graf-Id user workflow

Step-by-step journey through the product — and why each step exists.

---

## Overview

```
Open Graf-Id
    ↓
Select project (sidebar)
    ↓
Read Resume panel / Refresh context (header)
    ↓
Generate summary (deterministic compose)
    ↓
Open project (header) → IDE
    ↓
Work
    ↓
Exit note (CLI/IPC in v1.0 desktop)
    ↓
Next resume (next time you return)
```

---

## 1. Open Graf-Id

**What you do:** Launch the desktop app (or run `graf-id startup` in a terminal to initialise and check the local database).

**Why it exists:** Graf-Id is an **on-demand wake-up tool**, not a background service. You open it when you need continuity context, then return to your editor.

**What happens technically:** Tauri starts → `ipc_bootstrap` loads projects, settings, and cached resume panels into memory.

---

## 2. Select project

**What you do:** Click a project in the sidebar (search/filter by category or status if needed).

**Why it exists:** Continuity is **per project**. Each registered folder has its own sessions, scans, and summary.

**What you see:** Project name, compact preview line, session/git chips, full Resume panel in the main area (**Where you left off** first; Session and code markers secondary).

---

## 3. Scan sources (Refresh context)

**What you do:** Click **Refresh context** in the **project header** when files on disk may have changed.

**Why it exists:** Graf-Id does **not** watch your filesystem continuously. Explicit refresh keeps behavior predictable and bounded — you control when I/O runs.

**What is scanned:**

- Allowlisted workflow files (HANDOFF.md, README.md, NOTES.md, …)
- Code markers (TODO/FIXME) with quality filters
- Git branch, dirty/clean, modified files (if `git` available)

**What is not scanned:** Your entire drive, `node_modules`, or arbitrary paths outside project rules.

---

## 4. Generate summary

**What you do:** Automatic after refresh (or on bootstrap from last known state).

**Why it exists:** Raw scan data is too noisy. The **SummaryEngine** composes a short human-readable resume with tagged sources.

**Priority:** Your exit notes and handoff docs beat generic “recent edits in file X” git text.

**What you see:**

- Where you left off (primary — up to ~320 characters from handoff/session sources)
- Suggested next step
- Session status (secondary styling)
- MVP sections (expandable detail)
- Source tags

---

## 5. Open IDE

**What you do:** Click **Open project** in the project header (under the path).

**Why it exists:** Graf-Id is the **bridge**, not the workspace. The goal is to land you in Cursor/VS Code with context already read.

**What happens:**

- `last_opened_at` updated
- Work session started or resumed
- Preferred IDE launched (configurable per project or globally)
- If the editor cannot launch, File Explorer may open at the registered path (fallback — not a separate button in v1.0)

---

## 6. Work

**What you do:** Normal development in your editor. Graf-Id can stay open or go to the system tray.

**Why sessions matter:** An **active session** signals “work in progress” in the resume. Without an exit note, the summary may be weaker — that is intentional encouragement to close the loop.

---

## 7. Exit note

**What you do (v1.0 desktop):** There is **no End session button** in the UI. Use the CLI or IPC:

```bash
graf-id session close <project> --exit-note "..." --next-step "..." --blocker "..."
```

Optional fields: what you did, unfinished items, blocker, next step.

**Why it exists:** This is the **strongest continuity signal**. It captures intent in your words, not inferred from git noise.

**Skip:** You can end without notes, but future resumes may rely on weaker sources (docs, markers, git).

A desktop End session modal may return in a future release; the backend already supports `ipc close-session`.

---

## 8. Next resume

**What you do:** Days or weeks later — open Graf-Id, select the same project, read Resume.

**Why it works:** SQLite persisted your session, scans, and notes. Refresh context if the repo changed since last time.

**Wake panel:** If you have been away a long time, you may see a short “before you continue” reminder — dismiss and use the full Resume panel.

---

## CLI equivalent

| Desktop | CLI |
|---------|-----|
| Add project | `graf-id add <name> <path>` |
| Refresh context | `graf-id scan <name>` + `graf-id resume <name>` |
| Start session | `graf-id session start <name>` |
| End session + exit note | `graf-id session close <name> --done "..." --next "..."` |
| Export JSON/MD/TXT | Project header buttons (desktop) |
| Remove project | Sidebar ⋯ → confirm |
| Export for GrafiTalk | `graf-id export-grafitalk` |

---

## 9. Remove project

**What you do:** Sidebar row → **⋯** → **Remove from Graf-Id** → confirm in the dialog.

**Why it exists:** Unregister folders you no longer track without deleting anything on disk.

---

## 10. History and export

**History:** Open the **History** nav item to see past scan snapshots as cards (read-only).

**Export:** Use **GrafiTalk handoff**, **JSON**, **Markdown**, or **TXT** in the project header to save the project context as a file. **Import context…** brings a handoff file back into the project notes after a preview. See [EXPORT_IMPORT.md](EXPORT_IMPORT.md).

---

## Related docs

- [EXPORT_IMPORT.md](EXPORT_IMPORT.md) — export, import, backup
- [GUIDE.md](GUIDE.md) — fuller narrative
- [ARCHITECTURE.md](ARCHITECTURE.md) — technical pipeline
- [QA_CHECKLIST.md](QA_CHECKLIST.md) — manual verification steps
