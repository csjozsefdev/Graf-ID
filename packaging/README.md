# Graf-Id Windows packaging (Milestone 10)

English-only notes for preparing a **local-first** desktop `.exe` without requiring users to install Python or use a terminal.

## Prerequisites (release build)

`build_runtime.ps1` embeds and ships whichever Python is behind the repo
`.venv` — so for a **release** build that `.venv` must be built from
**exactly Python 3.12.10**, the version pinned in the script
(`$RequiredPythonVersion`). This matches the 3.12 line Docker/CI test
against; the script fails loudly if the version doesn't match, rather than
silently shipping whatever Python happens to be installed on the machine
(a real drift found during 1.0.0 release verification — one dev machine's
system Python was 3.14, while Docker/CI test 3.12).

Since `pyproject.toml` already requires `>=3.12` and Docker/CI test 3.12,
the simplest fix is to make the **one** repo `.venv` a 3.12.10 venv —
there's no real reason for day-to-day dev (`tauri dev`, `pytest`) to run
on a different Python than what release builds and CI use:

```powershell
winget install --id Python.Python.3.12 --version 3.12.10
cd <repo>
py -3.12 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

If you'd rather keep an existing `.venv` on a different Python version for
other work, build a separately named venv instead and point
`build_runtime.ps1`'s `$VenvPython` at it for release builds only — the
script only checks the *version* it resolves, not the venv's name or path.

The script copies the **base Python install** behind that `.venv` (not Codex, not an embedded Tauri runtime). Unicode paths (including Hungarian user folders) are supported.

## Recommended strategy: Tauri + embedded Python sidecar

| Approach | Summary |
|----------|---------|
| **Embedded Python runtime** | Ship a private `python.exe` + stdlib + `grafid` package under the install folder (e.g. `runtime/python/`). Tauri spawns it for IPC. |
| **Tauri sidecar** | Same interpreter, registered as a Tauri sidecar binary so the shell resolves it next to the app executable. |

**Recommendation:** Use **one embedded CPython build** (Windows embeddable package or venv freeze) as a **sidecar**. The Tauri app remains the UI shell; Python stays the business-logic backend via `python -m grafid.ipc <subcommand> …`.

### Tradeoffs

| | Embedded / sidecar Python | PyInstaller one-file backend |
|--|---------------------------|------------------------------|
| **Pros** | Reuses existing IPC module tree; fast iteration; clear logs; small Rust shell | Single artifact |
| **Cons** | Larger install folder (~40–80 MB); must bundle deps | Harder debugging; slower cold start; Typer/subprocess quirks |
| **Fit for Graf-Id** | **Best match** (already IPC-based) | Possible later, not MVP |

**Not in scope:** MSI with admin, auto-update, telemetry, background services.

## Release directory layout (target)

```
Graf-Id.exe                 # Tauri frontend
runtime/
  python.exe                # Embedded interpreter
  Lib/                      # grafid + dependencies (portable layout)
```

### What the runtime contains

`build_runtime.ps1` builds `desktop/src-tauri/runtime/` from scratch on every run, from the pinned base Python 3.12.10:

- **Excluded at copy time:** the stdlib `test` suite, `idlelib`, `tkinter`, `turtle`/`turtledemo`, `ensurepip`, `lib2to3`, `venv`, `pydoc_data`, `msilib`; the extension modules `_test*.pyd`, `_ctypes_test.pyd`, `_tkinter.pyd` and the Tk DLLs; `grafid/tests`; every `__pycache__`, `.pyc`, `.git*` file; pip's `bin/` launchers and third-party `tests/` folders.
- **Bytecode** is never copied from a developer machine. All `.pyc` files are compiled at build time by the runtime's own interpreter (`compileall`, `unchecked-hash`, so they are timestamp-independent and reproducible). The installed app lives under `Program Files` where Python cannot write caches, so complete bytecode keeps start-up fast.
- **Stale output** (`target\release\runtime`, `target\release\bundle`) is deleted by `build_runtime.ps1` itself. It is `tauri.conf.json`'s `beforeBuildCommand`, so `build_release.ps1` and a bare `npm run tauri:build` are equally protected.
- **The build fails** if the final audit finds a forbidden directory/file, bytecode for another Python version, a non-code file inside `grafid`, or a `grafid.__version__` that differs from `pyproject.toml`.

`pytest` does not recurse into the bundled runtimes: `norecursedirs` in `pyproject.toml` skips `desktop/`.

`build_runtime.ps1` **removes** any `pythonXY._pth` file from the output so the portable `Lib/` layout works. Do not add embed-isolation `._pth` files to the shipped runtime.

User data **never** lives inside `runtime/`:

```
%LOCALAPPDATA%\Graf-Id\     # or GRAFID_DATA_DIR (portable mode)
  config.json
  grafid.db
  logs/
