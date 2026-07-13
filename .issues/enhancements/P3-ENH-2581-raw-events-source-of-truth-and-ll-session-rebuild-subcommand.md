---
id: ENH-2581
title: raw_events source of truth and ll-session rebuild subcommand
type: ENH
priority: P3
status: done
discovered_date: 2026-07-08
captured_at: '2026-07-08T00:00:00Z'
completed_at: '2026-07-13T01:39:45Z'
discovered_by: capture-issue
parent: EPIC-2457
relates_to:
- ENH-2461
blocks:
- ENH-2461
- ENH-2493
- ENH-2494
- ENH-2506
- ENH-2507
- ENH-2511
- ENH-2580
- ENH-2582
labels:
- enhancement
- history-db
- schema
- captured
schema_version_owner: 19
confidence_score: 98
outcome_confidence: 75
score_complexity: 15
score_test_coverage: 23
score_ambiguity: 23
score_change_surface: 14
---

# ENH-2581: raw_events source of truth and ll-session rebuild subcommand

## Summary

Introduce a new `raw_events` table (schema v19) that holds the
verbatim JSONL line per captured event plus the parsed fields as
columns. All 13+ existing cache tables (the 4 `_PRUNABLE_TABLES`
plus 9 more) become rebuildable from `raw_events`. `backfill()`
splits into two operations with crisp semantics: `ll-session
backfill` (ingest, writes to `raw_events` only) and a new
`ll-session rebuild` (materialize, wipes + re-derives the cache
tables from `raw_events`). `prune()` splits into `ll-session
compact` (lifecycle: summarize-and-mark) plus `ll-session prune`
(lifecycle: delete-and-VACUUM, now operating on `raw_events` only).
The per-table watermark scheme (`last_backfill_ts` +
`last_backfill_ts_assistant_messages` +
`last_backfill_ts_skill_events`) collapses to a single
`last_raw_event_ts` key. The `_VALID_KINDS` constant becomes the
single source of truth for the CLI `--kind` choices (the hardcoded
argparse lists in `cli/session.py:90-106` and `113-129`, which are
already missing `"snapshot"`, get replaced).

This is the structural foundation that ENH-2580 (user-root
backfill) and ENH-2582 (analytics.auto_collect runner) build on,
and which makes the pending EPIC-2457 children
(ENH-2461, 2493, 2494, 2506, 2507, 2511) "write a new event_type
parser" tasks instead of "add a new `*_events` table per feature"
tasks.

## Motivation

Three concrete wins over the current architecture:

1. **One source of truth, one watermark.** The current
   `backfill_incremental()` at `session_store.py:2497-2605` uses
   three watermark keys (`last_backfill_ts`,
   `last_backfill_ts_assistant_messages`,
   `last_backfill_ts_skill_events`) each with its own self-heal
   path. The complexity exists only because the JSONL parsers
   are called directly. Routing all ingest through
   `raw_events.INSERT OR IGNORE ON (source_path, line_no)` makes
   the watermark a single key.

2. **Parser change → re-derive, not migrate.** Today, adding a
   new field to a `tool_events` row (e.g. the
   `agent_type` discriminator from ENH-2497, or the MCP
   telemetry columns from ENH-2511) requires an `ALTER TABLE`
   migration. In the new world, the parser change + `rebuild()`
   covers it. The schema only needs a new column when the
   *query* needs a new column, not when the *ingest* does.

3. **FTS5 leak fixed for free.** `prune()` at
   `session_store.py:2612-2727` deletes from
   `_PRUNABLE_TABLES` but never from `search_index`. Stale FTS
   rows point at deleted event rows (confirmed: zero
   `reindex_fts` / `INSERT INTO search_index(search_index)
   VALUES('rebuild')` matches in the tree). `rebuild()` always
   wipes + re-populates `search_index`, and the lifecycle
   order is `rebuild → compact → prune`, so FTS state is
   always consistent with cache state.

## Current Behavior

