# Graf-Id design decisions

Major architectural and product choices — recorded so future work does not accidentally undo them.

---

## Local-first

**Decision:** All user data stays on the machine (`%LOCALAPPDATA%\Graf-Id` by default).

**Why:** Privacy, offline use, no account friction, predictable ownership. Graf-Id is a personal utility, not a hosted service.

**Implication:** No sync, no multi-device state, no cloud backup built-in (zip export exists for manual backup).

---

## English internal data

**Decision:** UI copy, CLI messages, summary labels, and documentation are **English-only** for MVP.

**Why:** Single locale reduces test surface and keeps deterministic summary templates stable.

**Implication:** i18n is a future concern, not a silent addition.

---

## Optional AI (not in core)

**Decision:** The summary engine is **fully deterministic** — no LLM in the compose path.

**Why:** Explainability. Users must see *which source* produced each line. AI summaries are hard to trust for “where did I leave off.”

**Implication:** AI may exist in **ecosystem tools** (e.g. GrafiTalk) that consume exports — not inside Graf-Id’s core loop.

---

## AI only at startup (ecosystem)

**Decision:** If AI is used, it belongs in **downstream consumers** reading exported context at conversation start — not as a continuous monitor inside Graf-Id.

**Why:** Avoids creep toward “always-on agent” behavior that conflicts with explicit refresh philosophy.

---

## Deterministic core

**Decision:** `compose_workflow_summary()` uses a **fixed priority order** for signals.

**Why:** Same project state → same summary. Debuggable. Testable. No model drift.

**Implication:** Source priority changes are deliberate product decisions (see regression fix: docs beat git fallback).

---

## Exit Note concept

**Decision:** Sessions can end with structured human input: exit note, blocker, next step.

**Why:** The best continuity signal is what **you** write when pausing — not inferred git filenames.

**Implication:** UI encourages end session; weak summaries often mean missing exit note (by design nudge).

---

## JSON export for GrafiTalk

**Decision:** GrafiTalk integration is **file-based export** (`graf-id export-grafitalk`), not shared database or live API.

**Why:** Loose coupling. Graf-Id and GrafiTalk are separate repos/products. Read-only JSON inbox is easy to version and audit.

**See:** [GRAFITALK_INTEGRATION.md](GRAFITALK_INTEGRATION.md)

---

## No cloud dependency

**Decision:** No auth, no remote API, no telemetry pipeline required for core function.

**Why:** Aligns with local-first and “small utility” scope.

**Optional:** Usage journal is opt-in local logging only.

---

## No continuous AI monitoring

**Decision:** No background agent watching repos, no automatic “insights” push.

**Why:** Scope control, CPU trust, and user intent — refresh is explicit.

---

## Project continuity first

**Decision:** Product center is **resume / wake-up**, not task tracking or doc editing.

**Why:** Differentiated from PM tools and AI IDEs. Graf-Id answers one question well.

**UI reflection:** Resume panel is primary; technical metadata is behind “More details.”

---

## Explicit refresh (no file watcher)

**Decision:** Scans run on **Refresh context** or CLI scan — not on filesystem events.

**Why:** Bounded work, reproducible behavior, no daemon.

**See:** [PERFORMANCE_ARCHITECTURE.md](PERFORMANCE_ARCHITECTURE.md)

---

## Tauri + Python sidecar

**Decision:** Desktop UI in React/Tauri; business logic in Python subprocess IPC.

**Why:** Reuse CLI/core logic. Avoid duplicating scanner/resume in Rust.

**Trade-off:** Cold-start cost per IPC call — mitigated by bootstrap cache.

---

## Embedded Python for releases

**Decision:** Packaged app ships `runtime/python.exe` + stdlib + `grafid` — built by `packaging/build_runtime.ps1`.

**Why:** End users should not install Python.

**Trade-off:** Large build artifacts; `runtime/` gitignored; rebuild after backend changes.

---

## SQLite as single store

**Decision:** One `graf-id.db` for projects, sessions, scans, resumes.

**Why:** Simple, local, sufficient for MVP scale.

**Implication:** GrafiTalk does not attach to this DB — export only.

---

## Open Folder stays Rust-only, raw-path accepting (accepted risk)

**Decision:** `open_project_folder` (a Tauri command in
`desktop/src-tauri/src/lib.rs`, implemented in `shell.rs`) keeps accepting a
path string from the frontend, resolved and validated only on the Rust side
(`canonicalize()` + `is_dir()`). They are **not** rebound to `project_id`
with server-side (Python) path resolution.

**Why:** The 2026 audit (finding H12) flagged this as a defense-in-depth gap
— unlike every other IPC command, it does not validate against the
registry by id. Re-examining it during Milestone 8 surfaced why it was built
this way: `python.rs::run_ipc` spawns a **brand-new Python subprocess for
every single IPC call** (no persistent/pooled backend process), so *any*
Python round-trip — even a minimal `project_id → path` lookup — pays the
same ~100–300ms interpreter-startup cost as the full existing `open-folder`
IPC command. `open_project_folder` exists specifically
*because* that latency was unacceptable for this action (see their own doc
comments: "Rust-only — no Python IPC"); routing through Python again would
reintroduce exactly what they were built to avoid.

The alternative that avoids new latency — a Rust-side, in-memory
`project_id → path` cache kept in sync by hooking every bootstrap/dashboard/
project-detail/add/update/remove response — was evaluated and explicitly
declined: real new Rust state-management complexity and cache-staleness bug
risk, for a finding the original audit itself rated **low current risk**
(the webview only ever runs Graf-Id's own bundled frontend; there is no
remote or third-party content that could reach these commands with an
attacker-chosen path).

**Implication:** The existing validation (must canonicalize to a real,
existing directory) stays as the only guard. If Graf-Id's trust model ever
changes — e.g. loading any non-bundled/remote content into the webview, or
introducing a persistent backend process that makes a lookup call cheap —
this decision should be revisited.

---

## Related docs

- [ARCHITECTURE.md](ARCHITECTURE.md)
