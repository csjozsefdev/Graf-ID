# GrafiTalk inbox (Graf-Id export)

A read-only folder with one GrafiTalk-compatible handoff per project. No cloud sync, no live bus. Full description: [GRAFITALK_INTEGRATION.md](GRAFITALK_INTEGRATION.md) and [EXPORT_IMPORT.md](EXPORT_IMPORT.md).

## Create it

- Desktop: **Settings → Data → Export all projects…** and pick a folder.
- CLI:

```powershell
graf-id export-grafitalk
graf-id export-grafitalk --out D:\GrafiTalk\inbox
graf-id grafitalk status
```

Default folder: `<Graf-Id data folder>/grafitalk-inbox` (typically `%LOCALAPPDATA%\Graf-Id\grafitalk-inbox`). Override with `--out` or the `GRAFID_GRAFITALK_DIR` environment variable.

Run **Refresh context** first so the files reflect current git state and documents.

## Layout

```
grafitalk-inbox/
├── README.md
├── manifest.json
└── projects/
    ├── my-app.json
    └── other-project.json
```

## Per-project file

Flat GrafiTalk contract **v0.1**: `source: "graf-id"`, `schema_version: "0.1"`, `project_name`, plus the optional `current_status`, `changes`, `blockers`, `next_steps`, `estimated_time`, `notes`, `files`. Empty values are omitted. Import it in GrafiTalk's Context panel.

## Manifest

`manifest_version`, `app`, `app_version`, `exported_at`, `handoff_schema_version`, `project_count` and a `projects[]` list of `name`, `file` (relative to the manifest) and `headline`. There are **no absolute paths and no database ids** in the manifest or the files.

## Notes for consumers

- Treat files as read-only input; Graf-Id owns the database.
- Match projects by `project_name`, not by a path.
- Ignore unknown keys; files stay under 200 KB.
- Re-export when fresh context is needed (Graf-Id runs no file watcher).

For the zip backup used for migration, see [grafid-export-spec.md](grafid-export-spec.md).
