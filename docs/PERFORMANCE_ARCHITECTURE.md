# Performance architecture notes (MVP)

This is a short technical reference for why the desktop app is fast **without** introducing a long-lived backend daemon or background indexing.

## Problem we hit

Early desktop builds were “correct” but slow: normal UI actions spawned a fresh `python.exe` per click.

The biggest cost was not business logic — it was **process startup + import work**:
- starting a new interpreter
- importing large module trees
- Typer/CLI glue paths not optimized for IPC

## Fix: lightweight IPC entrypoint + lazy imports

**Old path (too heavy for UI clicks):**
- Tauri → `python -m grafid.cli.main ipc …` (retired)

**Current path (optimized for IPC):**
- Tauri → `python -m grafid.ipc <subcommand> …`
- A small entry module (`grafid/ipc/desktop_entry.py`) dispatches subcommands and keeps imports handler-scoped.

Result: less cold-start overhead, less import churn.

## Fix: bootstrap preload + in-memory cache (avoid IPC for reads)

The desktop app calls `ipc_bootstrap` once on startup and caches:
- `app_settings`
- per-project `resume_panel`
- per-project `history`

That enables **0-spawn** navigation:
- settings open
- selecting projects
- viewing history tabs

Python subprocesses remain for explicit “work” actions:
- Refresh Context (`refresh-resume`)
- Open Project (`open-project`)
- End session (`close-session`) — CLI/IPC; no desktop button in v1.0

## Scanner safeguards (keep work bounded)

The design goal is “explicit refresh, bounded scan”:
- no background watcher
- no always-on indexing
- no daemon that can silently eat CPU

When refresh runs, it is constrained by allowlists/ignore rules, and depth/size limits.

## Why no daemon (intentional)

Long-lived background services tend to creep:
- “just one more” periodic sync
- hidden CPU usage
- stateful bugs that are harder to reproduce

For MVP, Graf-Id stays predictable:
- **explicit** refresh
- **local-only** storage
- **deterministic** summary assembly from your sources