- `backfill()` at `session_store.py:2441-2494` calls 9
  `_backfill_*` functions + 2 derivation functions
  (`mine_corrections_from_messages` and `_compact_sessions`) in
  sequence, fusing ingest with materialization.
- `backfill_incremental()` at `session_store.py:2497-2605` is
  the JSONL-only incremental variant called from the
  `SessionStart` subprocess. Three watermark keys, each with
  self-heal logic.
- `prune()` at `session_store.py:2612-2727` deletes from
  `_PRUNABLE_TABLES = ("tool_events", "cli_events",
  "file_events", "message_events")` (line 2609) based on
  `analytics.retention.raw_event_max_age_days` (default 90).
  Dual-gated by `min_project_age_days >= 365` AND
  `min_db_size_mb >= 800`. Never calls
  `_compact_sessions`. Never touches `search_index`. VACUUM
  on a separate connection at lines 2713-2725.
- `_VALID_KINDS` at `session_store.py:104-118` is a
  `frozenset` of 11 entries, consumed only by `recent()` at
  `session_store.py:1278-1279`. The argparse `--kind` choices
  in `cli/session.py:90-106` and `113-129` are duplicated
  hardcoded lists, missing `"snapshot"`.
- Several `_backfill_*` functions
  (`_backfill_loops`, `_backfill_tool_events`,
  `_backfill_messages`, `_backfill_skill_events`) use plain
  `INSERT` (no `INSERT OR IGNORE`) — duplicate-prone on
  repeat backfill.

## Expected Behavior

Three top-level operations with crisp semantics:

- **`ll-session backfill` (ingest)** — reads on-disk sources
  (`.issues/`, `.loops/`, JSONL, `git log`), writes to
  `raw_events` only. Updates `last_raw_event_ts`. Idempotent
  via `INSERT OR IGNORE` on `(source_path, line_no)`. **Does
  not** touch the cache tables.

- **`ll-session rebuild` (materialize)** — wipes the 13 cache
  tables + `search_index`, re-derives them from `raw_events`.
  Calls the 9 `_backfill_*` functions (refactored to accept a
  `raw_events_cursor` instead of a JSONL list). Calls
  `mine_corrections_from_messages` and `_compact_sessions` at
  the end. Idempotent. Updates `last_rebuild_version` meta
  key.

- **`ll-session compact` (lifecycle: summarize)** — sweeps
  `raw_events` older than
  `analytics.retention.raw_event_max_age_days`, generates
  `summary_nodes` for them (per-session grouping, FEAT-1712
  style), marks the rows `compacted=1`.

- **`ll-session prune` (lifecycle: delete)** — deletes
  `raw_events` rows where `compacted=1` + VACUUM. Has
  `--dry-run`. **No derivation; no FTS mutation** (FTS is
  already correct because `rebuild` ran before this in any
  sane flow).

- **`ll-session compact --and-prune`** — combined.

The FTS5 leak disappears because `rebuild` always wipes +
re-populates `search_index` from the cache tables. The
lifecycle order `rebuild → compact → prune` is enforced by
`SessionStart` (calls `backfill` then optionally `rebuild` on
`SCHEMA_VERSION` change) and `SessionEnd` (calls
`compact --and-prune` if `analytics.auto_collect.enabled`,
per ENH-2582).

## Proposed Solution

### 1. Schema migration (v19)

Append to `_MIGRATIONS` in `session_store.py`, modeled on
the v17 `commit_events` migration (`session_store.py:501-520`):

```sql
CREATE TABLE IF NOT EXISTS raw_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    session_id  TEXT,
    host        TEXT NOT NULL,
    source_path TEXT NOT NULL,
    line_no     INTEGER NOT NULL,
    event_type  TEXT NOT NULL,
    raw_line    TEXT NOT NULL,
    parsed_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_events_dedup
    ON raw_events(source_path, line_no);
CREATE INDEX IF NOT EXISTS idx_raw_events_session_ts
    ON raw_events(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_raw_events_host_ts
    ON raw_events(host, ts);

-- For the compact/prune lifecycle.
ALTER TABLE raw_events ADD COLUMN compacted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE raw_events ADD COLUMN summary_node_id INTEGER
    REFERENCES summary_nodes(id);

-- Watermark initialization.
INSERT OR IGNORE INTO meta(key, value) VALUES('last_raw_event_ts', NULL);
INSERT OR IGNORE INTO meta(key, value) VALUES('last_rebuild_version', NULL);
```

