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
decision_needed: false
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — anchor references populated from codebase analysis:_

- **Step 1 (schema migration).** Append a new SQL block to `_MIGRATIONS` in
  `scripts/little_loops/session_store.py:208-545` (mirroring the v18
  `test_run_events` block at lines 521-544). `SCHEMA_VERSION = 18` lives at
  `session_store.py:102`. The `_apply_migrations()` runner at lines 609-645
  applies each block inside a `BEGIN IMMEDIATE` transaction, splits statements
  via `_split_sql_statements()`, and updates the `meta.schema_version` row
  automatically — no manual bookkeeping needed.
- **Step 2 (kinds).** `_VALID_KINDS` at `session_store.py:104-118` and
  `_KIND_TABLE` at `session_store.py:119-130`. Note: `"snapshot"` already maps
  to `issue_snapshots` in `_KIND_TABLE`; the new `"config"` entry must not
  collide with that name.
- **Step 3 (`record_config_snapshot`).** Two model functions to follow in order:
  - `record_commit_event()` at `session_store.py:1041-1091` — signature shape,
    `try/finally conn.close()`, `_index()` only when `cursor.rowcount` is
    truthy, optional `config` analytics-gate stub.
  - `record_issue_snapshot()` at `session_store.py:816-866` — `INSERT OR IGNORE`
    on a `(issue_id, transition)` UNIQUE index for idempotency.

  Use `_hash_args(value)` at `session_store.py:1439-1445` as the canonical
  (sorted-keys) JSON + SHA-256 helper, or mirror its body inline if a longer
  digest than 16 hex chars is desired (config-fingerprinting only has 64 bits
  of entropy at the 16-char slice — bumping to full 64-char SHA-256 is cheap).

  Hash-gating: instead of `INSERT OR IGNORE`, do an explicit
  `SELECT config_hash FROM config_snapshots ORDER BY id DESC LIMIT 1` before
  inserting; if equal to the computed hash, return early without writing. This
  is what makes the function safe to call unconditionally from `session_start`.

  FTS indexing: `_index(conn, content=json.dumps(merged_config, sort_keys=True),
  kind="config", ref=config_hash, anchor=source, ts=ts)` so `ll-session search
  --fts "<key>" --kind config` works.
- **Step 4 (session_start wiring).** Inject the call at
  `scripts/little_loops/hooks/session_start.py:111-118` — after the
  `merged_config = deep_merge(...)` step at line 111 and before the
  `if config_path is not None:` block at line 118 closes. Use the existing
  `contextlib.suppress(Exception)` pattern (precedent at lines 119, 137, 170).
  Pass `source="session_start"` and `session_id=None` (the hook payload's
  session_id is host-specific and not safely typed here).
- **Step 5 (configure write path).** Defer — `skills/configure/SKILL.md` has no
  Python write path today. See Integration Map → "Out of Scope / Optional".
- **Step 6 (read API).** `recent_commit_events()` at
  `scripts/little_loops/history_reader.py:524-559` is the closest typed-reader
  model. `_connect_readonly()` at line 235 returns `None` for missing/locked
  DBs; check the return value and short-circuit with `[]` for graceful
  degradation. Add a `ConfigSnapshot` dataclass near `CommitEvent` (line 124)
  and `RunEvent` (line 138).
- **Step 7 (CLI).** Both `search_parser` (`session.py:88-110`) and
  `recent_parser` (`session.py:112-141`) carry hardcoded `choices=[...]` lists
  that must be extended. Once added, `recent()` at `session_store.py:1268-1289`
  and the dispatcher at `cli/session.py:386-424` need no other change.
- **Step 8 (tests).** Place new test classes in
  `scripts/tests/test_session_store.py` next to `TestRecordCommitEvent`
  (line 3416-3464) and `TestRecordTestRunEvent` (line 3549+). Cover: roundtrip
  write→read, FTS-searchable (`search(db, query="<key>")` returns a
  `kind="config"` hit), hash-gated no-op on identical config, hash-stable
  across key reorder, `config_at(ts)` returns the latest snapshot with
  `ts <= given`, and graceful degradation when the DB path is read-only or
  parent directory is missing. Optionally add a mock-based test in
  `scripts/tests/test_hook_session_start.py` confirming the session_start
  handler calls `record_config_snapshot` post-merge.
- **Step 9 (docs).** `docs/ARCHITECTURE.md:612-635` schema table (add v19 row);
  `docs/reference/API.md:6975-6984` (import listing), `:7005-7048` (function
  section), `:7081-7091` (per-table schema block); `docs/reference/CLI.md:2208,
  2264` (mention `--kind config`); `docs/guides/HISTORY_SESSION_GUIDE.md:45`
  (bump stated schema version from 14 to 19) and `:49-60+` (add a
  "when was my config last flipped?" query recipe).

## Sources

