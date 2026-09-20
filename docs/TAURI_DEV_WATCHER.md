# Tauri dev watcher notes (Windows)

## EBUSY errno -4082 during `npm run tauri:dev`

### Root cause

**Vite's dev server watcher** (Node `fs.watch` / chokidar), not the Tauri Rust watcher.

When `tauri dev` runs, it starts `beforeDevCommand` (`npm run dev` → Vite). Vite watches the `desktop/` project root. By default that includes `src-tauri/`, including `target/debug/build/.../build_script_build.exe`.

While **Cargo compiles**, those `.exe` files are **locked**. Vite tries to attach a filesystem watch → Windows returns **EBUSY** (resource busy).

Stack trace signature:

```
createFsWatchInstance (vite/.../dep-*.js)
syscall: 'watch'
code: 'EBUSY'
path: .../src-tauri/target/debug/build/.../build_script_build.exe
```

### What is not the primary cause

- `.taurignore` only affects **Tauri's** `src-tauri` watcher, not Vite.
- `.taurignore` previously listed only `runtime/`, so `target/` was still visible to Vite.

### Fix (applied)

`desktop/vite.config.ts` — `server.watch.ignored`:

- `**/src-tauri/target/**`
- `**/src-tauri/runtime/**`
- `**/src-tauri/gen/**`

`desktop/src-tauri/.taurignore` — also ignore `target/` and `gen/` for Tauri's Rust watcher.

### Common on Windows?

Yes. Tauri + Vite + Cargo on the same tree is a known friction point on Windows when watchers overlap build artifacts.