Bump `SCHEMA_VERSION` from 18 to 19.

### 2. New `backfill_raw_events()`

```python
def backfill_raw_events(
    db: Path | str,
    *,
    jsonl_files: list[Path],
    since_ts: float | None = None,
) -> int:
    """Parse JSONL files and INSERT OR IGNORE rows into raw_events.
    Returns the count of new rows inserted. Updates last_raw_event_ts.
    """
```

`backfill_incremental()` becomes a thin wrapper that calls
`backfill_raw_events` and then optionally `rebuild`. The
three watermark keys collapse to one (`last_raw_event_ts`).

### 3. New `rebuild()`

```python
def rebuild(
    db: Path | str,
    *,
    config: dict | None = None,
) -> dict[str, int]:
    """Wipe + re-derive all cache tables from raw_events. Idempotent."""
```

Steps:

1. Wipe the 13 cache tables:
   `_PRUNABLE_TABLES` (4) + `issue_events`, `loop_events`,
   `user_corrections`, `summary_nodes`, `summary_spans`,
   `assistant_messages`, `commit_events`,
   `test_run_events`, `issue_snapshots`.
2. Wipe `search_index` (`DELETE FROM search_index`).
3. Re-derive: call each of the 9 `_backfill_*` functions,
   passing a `raw_events_cursor` instead of a JSONL list.
4. Re-populate `search_index` by iterating the cache tables
   and calling `_index()` for each row.
5. Run `mine_corrections_from_messages(conn, config)` and
   `_compact_sessions(conn, config)`.
6. Update `last_rebuild_version` meta key to current
   `SCHEMA_VERSION`.

### 4. Refactor `_backfill_*` to accept either input

Each of the 9 `_backfill_*` functions is refactored to
accept either `jsonl_files: list[Path]` (legacy) or
`raw_events_cursor: sqlite3.Cursor` (new). Both produce
identical cache state. A single helper dispatches:

```python
def _iter_events(cursor_or_files):
    """Yield (parsed_dict, source_path, line_no) for each event,
    transparently from raw_events rows OR from JSONL files."""
```

The existing `_backfill_*` function bodies stay largely
unchanged; only the input-source switch is new. This keeps
parser logic in one place and means pending EPIC-2457
children (ENH-2461, 2493, 2494, 2506, 2507, 2511) become
"add a new event_type parser" tasks instead of "add a new
table per feature" tasks.

### 5. New `compact()`

```python
def compact(
    db: Path | str,
    *,
    config: dict | None = None,
    and_prune: bool = False,
) -> dict[str, int]:
    """Sweep old raw_events, generate summary_nodes, optionally prune."""
```

Steps:

1. Read `analytics.retention.raw_event_max_age_days`
   (default 90) from config.
2. `SELECT id, ts, session_id, parsed_json FROM raw_events
   WHERE ts < cutoff AND compacted = 0`.
3. Group rows by `session_id`. For each session, generate
   one `summary_nodes` row (kind='condensed', level=0) with
   `summary_spans` linking back to the raw_events rows.
4. `UPDATE raw_events SET compacted = 1, summary_node_id = ?
   WHERE id IN (...)`.
5. If `and_prune`, call `prune(db, config=config)`.

The summary_node payload is either a short LLM summary
(per-session FEAT-1712 style) or a deterministic one-liner;
the LCM Algorithm 3 escalation in `_compact_session`
(`session_store.py:2189-2341`) is the template.

### 6. Refactor `prune()` to operate on `raw_events`

Old:
```sql
DELETE FROM tool_events WHERE ts < ?;  -- ×4 tables
```

New:
```sql
DELETE FROM raw_events WHERE ts < ? AND compacted = 1;
```

