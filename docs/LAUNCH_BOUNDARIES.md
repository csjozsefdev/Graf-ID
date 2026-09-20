# Launch boundaries (Open Folder vs Open Project)

English-only. Stabilization reference — not a feature milestone.

## Open Folder — show the directory

| Property | Value |
|----------|--------|
| Purpose | Open the **registered project root** in File Explorer |
| Desktop path | `openProjectFolderPath(path)` → Tauri `open_project_folder` → Rust `explorer` |
| Python IPC | **Not used** by the desktop UI in v1.0 (no Open Folder button) |
| DB / session | **None** |
| Path | Exact `projects.path` from registry (no subfolders, no guessing) |

## Open Project — resume the workflow

| Property | Value |
|----------|--------|
| Purpose | Update workflow state and launch editor or Explorer |
| Desktop path | `openProjectWorkflow(id)` → Python `ipc open-project` |
| State | `last_opened_at`, work session start/resume |
| Editor | `preferred_ide` on project or `config.json` |
| Explorer | **At most once** — Python defers (`launch_explorer=False`); UI calls Rust when `launch.explorer_opened` is true (Open project fallback only) |

## Open Project — coding agent (separate path)

| Property | Value |
|----------|--------|
| Purpose | Launch a coding agent (Claude Code, Codex CLI, custom) in a visible terminal |
| Desktop path | `openProjectWithCodingAgent(agentId, projectId)` → Python `ipc resolve-coding-agent-launch` (resolve only) → Rust `launch_coding_agent` (spawn only) |
| State | **None** — no work session, no `last_opened_at` update via this path |
| Editor/Explorer | Not involved — a coding agent launch never falls through to `openProjectWorkflow` |
| Routing | Decided client-side in `AppShell.handleOpenProject`, before any wake/session machinery starts, from the project's `preferred_ide` (or the default opener) being an `agent:<id>` value |

See [docs/CODING_AGENTS.md](CODING_AGENTS.md) for the full Editors-vs-Coding-Agents boundary and why this path never produces an Exit Note.

## CLI

- `graf-id ipc open-folder` — Python opens Explorer (CLI only).
- `graf-id open` — Python may open Explorer in-process (`launch_explorer=True`).
- `graf-id ipc resolve-coding-agent-launch <agent_id> <project_id>` — read-only resolution (executable/args/cwd) for a coding agent launch; never launches anything itself.

## Regression tests

`grafid/tests/test_folder_open_regression.py`
