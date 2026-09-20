# Graf-Id cleanup guide

Disk cleanup, dev environment reset, and what the **Clean / Dirty** git chip means in the desktop UI.

**Typical disk audit:** ~8 GB under `desktop/src-tauri`, with **~98% in `target/`** (Rust/Cargo cache) and **~125 MB in `runtime/`** (embedded Python for packaged builds).

---

## Quick checklist (before `tauri dev`)

1. Quit Graf-Id if it is running (tray **Quit** or close the dev window).
2. Clear stale packaged env vars (after MSI smoke tests):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File <repo>\packaging\clear_dev_env.ps1
   ```

3. **Restart the terminal or Cursor** so `PYTHONHOME` / `GRAFID_*` are not inherited from an old session.
4. Verify the repo venv:

   ```powershell
   cd <repo>
   .\.venv\Scripts\python.exe -c "import encodings; import grafid; print('ok')"
   ```

5. Start dev from `desktop/`:

   ```powershell
   cd <repo>\desktop
   npm run tauri:dev
   ```

Use **`npm run tauri:dev`** only — not `npm run dev` alone.

---

## Git **Clean** vs **Dirty** in the Graf-Id UI

The sidebar git chip (**Clean**, **Dirty**, **No git**) reflects the **registered project folder’s git working tree**, not Graf-Id’s internal database.

| Chip | Meaning |
|------|---------|
| **Clean** | Git repo, no staged or modified tracked files (porcelain status empty for changes). |
| **Dirty** | Git repo with uncommitted changes (modified, staged, untracked, or rename lines). |
| **No git** | Folder is not a git repository (or git unavailable). |

**If Graf-Id shows Dirty for this repo:** commit, stash, or discard local changes in `<repo>`. Untracked files also count as dirty in porcelain parsing.

```powershell
cd <repo>
git status
git add -A
git commit -m "your message"
```

After a clean working tree, run **Refresh context** on the project (or reopen it) to update the chip.

---

## Dev environment variables (Windows)

Packaged installs and release smoke tests can leave **User**-scope variables that break `tauri dev`:

| Variable | Typical stale value | Symptom |
|----------|---------------------|---------|
| `PYTHONHOME` | `C:\Program Files\Graf-Id\runtime` | `ModuleNotFoundError: No module named 'encodings'` |
| `GRAFID_PYTHON` | packaged `python.exe` | wrong interpreter selected |
| `PYTHONPATH` | packaged `site-packages` | import from wrong tree |

**Fix:** run `packaging\clear_dev_env.ps1`, then restart the IDE/terminal.

Debug IPC subprocesses strip inherited `PYTHONHOME` in Rust (`python.rs`); a **Process**-scope variable from an already-open Cursor session still breaks direct `.venv\Scripts\python.exe` calls until you restart.

Backend errors are appended to:

```
%LOCALAPPDATA%\Graf-Id\logs\desktop-backend.log
```

---

## System tray

When the main window is hidden to tray (e.g. after **Open project**):

| Action | Behavior |
|--------|----------|
| **Single left click** | Opens the tray menu only (Show Graf-Id / Quit). Does not restore the window. |
| **Double left click** | Restores the main window: `unminimize()` → `show()` → `set_focus()`. |
| **Show Graf-Id** (menu) | Same restore sequence as double-click. |

Tray icon is registered once at app startup (`setup_system_tray` in `lib.rs`).

---

## Benign WebView2 message on exit

On shutdown you may see:

```
Failed to unregister class Chrome_WidgetWin_0. Error = 1412
```

This comes from **Chromium/WebView2**, not Graf-Id application logic. It is harmless if the app exits normally. Common during `tauri dev` stop (Ctrl+C) or tray Quit.

---

## Why `src-tauri` can grow large

The Tauri desktop shell uses **Rust/Cargo**. Every `tauri dev` and `tauri build` run compiles dependencies and stores output under:

```
desktop/src-tauri/target/
```

On an active Windows dev machine, `target/` commonly reaches **several gigabytes** because it contains:

- **Debug builds** (`target/debug/`) — object files (`.o`), libraries (`.rlib`), Windows debug symbols (`.pdb`)
- **Incremental compilation caches** (`target/debug/incremental/`) — rustc reuse data between builds
- **Release builds** (`target/release/`) — optimized binaries, installer staging (MSI/NSIS)
- **Copied embedded Python** inside `target/*/runtime/` during builds (~100–125 MB per copy)

This is **normal Cargo behavior**. It is not application data, logs, or duplicate GrafiTalk content.

A typical audit for this repo found **~7.9 GB** in `src-tauri`, with **~98% in `target/`** and only **~125 MB** in the intentional `runtime/` tree.

---

## What is safe to delete

| Path | Safe? | Notes |
|------|-------|-------|
| `desktop/src-tauri/target/` | **Yes** | Entire Rust build cache. Regenerated on next `cargo` / `tauri` command. |
| `target/debug/` | **Yes** | Largest dev-build footprint. |
| `target/debug/incremental/` | **Yes** | Stale incremental caches. |
| `target/debug/deps/` | **Yes** | Compiled dependencies for debug profile. |
| `target/release/deps/` | **Yes** | Release dependency artifacts (rebuild with `tauri build`). |
| `target/release/build/` | **Yes** | Release build-script output. |
| Installer files under `target/release/bundle/` | **Optional** | Safe to delete if you can rerun `tauri build` to recreate MSI/NSIS. |

### Preferred cleanup command

From `desktop/src-tauri`:

```powershell
cd <repo>\desktop\src-tauri
cargo clean
```

This removes the whole `target/` directory and typically recovers **~7–8 GB** after heavy dev use.

**Tip:** Close the running Graf-Id app first. If `graf-id-desktop.exe` is still running from `target/release/`, Windows may lock the file and `cargo clean` can fail with “access denied”. Quit the app and run `cargo clean` again.

---

## What to keep

Do **not** casually delete these:

| Path | Why |
|------|-----|
| `desktop/src-tauri/runtime/` | Embedded Python + `grafid` package for packaged builds. Rebuild with `npm run build:runtime` if removed. |
| `desktop/src-tauri/src/` | Rust Tauri bridge source. |
| `desktop/src-tauri/icons/` | App icons for bundling. |
| `desktop/src-tauri/gen/` | Tauri generated config. |
| `desktop/src-tauri/capabilities/` | Tauri security capabilities. |
| `Cargo.toml`, `tauri.conf.json` | Project configuration. |

User data (SQLite, config, logs) lives under **`%LOCALAPPDATA%\Graf-Id`**, not in `src-tauri`.

---

## Expected size after cleanup

| State | Approximate `src-tauri` size |
|-------|------------------------------|
| After `cargo clean` | **~125 MB** (mostly `runtime/`) |
| After `cargo check` | **~1–3 GB** (debug artifacts only) |
| After `tauri dev` / many debug sessions | **3–8 GB** (grows over time) |
| After `tauri build` (release + installers) | **+1–2 GB** on top of debug cache |

Exact numbers depend on how many times you built and which profiles were used.

---

## Expected rebuild cost

After `cargo clean`:

| Command | What happens | Rough time (this machine) |
|---------|----------------|---------------------------|
| `cargo check` | Recompiles dependencies + app (debug) | ~5–10 minutes |
| `npm run tauri:dev` | Debug app + frontend dev server | First run slower after clean |
| `npm run tauri:build` | Full release + embedded runtime + installers | ~10–20+ minutes |

No source or Python application logic is lost. Only compiled cache is removed.

---

## Git ignore

`target/` is already ignored:

- `.gitignore` → `desktop/src-tauri/target/`
- `desktop/.gitignore` → `src-tauri/target/`

`runtime/` is also gitignored (large binaries). Regenerate with:

```powershell
cd <repo>\desktop
npm run build:runtime
```

---

## Quick disk checklist

1. Quit Graf-Id if it is running.
2. `cd desktop\src-tauri`
3. `cargo clean`
4. Confirm `runtime/` still exists.
5. `cargo check` or `npm run tauri:dev` to verify rebuild.
6. Optional: measure folder size before/after for your own records.

For env vars, git **Dirty** chip, and tray behavior, see the sections at the top of this file.

---

## Related docs

- [HANDOVER.md](HANDOVER.md) — returning to the project after months away
- [desktop/README.md](../desktop/README.md) — dev and release workflow
- [packaging/README.md](../packaging/README.md) — embedded runtime build
- [README.md](../README.md) — project overview
