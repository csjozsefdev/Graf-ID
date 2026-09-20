# Usage observation log (personal dogfooding)

English-only. **Local-only** — nothing leaves your machine.

## Purpose

During real daily usage, capture signals that help answer:

> How quickly and calmly can I reconnect to my previous mental context?

This is not analytics or telemetry. It is a private append-only journal for you.

## Enable observation

**Option A — config** (`config.json` in your Graf-Id data folder):

```json
{
  "log_level": "INFO",
  "usage_journal": true,
  "debug_timing": false
}
```

**Option B — environment** (session only):

```powershell
$env:GRAFID_USAGE_JOURNAL = "1"
$env:GRAFID_DEBUG_TIMING = "1"
```

## What gets recorded

| Event | When |
|-------|------|
| `ipc.bootstrap` | Desktop or IPC startup |
| `session.close` | Session closed |
| `session.close_skip_notes` | Closed with `--skip-notes` |
| `cli.scan` | Project scan completed |

File location: `%LOCALAPPDATA%\Graf-Id\logs\usage_journal.jsonl`

## Review your patterns

```powershell
graf-id usage status
graf-id usage summary
graf-id ipc usage-insights
```

`friction_hints` are heuristic suggestions (e.g. many dismissals, frequent skip-notes).

## Debug timing

When `debug_timing` is true or `GRAFID_DEBUG_TIMING=1`:

- Bootstrap IPC includes `debug_timings` (milliseconds per step)
- `graf-id scan` prints timing lines to stderr
- DEBUG log lines from the `grafid.timing` logger

## Manual observation template

Copy into your notes weekly:

### Week of YYYY-MM-DD

**Calm reconnect wins**

- 

**Friction (what slowed me down)**

- 

**Repeated manual actions**

- 

**Summaries I ignored / dismissed quickly**

- 

**Exit notes I skipped**

- 

**Missing continuity signals**

- 

**Future automation (only if pain repeats 3+ times)**

- 

## Principles

- Do not optimize from one bad day.
- Prefer calmer copy over more features.
- If a hint appears often in the journal, fix UX before adding automation.
