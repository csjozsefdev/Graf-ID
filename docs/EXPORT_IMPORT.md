# Export, import and backup

What leaves Graf-Id, what may come back in, and how a backup is restored safely.

| I want to… | Use |
|------------|-----|
| Hand one project to GrafiTalk | Project header → **Export → GrafiTalk handoff** |
| Keep the full structured context of one project | **Export → JSON** |
| Read or share a project summary | **Export → Markdown** / **TXT** |
| Give GrafiTalk every project at once | Settings → Data → **Export all projects…** |
| Bring a handoff file into a project | Project header → **Import context…** |
| Back up / restore all of Graf-Id | Settings → Data → **Create backup…** / **Restore from backup…** |

Everything is on demand and local. Nothing is sent anywhere.

---

## One source of truth: `ProjectContext`

Every export and the **Project Snapshot** card are rendered from one backend object, `ProjectContext` (`grafid/resume/project_context.py`):

- **identity** — name, category, status, last opened, open session
- **continuity** — current focus, where you left off, suggested next step, blockers, open issues, recent fixes / improvements, confidence, sources
- **git** — branch, state, modified/staged files, recent commits
- **context** — project notes and the list of workflow document names

Exports never scrape UI text. Scanner code markers (`TODO`, `FIXME`, …) are not used for issues, next steps or changes. Commit subjects are classified conservatively: only conventional prefixes (`fix:`, `feat(scope):`) or an imperative first word count; `chore:`, `docs:`, `test:` and similar are ignored.

---

## Formats

Filenames are suggested as `<project-slug>-<label>-<YYYY-MM-DD>.<ext>`.

| Format | Button | Content |
|--------|--------|---------|
| **GrafiTalk handoff** | *GrafiTalk handoff* | Lean JSON in the flat **GrafiTalk contract v0.1** (below). Import it in GrafiTalk's Context panel. |
| **JSON** | *JSON* | The same flat v0.1 keys **plus** the additive `graf_id` block with the full structured context. |
| **Markdown** | *Markdown* | GrafiTalk's labelled sections: Project, Current status, What changed, Current blocker, Next step, Estimated time, Notes, Files updated. |
| **TXT** | *TXT* | The same sections as plain text. |

### GrafiTalk contract v0.1 (owned by GrafiTalk)

| Key | Type | Notes |
|-----|------|-------|
| `source` | `"graf-id"` | required |
| `schema_version` | `"0.1"` | required, **string**; the only version GrafiTalk accepts |
| `project_name` | string | required |
| `current_status` | string | omitted when there is nothing reliable to say |
| `changes` | string[] | recent fixes and improvements from trusted commits |
| `blockers` | string[] | |
| `next_steps` | string[] | |
| `estimated_time` | string | |
| `notes` | string | |
| `files` | string[] | project-relative, capped; see *Safety* |

GrafiTalk ignores unknown keys and rejects files of 256 KB or more; Graf-Id stays under 200 KB. Graf-Id **never changes this envelope** — anything richer goes into `graf_id`. Empty values are omitted rather than written as placeholders.

### The `graf_id` extension (Graf-Id-owned)

Present in the **JSON** export only. `extension_version` is `1`; changes are additive. Contents: `exported_at`, `app_version`, and the blocks `project`, `continuity`, `git`, `context` (empty values omitted). Consumers must ignore unknown fields.

---

## Export all projects (inbox)

Settings → Data → **Export all projects…** asks for a folder and writes:

```
<folder>/
├── manifest.json
├── README.md
└── projects/<project-slug>.json     one lean GrafiTalk handoff per project
```

`manifest.json` lists `manifest_version`, `app`, `app_version`, `exported_at`, `handoff_schema_version`, `project_count` and, per project, `name`, `file` (relative) and `headline`. It contains **no absolute paths and no database ids**.

CLI: `graf-id export-grafitalk [--out <folder>]`. Without `--out` (or `GRAFID_GRAFITALK_DIR`) the folder is `<Graf-Id data folder>/grafitalk-inbox`.

---

## Import context

**Import context…** in the project header reads a handoff `.json` (GrafiTalk-compatible v0.1, with or without `graf_id`) and can write **only into that project's notes**.

1. Pick a file. It must be a regular `.json` file within 256 KB; the size is checked before it is read.
2. Graf-Id validates it (source, `schema_version`, types, list caps) and shows a **preview**: the exact text that would be saved, warnings (for example the file names a different project), ignored keys, and how many listed files are not imported.
3. You choose **Add below my existing notes** (default) or **Replace my existing notes** (with an explicit warning), then confirm.
4. The write happens in one transaction and is refused if the notes changed since the preview.

Nothing is written before step 3. The import never creates projects, never touches settings, editor paths or coding agents, and never applies file lists or the `graf_id` block; there is no new database schema.

---

## Backup and restore

**Create backup…** writes one `.zip`:

```
graf-id-backup.zip
├── grafid-export.json   manifest (spec_version, schema_version, exported_at, app, project_count)
├── graf-id.db           consistent SQLite snapshot (online backup API)
└── README.md
```

Settings are **not** included unless you ask (`graf-id export <file> --include-settings`).

**Restore from backup…** treats the archive as untrusted and only touches your data at the very end:

1. Validate the archive: allowlisted member names only (no traversal), a per-member and total size cap, a compression-ratio limit (zip-bomb guard), and a byte cap enforced while streaming.
2. Extract the database to a **temporary** file; run `PRAGMA integrity_check`; refuse a database whose schema is newer than this Graf-Id.
3. Migrate the **temporary copy** to the current schema.
4. Take a **safety backup** of your current database with SQLite's backup API into `<data folder>/backups/`.
5. Replace the live database with one atomic `os.replace`; stale `-wal` / `-shm` / `-journal` files are cleaned.

A failure at any step before 5 leaves your live database untouched. The desktop app reloads after a restore.

**Settings during restore.** `config.json` is never overwritten by default. With `--restore-settings` (CLI) only an allowlist is merged: `log_level`, `usage_journal`, `debug_timing`, `compact_mode`, `default_project_opener`. Editor paths, interpreter paths, coding agents and executable overrides are never restored; an agent or custom opener is reset to `system`.

CLI: `graf-id export <file.zip> [--include-settings]`, `graf-id import <file.zip> [--replace] [--restore-settings]`. An existing database is only replaced with `--replace`.

---

## Safety summary

- Exported file lists contain project-relative paths only. Absolute paths, `..`, drive letters, secret-looking names (`.env*`, `*.pem`, `id_rsa*`, …) and virtualenv / ignored trees are dropped.
- Workflow documents found in a **parent** folder appear in the UI for convenience but are never exported.
- No export contains database ids or absolute user paths (the JSON `graf_id.project` block has no `path`).
- Import and restore rules are described in [SECURITY.md](../SECURITY.md).

Related: [GRAFITALK_INTEGRATION.md](GRAFITALK_INTEGRATION.md), [grafid-export-spec.md](grafid-export-spec.md).
