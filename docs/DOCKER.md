# Docker dev/test environment

A reproducible, containerized environment for running Graf-Id's automated
test suites and checks — **not** for running the native desktop app itself.
The GUI (WebView2 window, system tray, MSI/NSIS installers) is Windows-only
and stays host-only.

## Build targets

The single `Dockerfile` has two targets:

- **`test`** (default) — Python 3.12 + Node 20 + git. Runs the Python test
  suite, the frontend (Vitest) test suite, the frontend production build,
  and the TypeScript typecheck.
- **`rust-check`** (optional, larger — adds the Rust toolchain and Tauri's
  Linux system libraries) — builds on `test` to additionally run
  `cargo check` / `cargo test` against `desktop/src-tauri`.

```bash
docker build --target test -t graf-id:test .
docker build --target rust-check -t graf-id:rust-check .
```

## Running the checks

```bash
# Python test suite
docker run --rm graf-id:test python -m pytest grafid/tests -q

# Frontend test suite
docker run --rm -w /app/desktop graf-id:test npm test -- --run

# Frontend production build
docker run --rm -w /app/desktop graf-id:test npm run build

# TypeScript typecheck (npx --prefix does not pick up the local tsconfig.json
# correctly — use an explicit working directory instead)
docker run --rm -w /app/desktop graf-id:test npx tsc --noEmit

# Rust check (Tauri Linux prerequisites + rustup toolchain)
docker run --rm -w /app/desktop/src-tauri graf-id:rust-check cargo check --locked

# Rust test suite
docker run --rm -w /app/desktop/src-tauri graf-id:rust-check cargo test --locked
```

On Windows/Git Bash, prefix any command whose arguments include a leading
`/path` (e.g. `-w /app/desktop`) with `MSYS_NO_PATHCONV=1` — otherwise MSYS
rewrites the Unix-style path into a bogus Windows one before `docker.exe`
sees it.

## Host-only checks (not run in Docker)

These stay Windows-host-only because they test Windows-specific behavior or
require the native GUI:

- `desktop/src-tauri` tests behind `#[cfg(target_os = "windows")]`
  (`shell.rs`'s terminal-launch command-shape tests, `workflow_launch.py`'s
  hidden-console/Explorer-launch tests) — the code under test doesn't exist
  to call on other platforms.
- Anything requiring the actual WebView2 window, system tray, or an
  installer (MSI/NSIS) build/run — `tauri dev` / `tauri build` are not run
  in this container.
- Windows junction-based tests in `test_build_cache.py` /
  `test_symlink_safety.py` — junctions are a Windows-only filesystem
  mechanism.

All of the above skip cleanly with an explicit, environment-only reason
string when run under `pytest`/`cargo test` on Linux — they are not hidden
or deleted, just correctly gated.

## Known findings from the first containerized run

Running the full suite on real Linux for the first time (rather than just
reading the code) surfaced two things worth flagging, neither of which this
Docker milestone silently fixed:

1. **`test_resume_help_lists_project_and_options` fails in the container.**
   Root cause: `typer` is unpinned (`typer>=0.12` in `pyproject.toml`), and
   the version that resolves fresh inside the container (0.27.2) renders
   `--help` output differently (`IDENTIFIER` vs `{identifier}`) than
   whatever is cached in the developer's local `.venv`. This is a real
   dependency-drift discovery — exactly what a reproducible environment is
   for — and touches user-facing CLI text, so it's left for a deliberate
   decision (pin the version? update the test's expectation? accept as
   environment-specific?) rather than patched here.

2. **`process_probe::tests::dead_launcher_pid_is_not_alive` fails under
   `cargo test --locked` on Linux.** The Windows implementation of
   `is_pid_alive` in `desktop/src-tauri/src/process_probe.rs` has an
   explicit `if pid == 0 { return false; }` guard; the `#[cfg(not(windows))]`
   fallback (`kill -0 <pid>`) does not. POSIX `kill(0, sig)` has special
   broadcast-to-own-process-group semantics, so the spawned `kill` process
   can always signal itself — meaning the Linux/macOS fallback incorrectly
   reports PID 0 as "alive". This is pre-existing code, not a regression
   from this or the earlier audit campaign's Rust work, and is currently
   dead code in production (the app ships Windows-only today) — but it's a
   real, reproducible cross-platform correctness bug if that code path is
   ever exercised. Left unfixed pending an explicit decision.

`npm ci` also reported 6 known vulnerabilities (3 moderate, 3 high) in
frontend dependencies during the container build — not actioned here,
flagged for a separate dependency-update pass.

## What the image does *not* contain

Verified by inspecting a running container and the build's layer history:
no `.db`/SQLite files, no `.git`, no user export data, no
`config.json` (local app config), and no Rust `target/` baked into the
image layers (it only appears in the writable layer of a container that
has actually run `cargo check`/`cargo test`, never committed to the image
itself). `node_modules` (~115 MB) is present by design — it's needed to run
the frontend suite/build/typecheck inside the container.
