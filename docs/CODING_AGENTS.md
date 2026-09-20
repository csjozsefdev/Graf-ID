# Coding Agents

A **Coding Agent** is any interactive CLI tool you want Graf-Id to launch, open
to a project's root directory — Claude Code, Codex CLI, or a tool of your own.
It is a deliberately different concept from an **Editor** (VS Code, Cursor,
PyCharm, Custom), and the two are not interchangeable.

## Editors vs Coding Agents

| | Editor | Coding Agent |
|---|---|---|
| Examples | VS Code, Cursor, PyCharm, Custom | Claude Code, Codex CLI, your own CLI tool |
| Work session | Started on launch | **Never started** |
| Process tracking | Lifecycle probe watches for the editor closing | **None** — Graf-Id does not track the process at all |
| Exit Note | Prompted when the editor closes | **Never shown** — there is nothing to close from Graf-Id's point of view |
| Launch surface | Hidden process spawn (`CREATE_NO_WINDOW`) | A visible terminal window |

Graf-Id's job for a coding agent stops at resolving the executable and
starting it in the right folder. Once the terminal opens, Graf-Id has no
further involvement — it does not know when the agent exits, and it does not
try to find out.

## Choosing Editor or Coding agent

In **Settings → Open Project starts** an **Editor / Coding agent** toggle picks
which kind of opener *Open project* uses. "Editor" lists VS Code, Cursor, etc.
and behaves as before (work session, Exit Note); "Coding agent" lists your
agents and just opens a terminal. Flipping the toggle remembers your last
choice on each side. The toggle's "Coding agent" side is disabled until at
least one agent exists. Save and its result (including errors) sit in a bar
that stays visible at the bottom of the Settings page.

## Why coding agents get no Exit Note

Exit Notes exist to hand a summary from one editor session to the next, since
an editor has no memory of its own between launches. A coding agent (Claude
Code, Codex CLI, or similar) manages its own session and context already —
layering Graf-Id's own session tracking on top would duplicate that, and
would require reliably detecting when the agent's process ends. CLI agent
processes don't have a stable, unique image name the way `Code.exe` or
`cursor.exe` do (`node.exe`, `cmd.exe`, and similar host processes are shared
with many unrelated programs), so that detection would be unreliable at best.
Rather than ship a lifecycle probe that sometimes lies, Graf-Id doesn't
attempt one: coding agents are a pure launcher, on purpose.

## Built-in agents

Claude Code and Codex CLI are offered as convenience presets — Graf-Id does
not assume you use either. They run on the same generic agent infrastructure
as custom agents; the preset only supplies a display name and the `PATH`
commands to look for (`claude`/`claude.cmd`, `codex`/`codex.cmd`).

**Resolution order** for a preset:

1. your explicit **executable override**, if you set one (Edit → *Executable
   override*, with **Browse…**);
2. otherwise `PATH` detection of the preset's commands;
3. otherwise **Not found** (Settings says why, and a launch attempt fails
   with the same reason — it never pretends to have launched).

A set override is never silently replaced: if it is invalid, the agent is
reported as unavailable with the reason and nothing falls back to `PATH`.
An override must exist, be a file (not a folder) and — because the terminal
is started with `cmd /C start` — be an `.exe`, `.cmd`, `.bat` or `.com` file
(a bare command name that resolves on `PATH` is also accepted). Saving
Settings rejects an invalid override with a specific message.

There is deliberately **no install-location heuristic**: Graf-Id never searches
the Start Menu, the registry, typical install folders, or desktop-app files.
Detection is `PATH` or an explicit path, nothing else. (A desktop app being
installed does not mean a CLI is launchable.)

**Removing presets.** Both presets can be removed with **Remove**, exactly like a
custom agent, so you don't have to keep looking at "Not found" rows for tools you
don't use. The preset definition stays in code (so it keeps updating with new
Graf-Id versions); only a `hidden` flag is stored in your `config.json`
(`builtin_agents`). Use **+ Add preset: …** under the list to bring one back —
it returns with default `PATH` detection (a removal also clears its override
and arguments).

## Custom agents

Add any other interactive CLI tool from **Settings → Coding agents → Add
coding agent**:

- **Display name** — shown in Settings and in the Open Project opener list.
- **Executable** — either a bare command resolved on `PATH` (`mytool`) or an
  explicit path to the executable (`C:\Tools\MyAgent\agent.exe`). An explicit
  path must point to a file (not a folder) that exists and is an `.exe`,
  `.cmd`, `.bat` or `.com`; Settings rejects a new or changed path that is not,
  with a specific message. (An unchanged entry whose tool was uninstalled later
  just shows **Not found** — it never blocks saving other settings.) A bare
  command is resolved on `PATH` and may be saved before it is installed.
- **Arguments** — one per line. Each line becomes exactly one argument passed
  to the process; there is no shell quoting to worry about, so a line
  containing spaces does not need escaping and is never split.

Custom agents can be edited or removed at any time. A newly added agent has
no id yet — Graf-Id assigns one deterministically from its display name when
you click **Save** — so it becomes selectable as an opener right after that
save completes.

**No dangling references.** Removing any agent (preset or custom) that is used as
an opener is handled deterministically when you Save:

- if it was the **default opener**, the default falls back to **Auto Detect**;
- any **project-specific opener** that used it is reset to inherit the default
  opener;
- Settings tells you both (the save message names the default fallback and the
  affected projects). An opener naming an agent that never existed is likewise
  never stored.

Removing agents never touches work sessions or history.

## Availability

Settings recomputes each agent's availability (PATH lookup or explicit-path
validation) every time Settings loads or saves, and shows **Available** or
**Not found** next to each one — including built-ins. There is no separate
"Check agent" action beyond reloading/saving Settings; either way, checking
availability only resolves the executable and never launches it or starts
any session.

## Security model

Coding agent launch never builds a shell command string from user input.
Project path, executable, and every argument stay as separate, structured
values end to end:

1. Python resolves `{executable, args, cwd}` for the requested agent + project
   (read-only — a `PATH`/filesystem lookup, no DB write, no session).
2. Rust receives that as structured data (never a concatenated string) and
   opens a visible terminal running it, with the project root as the working
   directory.
3. On Windows, the terminal is spawned via `cmd /C start "" <exe> <args...>`
   using `raw_arg()` with a from-scratch quoting function
   (`quote_cmd_arg` in `desktop/src-tauri/src/shell.rs`) that quotes every
   value independently and doubles `%`, so no field — including the project
   path or a custom argument — can break out of its own argument or be
   reinterpreted by `cmd.exe`'s `&|<>^%` metacharacters. See `mod tests` in
   the same file for the quoting/round-trip test coverage, and
   [SECURITY.md](../SECURITY.md).

You may freely configure any executable and arguments for a custom agent, or
an executable override for a preset — that configuration is yours to control —
but Graf-Id itself never turns user input into an arbitrary shell string.

Imported export bundles are not trusted with this: `graf-id import` drops any
`coding_agents` / `builtin_agents` (definitions and executable overrides) from
the bundled `config.json` and resets an `agent:` opener to Auto Detect, the same
way it already handles `custom_opener_path`. Re-add agents in Settings after an
import.

## What Graf-Id does *not* do for coding agents

- No work session is created or resumed.
- No process-lifecycle or editor-readiness probe runs.
- No Exit Note is prompted, and session history is never touched.
- Graf-Id does not manage, read, or store the agent's own memory, context, or
  conversation history — that stays entirely with the agent itself.
