---
id: ENH-2496
title: Config-change audit trail (.ll/ll-config.json) in history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-05
captured_at: "2026-07-05T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - config
  - captured
---

# ENH-2496: Config-change audit trail (.ll/ll-config.json) in history.db

## Summary

`.ll/ll-config.json` (and the `ll.local.md` override) shapes almost every
behavior in this project — analytics gating, scan focus dirs, context-handoff
threshold, TDD mode, loop run defaults — yet the DB has **no record of what the
config was when a run happened, or when it changed.** Only the file mtime exists.
"Which config produced last week's automation results?" and "when did we flip
`tdd_mode`?" are unanswerable. Add lightweight config snapshots: at `session_start`
compute a stable hash of the effective merged config and, when it differs from the
last recorded hash, write a `config_snapshots` row (hash + full JSON). This makes
every downstream signal (ENH-2492 orchestration, ENH-2493 harness) attributable to
a known configuration.

## Motivation

- **Reproducibility gap.** Batch/eval outcomes are only interpretable against the
  config that produced them; without a snapshot, historical results are ambiguous.
- **Change detection.** Flipping `tdd_mode`, `context_monitor.auto_handoff_threshold`,
  or `analytics.capture.*` silently changes behavior; an audit trail makes those
  inflection points visible when reviewing a trend.
- **Cheap and low-frequency.** Config rarely changes; hash-gated snapshotting adds
  at most one small row per config change, not per session.

## Current Behavior

- `session_start` loads and merges `.ll/ll-config.json` + `ll.local.md` but does
  not record a hash or snapshot.
- `/ll:configure` edits the file; no event is written.
- The only historical signal is the file's mtime, which is overwritten and not
  captured in the DB.
- No `--kind config` in `ll-session`.

## Expected Behavior

- At `session_start`, the effective merged config is hashed; if the hash differs
  from the most recent `config_snapshots` row, a new snapshot (hash + JSON +
  session_id) is written. Identical configs write nothing (hash-gated).
- `ll-session recent --kind config` returns the snapshot history;
  `ll-session search --fts "<key>" --kind config` matches values.
- Optionally `/ll:configure` writes a snapshot immediately after an edit so the
  change is attributed to that action rather than the next session.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS config_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    config_hash TEXT NOT NULL,   -- stable hash of merged effective config
    session_id TEXT,
    source TEXT,                 -- "session_start" | "configure"
    config_json TEXT,            -- full merged config at snapshot time
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_config_hash ON config_snapshots(config_hash);
```

Bump `SCHEMA_VERSION`. Add `"config"` to `_VALID_KINDS` and
`"config": "config_snapshots"` to `_KIND_TABLE`.

### Producer wiring

- Add `record_config_snapshot(db_path, *, ts, config_hash, session_id=None,
  source="session_start", config_json=None, head_sha=None, branch=None)` to
  `session_store.py`. Internally it reads the last snapshot's `config_hash` and
  **no-ops when unchanged** (hash-gated), so callers can invoke it unconditionally.
  Best-effort guarded. FTS-index the JSON body (`kind="config"`).
- Compute the hash with a canonical (sorted-keys) JSON serialization of the merged
  config so key ordering doesn't produce spurious snapshots.
- Wire the `session_start` Python hook handler
  (`scripts/little_loops/hooks/session_start`) to call it after config load/merge.
- Optionally wire `/ll:configure` (or its `ll-*` write path) to call it with
  `source="configure"` right after it writes the file.

### Read API

- `history_reader.recent_config_snapshots(since=None, limit=20)`.
- `history_reader.config_at(ts)` — the effective config in force at a timestamp
  (latest snapshot with `ts <=` given), for attributing a run to its config.

### CLI surface

- `ll-session recent --kind config`.

## Acceptance Criteria

- Schema migration lands; `config_snapshots` exists; `SCHEMA_VERSION` bumped.
- First `session_start` after this ships writes one snapshot; a subsequent
  `session_start` with unchanged config writes **no** new row (hash-gated).
- Editing `.ll/ll-config.json` (e.g. flip `tdd_mode`) and starting a session
  writes a new snapshot whose `config_json` reflects the change.
- Hash is order-insensitive (reordering keys does not create a snapshot).
- Writes are best-effort: DB absent/locked never blocks session start.
- `ll-session recent --kind config` returns rows; `config_at(ts)` returns the
  correct snapshot.
- Tests cover: first snapshot, unchanged no-op, changed value, key-reorder
  stability, `config_at` lookup, graceful degradation.

## Implementation Steps

1. Schema migration for `config_snapshots`; bump `SCHEMA_VERSION`.
2. Add `"config"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_config_snapshot()` (hash-gated no-op, canonical hashing) in
   `session_store.py`; export.
4. Wire the `session_start` hook handler to call it post-merge.
5. Optionally wire `/ll:configure` write path with `source="configure"`.
6. `history_reader.recent_config_snapshots()` + `config_at()`.
7. CLI: `ll-session recent --kind config`.
8. Tests: `TestRecordConfigSnapshot`, `TestConfigHashStability`,
   `TestConfigSchema`, `TestConfigAt`, graceful degradation.
9. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md`,
   `docs/reference/CLI.md`.

## Sources

- `thoughts/history-db-expand-wiring.md` — §2 (uncaptured surfaces)
- EPIC-2457 review (2026-07-05) — item #6
- `scripts/little_loops/hooks/session_start` — config load/merge site
- `config-schema.json` — merged-config shape
- `.claude/CLAUDE.md` § Local Settings Override — merge semantics (deep merge)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `config-schema.json` | Config shape being snapshotted |

## Status

**Open** | Created: 2026-07-05 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
