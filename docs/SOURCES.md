# What Graf-Id reads from your projects

Plain-language guide to the **raw materials** Graf-Id uses when you click **Refresh context** or open the **Resume** panel.

Graf-Id does not invent context. It **collects traces you already left** on disk and in your local database, then assembles them in a **fixed priority order**. Same inputs → same summary.

---

## The short version

| Source | Where it lives | When it is read |
|--------|----------------|-----------------|
| **Exit notes & session fields** | Graf-Id database (`%LOCALAPPDATA%\Graf-Id`) | Every resume |
| **Handoff & workflow files** | Your project folder (allowlisted names only) | On **Refresh context** |
| **Task markers** | Source files (`TODO`, `FIXME`, …) | On **Refresh context** (bounded scan) |
| **Git snapshot** | Your repo (read-only) | On **Refresh context**, if `git` is on PATH |

Nothing is sent to the cloud. Nothing runs in the background between your clicks.

---

## 1. Session notes (strongest signal)

When you end a work session with an exit note (CLI/IPC in v1.0 desktop), Graf-Id stores:

- **Exit note** — what you finished or where you stopped
- **Blocker** — what was in the way
- **Next step** — what you planned to do next

These live in your **local SQLite database**, not in the project folder. They appear at the **top** of the resume because you wrote them explicitly for continuity.

Example (CLI):

```powershell
graf-id session close my-app --exit-note "Finished auth refactor" --next-step "Add integration tests"
```

---

## 2. Workflow files (human-written docs)

On **Refresh context**, Graf-Id looks for **specific filenames** in the project root (and parent folder for handoff files). It reads only the **first ~12 KB** and a **short preview** (up to **~320 characters** per line, truncated on word boundaries) — not your entire repo.

### High-priority files

| File | Typical use |
|------|-------------|
| `HANDOFF.md`, `handoff.md` | “Where I left off” for the next person (or future you) |
| `PROJECT_HANDOFF.md` | Same intent, alternate name |
| `HANDOVER.md`, `handover.md` | Handover notes |
| `NEXT.md` | Explicit next steps |
| `SESSION.md` | Session log or scratch notes |
| `EXIT_NOTE.md` | Exit note kept in the repo |

### Medium-priority files

| File | Typical use |
|------|-------------|
| `TODO.md` | Task list |
| `NOTES.md` | General project notes |
| `README.md` | Project overview (preview only) |
| `CHANGELOG.md` | Recent changes (preview only) |

Graf-Id extracts lines like **Focus area:** and **Next step:** when they follow simple patterns. You do not need a special format — **plain prose paragraphs** work best (e.g. a short “where we left off” note under a heading).

**Not scanned:** random `.md` files, `docs/` trees, node_modules, `.git`, build output, or anything outside the allowlist.

---

## 3. Task markers in code

The scanner walks the project with **depth and file-count limits**. It collects lines containing:

`FIXME` · `BUG` · `HACK` · `TODO` · `NEXT`

These appear in the resume as **unfinished task markers** — useful when you did not write a handoff file but left breadcrumbs in code.

The scan is **read-only**. Graf-Id never edits your files.

---

## 4. Git snapshot (optional)

If `git` is on your PATH and the folder is a repository, Refresh context captures a **read-only** snapshot:

- Current branch (including detached HEAD)
- Modified and staged files
- Recent commits (subjects only)

Git status helps when you have **no handoff doc** — but human notes and exit notes still rank higher in the summary.

---

## 5. How sources are ranked in the resume

When several sources exist, Graf-Id uses this order (simplified):

1. **Exit note** from your last session  
2. **Handoff** workflow files (`HANDOFF.md`, …)  
3. **Next step** from session or workflow files  
4. Other workflow sections (session notes, TODO file, README, changelog, …)  
5. **Blocker** from session  
6. **Git** modified/staged lists  
7. **Task markers** from the scan  
8. **Metadata** (last scan time, branch, session timestamps)

You always see **which kind of source** fed each section — the engine is deterministic, not a black box.

---

## 6. What Graf-Id does *not* read

- Entire directory trees or unlimited file globs  
- Cloud drives, email, Slack, or browser history  
- AI-generated plans (no LLM in the core path)  
- Files renamed to dodge the allowlist (only listed names count)  
- Live git hooks or write operations  

If you want richer context, **add or update** a handoff file or exit note — that is the intended workflow.

---

## 7. Practical tips

**Leave good raw materials:**

- One `HANDOFF.md` or `NEXT.md` with a few sentences in plain language — what you were doing and what’s next  
- Or use `graf-id session close` with `--exit-note` and `--next-step`  
- Keep `TODO`/`FIXME` comments specific (“wire auth callback”) not vague (“fix this”)

**When to click Refresh context:**

- After editing handoff/README/changelog  
- After a big git change you want reflected  
- When the resume feels stale  

**When you do not need Refresh:**

- Browsing the last stored summary  
- Exporting JSON/Markdown from existing data  

---

## Related docs

| Doc | Topic |
|-----|--------|
| [WORKFLOW.md](WORKFLOW.md) | Step-by-step user journey |
| [GUIDE.md](GUIDE.md) | Full program guide |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Technical data flow |
| [PACKAGED_USAGE.md](PACKAGED_USAGE.md) | Installed app, no Python required |
