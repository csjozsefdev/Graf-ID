# GrafiTalk integration

How Graf-Id shares project context with **GrafiTalk** without coupling databases or live services. Format details live in [EXPORT_IMPORT.md](EXPORT_IMPORT.md); this page is the integration view.

---

## Principle

| Rule | Detail |
|------|--------|
| Graf-Id **exports** | Writes read-only JSON handoff files |
| GrafiTalk **consumes** | Imports those files in its Context panel |
| **No direct DB coupling** | GrafiTalk never opens `graf-id.db` |
| **No live bus** | Re-export when you want fresh context |
| **GrafiTalk owns the contract** | Flat `schema_version: "0.1"`; Graf-Id never changes it |

GrafiTalk is a **separate project**. Do not merge repos or share SQLite schemas. The contract is defined by GrafiTalk (`docs/GRAF_ID_EXPORT_SCHEMA.md` in its repo).

---

## Flow

```
Graf-Id  →  Refresh context  →  ProjectContext (backend)
                                    │
             ┌──────────────────────┼─────────────────────┐
             ▼                      ▼                     ▼
   Export → GrafiTalk handoff   Export → JSON      Export all projects…
   (lean, flat v0.1)            (v0.1 + graf_id)   (folder of handoffs + manifest)
             │
             ▼
   GrafiTalk → Context panel → Import
```

Use **Refresh context** first so the handoff reflects the latest git state and documents.

---

## What GrafiTalk receives

A handoff file has `source: "graf-id"`, `schema_version: "0.1"`, `project_name`, and — only when Graf-Id has something reliable to say — `current_status`, `changes`, `blockers`, `next_steps`, `estimated_time`, `notes` and `files`.

- **`changes`** are recent fixes/improvements taken from trusted commit subjects (`fix:`, `feat(scope):`, imperative verbs) — not from scanner markers.
- **`files`** are project-relative and capped; secret-looking names and virtualenv trees are excluded.
- A project with no exit note and no handoff document therefore produces a deliberately thin file rather than invented prose.

The full **JSON** export adds the `graf_id` extension (`extension_version: 1`) with structured continuity, git and context. GrafiTalk ignores it; other tools may use it.

---

## Inbox (all projects)

Settings → Data → **Export all projects…**, or:

```powershell
graf-id export-grafitalk
graf-id export-grafitalk --out D:\GrafiTalk\inbox
graf-id grafitalk status
```

Default folder: `<Graf-Id data folder>/grafitalk-inbox` (override with `--out` or `GRAFID_GRAFITALK_DIR`).

```
grafitalk-inbox/
├── manifest.json
├── README.md
└── projects/<project-slug>.json
```

Manifest example (no absolute paths, no ids):

```json
{
  "manifest_version": 1,
  "app": "Graf-Id",
  "app_version": "1.0.0",
  "exported_at": "2026-09-19T20:00:00+00:00",
  "handoff_schema_version": "0.1",
  "project_count": 1,
  "projects": [
    { "name": "my-app", "file": "projects/my-app.json", "headline": "Checkout flow done" }
  ]
}
```

---

## Coming back the other way

**Import context…** takes a handoff file into a project's notes after a validated preview and explicit confirmation. See [EXPORT_IMPORT.md](EXPORT_IMPORT.md#import-context).

---

## Backup is separate

The zip backup (Settings → Data → **Create backup…**) is for migration and disaster recovery, not for GrafiTalk. See [grafid-export-spec.md](grafid-export-spec.md).

---

## Integration status

| Item | Status |
|------|--------|
| Named exports (handoff / JSON / Markdown / TXT) | **Implemented** |
| Export all projects (Settings and `export-grafitalk`) | **Implemented** |
| Context import into project notes | **Implemented** |
| Compatibility with the v0.1 contract | **Verified in tests** (an independent oracle in `grafid/tests/grafitalk_contract.py`) |
| GrafiTalk auto-watch | Not in Graf-Id (GrafiTalk's responsibility) |
| Live sync | Out of scope |

---

## Related docs

- [EXPORT_IMPORT.md](EXPORT_IMPORT.md) — formats, import, backup and restore
- [grafid-export-spec.md](grafid-export-spec.md) — zip backup bundle
- [grafitalk-inbox.md](grafitalk-inbox.md) — inbox folder quick reference
- [DECISIONS.md](DECISIONS.md) — why file-based export