- `thoughts/history-db-expand-wiring.md` — §2 (uncaptured surfaces)
- EPIC-2457 review (2026-07-05) — item #6
- `scripts/little_loops/hooks/session_start` — config load/merge site
- `config-schema.json` — merged-config shape
- `.claude/CLAUDE.md` § Local Settings Override — merge semantics (deep merge)

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py:102` — bump `SCHEMA_VERSION` from 18 to 19.
- `scripts/little_loops/session_store.py:208-545` — append the v19 migration SQL block to `_MIGRATIONS` (the existing `_apply_migrations()` runner handles commit + `meta.schema_version` update automatically).
- `scripts/little_loops/session_store.py:104-118` — add `"config"` to `_VALID_KINDS`.
- `scripts/little_loops/session_store.py:119-130` — add `"config": "config_snapshots"` to `_KIND_TABLE` (this is what `recent()` consults at line 1268).
- `scripts/little_loops/session_store.py:60-87` — add `record_config_snapshot` to `__all__`.
- `scripts/little_loops/session_store.py` — implement `record_config_snapshot()`. Model after `record_commit_event()` at lines 1041-1091 (signature, `try/finally conn.close()`, `_index()` only-on-insert). Use `_hash_args()` at lines 1439-1445 for the canonical (sorted-keys) JSON + SHA-256 hash.
- `scripts/little_loops/hooks/session_start.py:75-117` — after the `merged_config = deep_merge(...)` step at line 111, inside the existing `if config_path is not None:` block at line 118, call `record_config_snapshot(db, config=merged_config, source="session_start")` wrapped in the existing `contextlib.suppress(Exception)` pattern (precedent at lines 119, 137, 170).
- `scripts/little_loops/cli/session.py:90-106` — add `"config"` to `search_parser` `--kind` `choices` list.
- `scripts/little_loops/cli/session.py:113-129` — add `"config"` to `recent_parser` `--kind` `choices` list (the dispatcher at lines 386-424 needs no other change).
- `scripts/little_loops/history_reader.py:524-559` — model `recent_config_snapshots()` and `config_at()` after `recent_commit_events()`; add a `ConfigSnapshot` dataclass alongside `CommitEvent` (line 124) and `RunEvent` (line 138).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py:386-424` — `recent` handler routes via `recent()` (`session_store.py:1268`) → `_KIND_TABLE[kind]`; once `"config"` is in the map, `ll-session recent --kind config` works end-to-end with no other change.
- `scripts/little_loops/history_reader.py:332-367` `search()` — already filters `WHERE kind = ?` against the FTS table; `ll-session search --fts "<key>" --kind config` works automatically once `record_config_snapshot` writes FTS rows with `kind="config"`.

### Similar Patterns
- `scripts/little_loops/session_store.py:1041-1091` `record_commit_event()` — closest model (signature shape, `INSERT OR IGNORE` on UNIQUE, `_index()` only when `cursor.rowcount` is truthy, `try/finally conn.close()`, optional `config` analytics-gate stub).
- `scripts/little_loops/session_store.py:816-866` `record_issue_snapshot()` — alternative `INSERT OR IGNORE` pattern keyed on `(issue_id, transition)` UNIQUE.
- `scripts/little_loops/session_store.py:1439-1445` `_hash_args()` — canonical-JSON + SHA-256 helper to reuse (or to mirror) for `config_hash`.
- `scripts/little_loops/session_store.py:1268-1289` `recent()` — `kind` → table lookup via `_KIND_TABLE`; works automatically with the new `"config"` entry.
- `scripts/little_loops/hooks/post_commit.py` — analogous "side-effect hook → `record_*` function" wiring (ENH-2458); template for the `session_start` integration.
- `scripts/little_loops/history_reader.py:524-559` `recent_commit_events()` — model for `recent_config_snapshots()` typed read API.

### Tests
- `scripts/tests/test_session_store.py:3416-3464` `TestRecordCommitEvent` — closest test class analog (roundtrip + dedupe-on-sha + FTS-searchable).
- `scripts/tests/test_session_store.py:2942-3012` `TestRecordIssueSnapshot` — model for `TestRecordConfigSnapshot` (roundtrip + FTS-indexed + idempotent `INSERT OR IGNORE` + missing-file no-op).
- New tests to add alongside the existing `TestRecordCommitEvent` / `TestRecordTestRunEvent` blocks: `TestRecordConfigSnapshot`, `TestConfigHashStability` (key-reorder invariance), `TestConfigAt` (timestamp lookup), and a graceful-degradation test (DB missing/locked → no exception).
- `scripts/tests/test_hook_session_start.py` already exercises the merge path at lines 34-160; add a test there that asserts `record_config_snapshot` is called post-merge (mock the record function).

### Documentation
- `docs/ARCHITECTURE.md:612-635` — add a `| v19 | config_snapshots | ... |` row to the schema versions table.
- `docs/reference/API.md:6975-6984` — add `record_config_snapshot` to the `session_store.__all__` import listing.
- `docs/reference/API.md:7005-7048` — add a `### record_config_snapshot` section after `record_commit_event`.
- `docs/reference/API.md:7081-7091` — add a `### config_snapshots table (v19, ENH-2496)` schema block mirroring the `correction_retirements` block.
- `docs/reference/CLI.md:2208, 2264` — mention `--kind config` alongside the existing `--kind commit` / `--kind test_run` references.
- `docs/guides/HISTORY_SESSION_GUIDE.md:49-60+` — update the `## What Gets Recorded` table (current schema version stated as 14 at line 45, needs bumping to 19); add a "when was my config last flipped?" query recipe.

### Configuration
- `config-schema.json` — the JSON Schema for the merged config being snapshotted; no schema change is needed for this ENH.
- `.ll/ll-config.json` + `.ll/ll.local.md` — the on-disk sources the merged snapshot consumes (read-only for this ENH).

### Out of Scope / Optional
- `/ll:configure` write-path wiring (`source="configure"`) is **optional** per the issue spec. `skills/configure/SKILL.md` is LLM-driven and edits `.ll/ll-config.json` directly via the `Edit` tool — there is no Python write path to hook today. The only programmatic writer is `ll-init`'s `write_config()` at `scripts/little_loops/init/writers.py:148`, which could be hooked for an `ll-init`-initiated snapshot. A future PostToolUse hook on `.ll/ll-config.json` edits is a clean way to wire `source="configure"`; defer to a follow-on.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `config-schema.json` | Config shape being snapshotted |

## Status

**Open** | Created: 2026-07-05 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-07-07T01:10:17 - `0e87c489-48ca-489b-8c2a-14ba92f190fd.jsonl`
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