The FTS5 leak disappears because `search_index` is rebuilt
by `rebuild()` and `rebuild` runs before `prune` in any
sane flow. The retention dual-gate
(`min_project_age_days >= 365` AND
`min_db_size_mb >= 800`) at lines 2676-2687 stays as-is.

### 7. CLI subcommand surface

In `scripts/little_loops/cli/session.py`:

- `backfill` subparser: **remove** `--extract-decisions`
  and `--snapshots` (subsumed by `rebuild`). **Add**
  `--rebuild` (combined mode: ingest + materialize in
  one call).
- **New** `rebuild` subparser: `--config PATH`.
- **New** `compact` subparser: `--and-prune`, `--config
  PATH`.
- `prune` subparser: unchanged from user perspective.
  `--dry-run` already there.

### 8. `_VALID_KINDS` centralization

1. Convert `_VALID_KINDS` from `frozenset` to
   `tuple[str, ...]` (argparse `choices=` requires a
   sequence, not a set).
2. `cli/session.py` imports `_VALID_KINDS` and passes it
   to both `search_parser` and `recent_parser`
   `choices=`.
3. Add a `_KIND_TABLE` consistency test that asserts
   every `_VALID_KINDS` entry has a matching
   `_KIND_TABLE` entry, except for `snapshot` (lives in
   `issue_snapshots`).
4. Add a `ll-verify-kinds` CLI check that asserts every
   `CREATE TABLE` migration has a matching `_VALID_KINDS`
   entry (catches new tables that forget to register).

### 9. `SessionStart` orchestration

`scripts/little_loops/hooks/session_start.py:150-163`
currently spawns a detached subprocess
(`subprocess.Popen([sys.executable, "-m",
"little_loops.cli.backfill_worker", str(_db_path),
_backfill_path], ...)`) that calls
`backfill_incremental()`.

Changes:

- The subprocess gains a `--rebuild` flag. The subprocess
  becomes `cli/backfill_worker.py <db_path>
  <backfill_path> [--rebuild]`.
- The hook passes `--rebuild` only when
  `SCHEMA_VERSION > last_rebuild_version` (new meta key).
- `SessionEnd` hook (NEW, owned by ENH-2582) triggers
  `compact --and-prune` if `analytics.auto_collect.enabled`
  is true.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-12). All
line-number claims elsewhere in this issue were independently re-verified
against the current file state and are accurate — `backfill()` 2441-2494,
`backfill_incremental()` 2497-2605, `prune()` 2612-2727, `_PRUNABLE_TABLES`
2609, `_VALID_KINDS`/`_KIND_TABLE` 104-130, v17 migration 501-520,
`cli/session.py` 90-106/113-129, `hooks/session_start.py` 150-163. Current
`SCHEMA_VERSION = 18` (`session_store.py:102`); `raw_events`/`rebuild()`/
`compact()`/`backfill_raw_events()` do not yet exist anywhere in the tree._

- **Migration counter nuance**: `_apply_migrations()` (`session_store.py:609-645`)
  iterates `len(_MIGRATIONS)`, not the `SCHEMA_VERSION` constant — the two
  must be bumped in lockstep manually. `_current_version()`
  (`session_store.py:592-606`) reads `meta.schema_version`, treating a
  genuinely-missing `meta` table as version 0 but re-raising any other
  `OperationalError`. The new v19 entry must be appended to `_MIGRATIONS`
  *and* `SCHEMA_VERSION` bumped to 19 as two separate edits.
- **`rebuild()` has no existing precedent in this codebase.** A grep for
  wipe-then-repopulate idioms (`rebuild`/`reindex`) found none — this would
  be the first "wipe cache tables + re-derive from a source-of-truth table"
  function in `session_store.py`. The closest structural precedents are
  `prune()`'s delete-then-VACUUM shape (`session_store.py:2612-2727`) and
  `backfill()`'s multi-step dict-of-counts return shape
  (`session_store.py:2441-2494`).