```

## Environment contract (set by Tauri when spawning IPC)

| Variable | Purpose |
|----------|---------|
| `GRAFID_RUNTIME_MODE` | `development` or `packaged` |
| `GRAFID_DATA_DIR` | Config, SQLite DB, logs (writable) |
| `GRAFID_RESOURCE_ROOT` | Directory on `PYTHONPATH` containing `grafid/` |
| `GRAFID_PYTHON` | Path to embedded `python.exe` |

Development continues to use `.venv` and optional `GRAFID_REPO_ROOT` / `GRAFID_PYTHON` overrides.

## Validation commands

```powershell
# From repo with venv active
graf-id ipc health
graf-id ipc runtime-check
graf-id ipc runtime-check --full
```

`runtime-check` validates directories, config JSON, and database integrity without duplicating business rules in Rust.

## Deterministic runtime dependencies

Production Python deps for the embedded runtime are locked in `packaging/runtime-requirements.txt` (source: `runtime-requirements.in`, currently `typer==0.25.1` plus transitive pins). `build_runtime.ps1` installs from this file with `--no-deps` so rebuilds are reproducible.

To refresh the lock after changing `pyproject.toml` dependencies:

```powershell
$target = "$env:TEMP\grafid-runtime-lock"
Remove-Item -Recurse -Force $target -ErrorAction SilentlyContinue
.venv\Scripts\pip install typer==0.25.1 --target $target
.venv\Scripts\pip freeze --path $target | Set-Content packaging\runtime-requirements.txt
```

Optional: pass `-UpgradePip` to `build_runtime.ps1` if you explicitly need a newer pip in the build venv.

## Build checklist

1. `packaging\create_icons.ps1` — exports the transparent logo PNG and favicons (`favicon.svg`, `favicon.ico`, `favicon-16x16.png`, `favicon-32x32.png`) into `desktop/public/` and `desktop/src-tauri/icons/`. Do **not** run `npx tauri icon` afterward (it bakes a dark background).
2. `packaging\build_runtime.ps1` → `desktop\src-tauri\runtime\`
3. `packaging\verify_packaged_runtime.ps1` — IPC smoke without UI
4. `packaging\build_release.ps1` — full build + `verify_release_bundle.ps1`
5. Artifacts: `target\release\graf-id-desktop.exe`, `target\release\bundle\msi\`, `target\release\bundle\nsis\`

See [docs/PACKAGED_USAGE.md](../docs/PACKAGED_USAGE.md).

## Known limitations

- Runtime is **built locally** from your `.venv` base Python (not committed to git).
- Portable mode (`GRAFID_DATA_DIR` next to exe) is supported via env but not default UI.
- Git integration still depends on user having `git` on PATH when opening terminals.

## Python modules

- `grafid/packaging/runtime.py` — mode detection, layout paths
- `grafid/packaging/validation.py` — startup validation report
- `grafid/packaging/bootstrap.py` — IPC-facing helpers

See root `README.md` for developer setup.
