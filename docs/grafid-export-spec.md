# grafid-export.json (backup bundle, spec v1)

The zip backup used for migration and disaster recovery. For the per-project handoff formats see [EXPORT_IMPORT.md](EXPORT_IMPORT.md) and [grafitalk-inbox.md](grafitalk-inbox.md).

## Bundle layout

```
export.zip
├── grafid-export.json   # manifest
├── graf-id.db           # consistent SQLite snapshot (online backup API)
├── config.json          # OPTIONAL — only with --include-settings, harmless allowlist only
└── README.md            # human instructions
```

Settings are excluded by default. No other member names are accepted on restore.

## Manifest fields

| Field | Type | Description |
|-------|------|-------------|
| `spec_version` | int | Bundle format version (currently `1`) |
| `schema_version` | int | SQLite schema version at export time |
| `exported_at` | ISO-8601 | UTC timestamp |
| `app` | string | Always `"Graf-Id"` |
| `app_version` | string | Graf-Id version that wrote the bundle |
| `project_count` | int | Number of registered projects |

## Restore rules

Restore verifies before it replaces: allowlisted members, per-member/total size caps, compression-ratio limit, streaming byte cap, `PRAGMA integrity_check`, schema not newer than the running app, migration on a temporary copy, a safety backup of the current database in `<data folder>/backups/`, and one atomic file replace. Any earlier failure leaves the live database untouched.

`config.json` is never overwritten by default. With `--restore-settings` only `log_level`, `usage_journal`, `debug_timing`, `compact_mode` and `default_project_opener` are merged; editor paths, coding agents and executable overrides are never restored.

## Desktop and CLI

- Settings → Data → **Create backup…** / **Restore from backup…**
- `graf-id export <path.zip> [--include-settings]`
- `graf-id import <path.zip> [--replace] [--restore-settings]` — an existing database is only replaced with `--replace`
- `graf-id maintenance vacuum` — SQLite VACUUM
- `graf-id maintenance prune-snapshots` — apply retention policy

## Coupling

Consumers should treat the bundle as **read-only input**. No shared auth, cloud sync, or live bus.