- **`_index()` (`session_store.py:705-718`) has no existing bulk/batch call
  site.** Every current caller (`write_file_event`, `record_correction`,
  `record_skill_event`, `record_commit_event`, `record_test_run_event`, etc.)
  calls it once per event, inline with the original write. `rebuild()`'s
  "iterate the cache tables and call `_index()` for each row" step (Proposed
  Solution §3.4) is genuinely new — no existing loop-and-batch-index pattern
  to copy. There is also no existing `DELETE FROM search_index` anywhere in
  the file (confirmed via grep), matching the FTS5-leak claim in Motivation
  point 3.
- **Watermark reads/writes are inlined at each call site, not a shared
  helper.** There is no `_get_meta`/`_set_meta` function — `backfill_incremental()`
  repeats the same `SELECT ... FROM meta WHERE key = ?` + ISO-timestamp-parse
  + `INSERT ... ON CONFLICT DO UPDATE` shape three times (primary key at
  `session_store.py:2527-2536`/`2597-2601`, `_ASST_KEY` at `2549-2569`,
  `_SKILL_KEY` at `2574-2594`). Collapsing to `last_raw_event_ts` removes two
  of these three inlined blocks rather than refactoring into a shared helper
  (no such helper exists to reuse).
- **`contextlib.suppress(Exception)` (EPIC-1707 contract) is a caller-side
  responsibility, not something inside `session_store.py` functions.** All
  suppress-wrapped call sites are in `hooks/session_start.py` (lines 119,
  137, 170) and `pytest_history_plugin.py` (line 120); `session_store.py`
  functions themselves raise normally. `rebuild()` and `compact()` should
  follow this same convention — raise internally, let `SessionStart`/
  `SessionEnd` hook call sites wrap them in `contextlib.suppress(Exception)`.
- **`ll-verify-kinds` (Implementation Step 11) should follow the
  `ll-verify-decisions` template** (`cli/verify_decisions.py`, 109 lines,
  the smallest complete example): a private `_run()` returning
  `(exit_code, error_message)`, wrapped in
  `with cli_event_context(DEFAULT_DB_PATH, "ll-verify-kinds", sys.argv[1:])`,
  `--json` via `add_json_arg`/`print_json`, exit 1 on any violation. Register
  the entry point in `scripts/pyproject.toml` alongside
  `ll-verify-skills = "little_loops.cli:main_verify_skills"` and
  `ll-verify-decisions = "little_loops.cli:main_verify_decisions"`.
- **CLI subcommand addition is two-part** in `cli/session.py`: an
  `add_parser(...)` block in `_build_parser()` (lines 55-277) plus an
  `if args.command == "<name>":` dispatch block in `main_session()` (lines
  303-645). The `prune` subparser (`cli/session.py:265-275`, dispatch at
  572-621) is the closest structural precedent for the new `rebuild`/
  `compact` subparsers — both are whole-DB lifecycle operations using
  `--dry-run`/`add_json_arg` and `resolve_config_path` to load project
  config before calling into `session_store`. The `backfill` subparser/
  dispatch pair (parser at `cli/session.py:150-185`, dispatch at 426-501)
  shows the `--since`-incremental-vs-full branch structure and the
  `logger.success(f"Backfilled {total} rows (...)")` summary-line
  convention to mirror for `rebuild`/`compact`.
- **`backfill_worker.py` has no argparse** — `main()` slices `sys.argv`
  positionally (`db_path`, `path_arg`). Adding `--rebuild` (Implementation
  Step 9) needs an ad hoc `"--rebuild" in args`-style check to stay
  consistent with the file's existing minimal-parsing style, not a new
  `ArgumentParser`.
