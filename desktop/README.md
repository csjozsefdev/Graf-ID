# Graf-Id Desktop (Tauri shell)

Desktop UI for the Graf-Id Python core. The UI does not access SQLite directly.

## Architecture

```
React UI  --invoke-->  Tauri (Rust)  --subprocess-->  Python `graf-id ipc`
                                                      Services + SQLite
```

- **Frontend** (`desktop/src/`): sidebar, dashboard, history, settings.
- **IPC client** (`desktop/src/ipc/client.ts`): typed wrappers for Tauri commands.
- **Rust bridge** (`desktop/src-tauri/src/python.rs`): spawns bundled or dev Python, reads JSON from stdout.
- **Python IPC** (`grafid/ipc/`): reuses existing services (no duplicated business logic).

## Prerequisites (development only)

1. **Python 3.12+** — repo `.venv` with `pip install -e ".[dev]"` from repo root.
2. **Node.js** + **npm**
3. **Rust** — [rustup](https://rustup.rs/) for `tauri dev` / `tauri build`

End users of the **packaged app** do not install Python, Node, or Rust.

## Development workflow

```powershell
cd <repo>
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

cd desktop
npm install
npm run tauri:dev
```

Use **`npm run tauri:dev`** only (not `npm run dev` alone). If port 1420 is in use, stop any standalone Vite process first.

**Before first dev run or after a packaged install:** see [docs/CLEANUP.md](../docs/CLEANUP.md) — clear stale `PYTHONHOME` / `GRAFID_*` with `packaging\clear_dev_env.ps1`, then restart the terminal.

## System tray

After **Open project**, the window may hide to tray.

| Input | Result |
|-------|--------|
| Single left click on tray icon | Tray menu only (Show Graf-Id / Quit) |
| Double left click | Restore main window and focus |
| **Show Graf-Id** menu item | Same as double-click |

Optional environment variables:

| Variable | Purpose |
|----------|---------|
| `GRAFID_PYTHON` | Override `python.exe` (dev). `tauri dev` prefers repo `.venv` and ignores a missing packaged path. |
| *(cleanup)* | Stale packaged env in a terminal (`encodings` / `backend_unavailable`): run `powershell -File ..\\packaging\\clear_dev_env.ps1` from `desktop/`, then restart Cursor. Debug builds ignore packaged mode unless `GRAFID_FORCE_PACKAGED=1`. |
| `GRAFID_REPO_ROOT` | Repo root when cwd is not `desktop/` |
| `GRAFID_RUNTIME_MODE` | `development` or `packaged` |
| `GRAFID_DATA_DIR` | Writable config/DB/logs directory |
| `GRAFID_RESOURCE_ROOT` | Directory on `PYTHONPATH` containing `grafid/` |

## Packaged / release build

From repo root:

```powershell
packaging\build_release.ps1
```

This builds the embedded runtime, runs IPC smoke tests, produces:

| Artifact | Path |
|----------|------|
| Release binary | `desktop\src-tauri\target\release\graf-id-desktop.exe` |
| MSI installer | `desktop\src-tauri\target\release\bundle\msi\Graf-Id_1.0.0_x64_en-US.msi` |
| NSIS installer | `desktop\src-tauri\target\release\bundle\nsis\Graf-Id_1.0.0_x64-setup.exe` |

Verify without repo `.venv`:

```powershell
packaging\verify_release_bundle.ps1
```

**User data (packaged):** `%LOCALAPPDATA%\Graf-Id` — `config.json`, `graf-id.db`, `logs\` (override with `GRAFID_DATA_DIR`).

See [docs/PACKAGED_USAGE.md](../docs/PACKAGED_USAGE.md) and [packaging/README.md](../packaging/README.md).

## Desktop features (v1.0)

| Area | Features |
|------|----------|
| **Sidebar** | Project list (search, category, status), **Add project**, **⋯ → Remove from Graf-Id** |
| **Dashboard** | Project header + Resume panel for selected project |
| **Project header** | **Open project**, **Refresh context**, **Export** (JSON/MD/TXT), **More details** |
| **Resume panel** | MVP sections, session fields, folded activity/git detail, wake reminder |
| **History** | Separate nav page — scan snapshot cards (read-only) |
| **Settings** | Default opener, usage journal, debug timing, Grafi advisor (Show / Helping Mode / motion / critical alerts only), open data/logs folders |

**Not in v1.0 UI:** standalone Open folder button, Open terminal, dashboard Remove button, in-app project edit.

**Grafi advisor (v1.0.0):** Bottom-left advisor for status messages. **Helping Mode** adds short hover/focus tooltips on dashboard controls (`data-grafi-help`). All Grafi toggles live in Settings.

**Dev vs packaged Python:** `tauri dev` uses the repo `.venv` (latest `grafid` source). Release builds use `desktop/src-tauri/runtime/` — rebuild with `packaging\build_runtime.ps1` after backend changes.

Dev-server troubleshooting on Windows: [docs/TAURI_DEV_WATCHER.md](../docs/TAURI_DEV_WATCHER.md).

## Python IPC commands (manual test)

```powershell
graf-id ipc health
graf-id ipc runtime-check
graf-id ipc bootstrap
graf-id ipc dashboard
graf-id ipc project-detail 1
graf-id ipc open-project 1
graf-id ipc open-folder 1
graf-id ipc add-project my-app C:\dev\my-app --category "Client Work"
graf-id ipc update-project 1 --status paused --notes "On hold"
graf-id ipc refresh-resume 1
graf-id ipc close-session 1 --exit-note "Shipped feature" --next-step "Tests"
```

Each command prints one JSON object on stdout.

## Workflow launch (Open project)

| Action | Desktop behavior |
|--------|------------------|
| **Open project** | Python IPC: updates `last_opened_at`, starts/resumes session, launches **Cursor** or **VS Code**. May hide to tray on success. Explorer fallback via Rust when editor unavailable. |

### Project wake transition

After **Open project**, a short full-screen transition plays while Graf-Id launches your editor and polls for readiness (Cursor or VS Code).

- The overlay **stays up until the IDE is ready** — not on a fixed timer.
- If startup is fast, the transition fades out as soon as readiness is detected.
- If startup is slow, the intro **video loops**, the terminal sequence repeats, and the projector shows: *Project startup is taking longer than expected...*
- **Skip** ends the animation early; readiness handling continues in the background.
- **Reduced motion** skips the video and uses the same readiness gate.

Configure editor per project: `graf-id add my-app C:\dev\my-app --ide cursor` (or `vscode`).  
Global default in `config.json`: `"preferred_ide": "cursor"` (or `vscode`, `explorer`).

See [docs/LAUNCH_BOUNDARIES.md](../docs/LAUNCH_BOUNDARIES.md).

## Tests

```powershell
# Python (repo root)
.venv\Scripts\pytest grafid\tests -q

# Desktop utilities
cd desktop
npm test
```

## Known limitations

- **Python subprocesses** for heavy actions (Open project, Refresh context, export write, add/remove). Bootstrap caches project list, resume panels, and history for fast navigation.
- **Git** — requires `git` on PATH for git snapshot collection.
- **No Grafi animations, watchers, cloud, or AI.**
- **Exit note** — prompted after editor close when detection is reliable; CLI/IPC fallback.
