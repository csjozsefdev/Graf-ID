# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.0   | Yes       |

## Reporting a vulnerability

Graf-Id is a local-first desktop utility. If you discover a security issue:

1. **Do not** open a public GitHub issue that contains vulnerability details.
2. Report it privately through [GitHub private vulnerability reporting](https://github.com/csjozsefdev/Graf-ID/security/advisories/new) (the repository's **Security** tab > **Report a vulnerability**).
3. If that option is not available to you, open a public issue that says only that you have a security report (no details) and ask for a private channel; the maintainer will reply there.
4. Include steps to reproduce, the affected version, and an impact assessment.

We aim to acknowledge reports within 7 days.

## Threat model (summary)

Graf-Id runs entirely on the user's machine. It does not send project data to cloud services. Primary risks:

- **Local data exposure** — SQLite DB and config at `%LOCALAPPDATA%\Graf-Id` (or `GRAFID_DATA_DIR`)
- **Subprocess IPC** — Tauri spawns bundled Python for backend commands; no network listener in production
- **Filesystem access** — scans registered project folders on explicit user action (Refresh context)
- **Export files** — user-chosen paths via save dialog
- **Untrusted project content** — a registered project (e.g. a cloned third-party repo) is not fully trusted. The scanner and workflow-artifact reader never follow symlinks or NTFS junctions (`grafid/utils/safe_path.py`) and verify every read stays inside the registered project root, so a crafted link cannot make Graf-Id read files from outside the project.
- **Import bundles** — `graf-id import` treats the bundled `config.json` as untrusted input: `custom_opener_path` is always stripped and `default_project_opener`/`preferred_ide` reset off `"custom"`, so a restored bundle cannot silently point the "Open Project" editor launch at an arbitrary executable. The same applies to Coding Agents: `coding_agents` and `builtin_agents` (agent definitions and executable overrides) are always dropped, and an `agent:` opener is reset to `"system"`.

## Export, import and restore safety

- **Exports** are rendered from a backend `ProjectContext`, never from UI text. They contain only project-relative, capped file lists (secret-looking names such as `.env`, `*.pem`, `id_rsa`, absolute paths, `..` traversal and virtualenv trees are dropped) and no database ids. Workflow documents from a **parent folder** are UI-only and never exported; symlinked/junction documents are never read (see above).
- **Context import** validates the file (schema, `schema_version`, types, size before reading, UTF-8/JSON), shows a preview, and writes only after explicit confirmation, in one transaction that refuses to write if the notes changed since the preview. It writes the project notes only; it cannot reach configuration, editor paths or coding agents.
- **Restore** treats a backup as untrusted input: member allowlist (no traversal), per-member/total size limits, a compression-ratio limit and a byte cap enforced while streaming; the database is extracted to a temp file, integrity-checked, refused if its schema is newer, and migrated **on the temp copy**; a safety copy of the current database is taken with SQLite's backup API; the switch is one atomic replace. Any earlier failure leaves the live database byte-identical. Settings are never overwritten unless the caller opts in, and then only an allowlist (`log_level`, `usage_journal`, `debug_timing`, `compact_mode`, `default_project_opener`) is merged — never editor paths, coding agents or interpreter paths.

## Tauri capabilities

The desktop shell grants minimal permissions (`desktop/src-tauri/capabilities/default.json`):

| Permission | Purpose |
|------------|---------|
| `core:default` | Base Tauri runtime |
| `core:tray:default` | System tray hide/show on Open project |
| `core:menu:default` | Application menu |
| `core:window:*` | Close, hide, show, focus main window |
| `dialog:default` | Export save dialog and Add Project folder picker |

The Coding Agent launcher (`ipc_resolve_coding_agent_launch` + `launch_coding_agent`, shipped in 1.0.0) **is** invoked by the UI, from a deliberately separate code path from the editor launch above — see [docs/CODING_AGENTS.md](docs/CODING_AGENTS.md). It resolves an agent's executable (PATH lookup or an explicit path the user configured) and hands `{executable, args, cwd}` to Rust as structured data, never a shell string. The visible terminal spawn on Windows (`cmd /C start`) uses `raw_arg()` with a from-scratch, unit-tested `quote_cmd_arg()` — every value (project path, executable, each argument) is quoted independently and `%` is doubled, so no field can break out of its own argument or be reinterpreted by `cmd.exe`'s `&|<>^%` metacharacters (`desktop/src-tauri/src/shell.rs`, `mod tests`).

## Content Security Policy

Production builds use a minimal CSP in `tauri.conf.json`:

- `default-src 'self'`
- `script-src 'self'`
- `style-src 'self' 'unsafe-inline'` (React inline styles)
- `connect-src 'self' ipc: http://ipc.localhost`

Development mode uses `devCsp` in `tauri.conf.json`, which additionally allows `http://localhost:1420` and WebSocket for Vite HMR. Production `csp` does not include localhost origins.

## Dependency hygiene

- Python: `typer` and transitive deps pinned in `packaging/runtime-requirements.txt`
- Frontend: `npm audit --audit-level=high` in CI (zero high/critical required)
- Rust: `cargo check --locked` and `cargo test --locked` in CI