- **Test class precedents are more specific than the issue's generic
  references**: use `TestSchemaV16IssueSessionId`
  (`test_session_store.py:3242-3287`) as the template for raw-table-shape
  assertions (`PRAGMA table_info`, index existence via
  `EXPLAIN QUERY PLAN`) in the new `TestRawEventsTable`; use
  `TestBackfillCommitEvents` (`test_session_store.py:3492-3565`, includes an
  idempotency test calling `backfill()` twice and asserting the second call
  inserts zero new rows) as the template for `TestRebuild`/`TestCompact`
  idempotency assertions; use `TestBackfillSinceFlag`
  (`test_ll_session.py:497-556`, covers argv parsing, default values, a
  mocked-dispatch assertion via `patch("little_loops.cli.session.backfill_incremental")`,
  and an invalid-input path) as the template for `TestRebuildSubcommand`/
  `TestCompactSubcommand`.

## Acceptance Criteria

- `raw_events` table exists at schema v19 with the columns
  above. `raw_events.compacted` and
  `raw_events.summary_node_id` are present.
- `backfill()` ingests to `raw_events` only; `rebuild()`
  materializes the 13 cache tables; both are idempotent.
- The three watermark keys (`last_backfill_ts`,
  `last_backfill_ts_assistant_messages`,
  `last_backfill_ts_skill_events`) are gone; replaced by
  one `last_raw_event_ts` and one `last_rebuild_version`.
- `compact --and-prune` works end-to-end on a test DB with
  old data.
- `_VALID_KINDS` is the single source for the CLI `--kind`
  choices. `search --kind snapshot` and
  `recent --kind snapshot` both work (they silently don't
  today).
- FTS5 leak test: prune a row, run rebuild, assert FTS
  row count drops to match.
- `SessionStart` calls `backfill` then conditionally
  `rebuild` based on `SCHEMA_VERSION` change.
- Pre-migration DBs at v0..v18 migrate cleanly to v19
  (additive `CREATE TABLE IF NOT EXISTS`, no destructive
  `ALTER TABLE`).
- EPIC-1707 graceful-degradation contract: writes are
  `contextlib.suppress(Exception)`-guarded; reads degrade
  on missing/empty DB.

## Implementation Steps

1. Append the v19 migration to `_MIGRATIONS` in
   `session_store.py`. Bump `SCHEMA_VERSION` to 19.
2. Implement `backfill_raw_events()` in
   `session_store.py`. Export in `__all__`.
3. Refactor the 9 `_backfill_*` functions to accept
   either input. Add `_iter_events()` helper.
4. Implement `rebuild()` in `session_store.py`. Export.
5. Implement `compact()` in `session_store.py`. Export.
6. Refactor `prune()` to operate on `raw_events`.
7. Convert `_VALID_KINDS` to `tuple[str, ...]`. Update
   `cli/session.py:90-106` and `113-129` argparse
   `choices=` to import from `session_store`.
8. Add `rebuild` and `compact` subcommands in
   `cli/session.py`. Update `backfill` subparser
   (remove `--extract-decisions` and `--snapshots`, add
   `--rebuild`).
9. Update `cli/backfill_worker.py` to accept `--rebuild`.
10. Update `hooks/session_start.py:150-163` to pass
    `--rebuild` when `SCHEMA_VERSION` has changed.
11. Add `ll-verify-kinds` CLI check.
12. Tests:
    - `TestRawEventsTable` in
      `scripts/tests/test_session_store.py` (mirrors
      `TestSchemaV17` pattern).
    - `TestRebuild` in `scripts/tests/test_session_store.py`
      (round-trip DB tests).
    - `TestCompact` in `scripts/tests/test_session_store.py`.
    - `TestValidKindsCentralization` in
      `scripts/tests/test_ll_session.py` (follows
      `test_recent_rejects_invalid_kind` at line 46).
    - `TestRebuildSubcommand`,
      `TestCompactSubcommand` in
      `scripts/tests/test_ll_session.py` (follow
      `TestBackfillSinceFlag` pattern at lines 497-554).
    - `TestSessionStartRebuild` in
      `scripts/tests/test_hook_session_start.py`
      (follows `TestSessionStartBackfillThread` at
      236-303).
    - `TestFts5LeakFixed` in
      `scripts/tests/test_session_store.py` (prune a
      row, rebuild, assert FTS row count drops).
