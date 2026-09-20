# Graf-Id packaged app (Windows)

English-only. Run Graf-Id **without** installing Python or using a terminal.

## Packaging method

| Component | Role |
|-----------|------|
| **Graf-Id.exe** | Tauri desktop shell (UI) |
| **Embedded Python** | `runtime/python.exe` bundled as app resources |
| **Backend** | Same IPC as development: `python -m grafid.ipc <subcommand> …` |

This is **Tauri + embedded Python sidecar** (not a separate PyInstaller binary).

## How to run (end user)

1. Install or unzip the release from `desktop\src-tauri\target\release\bundle\`.
2. Run **Graf-Id.exe**.
3. On first launch the app creates local data automatically.

No Python, virtualenv, or `graf-id` CLI on PATH is required for the desktop app.

## Where your data lives

| Item | Location |
|------|----------|
| Config | `%LOCALAPPDATA%\Graf-Id\config.json` |
| Database | `%LOCALAPPDATA%\Graf-Id\graf-id.db` |
| App logs | `%LOCALAPPDATA%\Graf-Id\logs\graf-id.log` |
| Desktop backend log | `%LOCALAPPDATA%\Graf-Id\logs\desktop-backend.log` |

Portable override: set environment variable `GRAFID_DATA_DIR` to a writable folder before starting the app.

## First-time project setup

Use **Add Project** in the desktop sidebar (folder picker dialog). The app registers the path in the local database and runs an initial context scan. No separate Python install or CLI is required for the packaged app.

## Build from source (maintainers)

```powershell
cd <repo>
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

# Embedded runtime + verify
packaging\create_icons.ps1
packaging\build_runtime.ps1
packaging\verify_packaged_runtime.ps1

# Full Tauri bundle (requires Node.js + Rust)
packaging\build_release.ps1
# or: cd desktop && npm install && npm run tauri:build
```

Output: `desktop\src-tauri\target\release\bundle\`

## If the backend fails to start

The UI shows a short **user-facing** message. Technical details are appended to:

`%LOCALAPPDATA%\Graf-Id\logs\desktop-backend.log`

Common causes:

- Incomplete install (missing `runtime\python.exe` in the bundle)
- Antivirus quarantined the embedded runtime
- Data folder not writable

## Known limitations

- **Git** in terminal actions requires `git` on system PATH
- **No auto-update** installer in MVP
- **Embedded runtime size** ~50–100 MB depending on Python version
- Built and tested against the Python version used in `build_runtime.ps1` (from your `.venv` base install)

## Validation

```powershell
packaging\verify_packaged_runtime.ps1
pytest
```

After `tauri build`, run the bundled `Graf-Id.exe` once and confirm bootstrap loads (empty project list is OK).