13. Docs:
    - `docs/ARCHITECTURE.md` — schema row for v19; new
      producer→consumer diagram.
    - `docs/reference/API.md` — `rebuild()`, `compact()`,
      `_iter_events()`.
    - `docs/reference/CLI.md` — `ll-session rebuild`,
      `ll-session compact [--and-prune]`.

## Impact

- **Priority**: P3 (EPIC-2457 rollup pattern).
- **Effort**: Medium-Large. The refactor touches many
  files but each change is additive. The per-table
  watermark scheme goes away. Several duplicate-prone
  `_backfill_*` functions (loops, tool_events, messages,
  skill_events) get fixed for free because they route
  through `raw_events`'s `INSERT OR IGNORE` on
  `(source_path, line_no)`.
- **Risk**: Low per change; cumulative risk is "the new
  `rebuild()` is expensive on first run." Mitigated by:
  rebuild is opt-in (no auto-run on every session
  start; only on `SCHEMA_VERSION` change or explicit
  invocation).
- **Breaking Change**: No for the data model (additive
  table, additive columns). **Yes** for the
  `backfill --extract-decisions` and
  `backfill --snapshots` flags (subsumed by `rebuild`).
  Both flags are recent additions (ENH-2151, ENH-2152)
  with low expected usage.

## Sources

- `thoughts/history-db-raw-events-architecture.md` —
  the parent design doc; this is its implementation
  issue.
- `thoughts/history-db-expand-wiring.md` — the
  original findings report.
- `scripts/little_loops/session_store.py` — schema
  (v0–v18), `_MIGRATIONS`, the 9 `_backfill_*`
  functions, `backfill()`, `backfill_incremental()`,
  `prune()`, `_PRUNABLE_TABLES`, `_VALID_KINDS`,
  `_KIND_TABLE`, `_index()`,
  `mine_corrections_from_messages()`,
  `_compact_sessions()`.
- `scripts/little_loops/cli/session.py` — the
  11-subcommand surface; hardcoded `--kind` choices
  at lines 90-106 and 113-129.
- `scripts/little_loops/cli/backfill_worker.py` —
  the detached subprocess body to extend.
- `scripts/little_loops/hooks/session_start.py:150-163`
  — current detached subprocess spawn.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table; producer/consumer flow. |
| `docs/reference/API.md` | `session_store` module reference; new `rebuild`, `compact` exports. |
| `docs/reference/CLI.md` | `ll-session` subcommand reference; new `rebuild`, `compact`. |
| `thoughts/history-db-raw-events-architecture.md` | The parent design doc. |
| `thoughts/history-db-expand-wiring.md` | The original findings report. |

## Status

**Open** | Created: 2026-07-08 | Priority: P3

**Lands first.** ENH-2580 and ENH-2582 both depend on
`raw_events` (ENH-2580 writes to it; ENH-2582 reads from
it via `compact`).

**Owns schema v19.** ENH-2461 was independently drafted
against schema v19 too (a `usage_events` sibling table);
that collision is resolved in ENH-2461's favor-of-this-issue
— this issue owns v19, ENH-2461 is now `blocked_by` this one
and reframed to a usage `event_type` parser over
`raw_events` rather than a new ingest table. The same
reframing applies to the other blocked children
(ENH-2493, 2494, 2506, 2507, 2511): each becomes an
`_iter_events()` parser task, not a per-feature `ALTER
TABLE`/`CREATE TABLE`. Decision recorded 2026-07-12;
FEAT-2123 (downstream of ENH-2461) is not urgent, so
foundation-first ordering was chosen.

## Resolution

Implemented per the Proposed Solution, with two scope decisions made
autonomously (documented in `thoughts/shared/plans/2026-07-13-ENH-2581-management.md`,
gitignored):

1. **`raw_events` scope is the 5 JSONL-sourced event kinds only** (tool,
   message, assistant_message, skill_event, session-mapping) — matching the
   concrete `backfill_raw_events(db, *, jsonl_files, since_ts=None)` signature
   given in Proposed Solution §2 and the three JSONL-only watermarks being
   replaced. Issue/loop-state/commit ingestion keeps its existing direct-write
   path in `backfill()`, unaffected — out of scope for this issue, called out
   explicitly rather than silently narrowed.
2. **`rebuild()` wipes only tables with a real re-derivation path**:
   `tool_events`, `message_events`, `assistant_messages`, `skill_events`,
   `sessions`, `user_corrections`, `summary_nodes`/`summary_spans`, plus the
   corresponding `search_index` kinds. `cli_events`/`file_events`/
   `test_run_events` (in the issue's literal "13 cache tables" list) have no
   `_backfill_*` re-derivation function today — they're live-write-only —
   so wiping them would be unrecoverable data loss with no way back. Left
   untouched.
3. `compact()`'s new `kind='retention'` summary nodes use a fresh dedup index
   (`idx_summary_nodes_retention_dedup`) — the existing
   `idx_summary_nodes_condensed_dedup` is `UNIQUE(session_id) WHERE
   kind='condensed'` (one row per session, full stop), which would have
   silently swallowed retention summaries for any session already compacted
   by the unrelated `history.compaction` (LLM-summary) feature.
4. `ll-verify-kinds` surfaced one real pre-existing gap while being written:
   `correction_retirements` (v13/ENH-2046) had no kind registration and no
   kindless-table exemption — added to `_KINDLESS_TABLES`.
5. Fixed a latent bug found during `_KIND_TABLE` centralization:
   `recent(kind="snapshot")` raised `KeyError` (missing from `_KIND_TABLE`
   despite being in `VALID_KINDS`) — now maps to `issue_snapshots`, satisfying
   the AC verbatim ("`recent --kind snapshot` ... work[s] (silently doesn't
   today)").

All 12 Implementation Steps landed: v19 migration, `backfill_raw_events()`,
`_iter_events()` dispatch + 5 refactored `_backfill_*` functions, `rebuild()`,
`compact()`, `prune()` refactor, `VALID_KINDS` centralization + `ll-verify-kinds`,
`rebuild`/`compact` CLI subcommands + `backfill --rebuild`,
`backfill_worker.py --rebuild`, `SessionStart` conditional-rebuild wiring, full
test coverage (new: `TestRawEventsTable`, `TestRebuild`, `TestCompact`,
`TestFts5LeakFixed`, `TestValidKindsCentralization`, `TestRebuildSubcommand`,
`TestCompactSubcommand`, `TestSessionStartRebuild`, `test_verify_kinds.py`),
and docs (`ARCHITECTURE.md`, `API.md`, `CLI.md`, `.claude/CLAUDE.md`).
14807 tests pass, `ruff check`/`mypy` clean (mypy's one remaining error,
`wcwidth` missing stubs, predates this change and is unrelated).

## Session Log
- `/ll:manage-issue` - 2026-07-13T01:38:52Z - `ee2927c1-e09d-4666-af82-d0275f2ca1cd.jsonl`
- `/ll:ready-issue` - 2026-07-13T00:25:25 - `6a2b4c2f-8a8b-4234-b9ef-57429b7ac418.jsonl`
- `/ll:confidence-check` - 2026-07-12T00:00:00Z - `1e7bea2d-02ea-4e42-8286-a31fd0e09c79.jsonl`
- `/ll:refine-issue` - 2026-07-13T00:20:45 - `af64d3b3-b8cf-4b8d-86fb-f34d7b26b01f.jsonl`
- sequencing-review - 2026-07-12 - Confirmed `raw_events` is NOT yet implemented (schema still v18; no `raw_events`/`rebuild()`/`compact()`/`backfill_raw_events()` in `session_store.py`). Marked this issue the v19 schema owner and `blocks` its sibling children (ENH-2461, 2493, 2494, 2506, 2507, 2511, plus ENH-2580/2582). Decision: implement this foundation before ENH-2461 so per-feature signals become parsers, not per-feature tables. See ENH-2461's superseding-decision banner.
- `/ll:capture-issue` - 2026-07-08T00:00:00Z - fourth-pass expansion of EPIC-2457
