---
id: ENH-2510
title: Persist ll-history-context query telemetry into history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-06
captured_at: "2026-07-06T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - context
  - telemetry
  - captured
---

# ENH-2510: Persist ll-history-context query telemetry into history.db

> **✅ Architecture alignment (ENH-2581 `raw_events`).**
> [[ENH-2581]] made `raw_events` the single ingestion point for **session-transcript
> JSONL**, with stream-derived tables materialized by `_backfill_*()` parsers via
> `rebuild()` (the pattern [[ENH-2461]] became). **`context_query_events` is NOT such
> a table, and correctly so.** The telemetry (`queried_kind`, `queried_id`,
> `result_tokens`, `hit_rate`) is a *structured result already in hand* inside
> `ll-history-context` — captured in-process, one row per call — not reconstructed
> from transcript text. (`ll-history-context` is a CLI the planning skills invoke; its
> internal per-query cost is not a transcript tool_use payload.) It is therefore a
> **live-write-only direct-write sibling** (same category as `cli_events` /
> `test_run_events`/[[ENH-2459]]), correctly **outside `raw_events`'s scope** (NOT in
> `_REBUILD_TABLES` / `_REBUILD_SEARCH_KINDS`). No `raw_events`-sourced parser is
> needed. (Read the live `SCHEMA_VERSION`/`VALID_KINDS` at implementation time.)

## Summary

Every time the agent asks the DB for historical context — "Context for
BUG-2471", "effort context for ENH-2493", "FTS match for `session_id`
" — currently leaves no row. So we can't tune the history-context
budget (`history.compaction.budget_tokens` = 4096), can't see which
issue IDs get queried the most, and can't correlate high-cost planning
sessions with high-volume history fetches. Add a `context_query_events`
table with `(session_id, queried_kind, queried_id, result_tokens,
hit_rate, ts)` and wire it into `ll-history-context`. Pairs naturally
with `ll-ctx-stats` for cost analysis — together they tell you
"this session burned 41K output tokens, half of which was
ll-history-context fetches."

## Motivation

- **Tuning the budget is impossible without telemetry.** Today the
  `history.compaction.budget_tokens: 4096` cap is set at config-schema
  default with no signal about whether it's the right number. Some
  issues may need more, others may waste it; without per-query rows
  we can't tell.
- **The query kind space is small and meaningful.** `ll-history-context`
  has three modes today: per-issue context (`--for-skill NAME` gated
  plus free-form), FTS-driven corrections, and effort summaries. Each
  is a distinct cost shape and should be a discriminator.
- **Pairs naturally with `ll-ctx-stats`.** `ll-ctx-stats` reports
  per-session tool-call byte accounting and cache-hit ratios;
  `context_query_events` reports per-session history-fetch cost.
  Together they answer "is the history-context fetcher a meaningful
  slice of session spend, and is the cache holding?"
- **Tiny producer.** `ll-history-context` already builds the
  structured result; capturing `(queried_kind, queried_id,
  result_tokens)` is one line per call.

## Current Behavior

- `ll-history-context` (`scripts/little_loops/cli/history_context.py`)
  builds the result, writes it to stdout, exits. No DB write.
- `ll-session search --fts` (the FTS path) is its own CLI; not yet
  wired through `ll-history-context`. Capture FTS-query events
  separately (or extend `ll-history-context` to wrap them).
- `history.compaction.budget_tokens` is a static config value; nothing
  measures whether the cap is hit, exceeded, or wasteful.

## Expected Behavior

- A `context_query_events` table records one row per history-context
  fetch with `queried_kind` (`issue` | `epic` | `fts` | `effort` |
  `corrections`), `queried_id` (the issue ID, search term, or NULL for
  unfiltered FTS), `result_tokens` (integer est.), `hit_rate` (0–1;
  fraction of FTS results that survived the budget filter), `ts`,
  `session_id`.
- `ll-history-context` (and the FTS-query path in `ll-session`) call
  `record_context_query_event(...)` before returning. Best-effort.
- `ll-ctx-stats`: add a "History-context fetches" rendering block
  listing per-session fetch counts and total result_tokens.
- `history.compaction.budget_tokens` tuning becomes data-driven: "for
  the last 30 days, the 90th-percentile result_tokens was 6,200, so
  raise the budget to 8,000."

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS context_query_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    queried_kind TEXT NOT NULL,   -- "issue" | "epic" | "fts" | "effort" | "corrections"
    queried_id TEXT,              -- "BUG-2471" or the FTS term, NULL if unfiltered
    result_tokens INTEGER,        -- estimated token count of the rendered result
    hit_rate REAL,                -- 0.0–1.0; FTS matches that survived budget filtering
    budget_tokens INTEGER,        -- the configured budget_tokens at query time
    under_budget INTEGER,         -- 0/1; 1 if result_tokens <= budget_tokens
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_ctx_query_session ON context_query_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ctx_query_kind ON context_query_events(queried_kind);
CREATE INDEX IF NOT EXISTS idx_ctx_query_under_budget ON context_query_events(under_budget);
```

Bump `SCHEMA_VERSION`. Add `"context_query"` to `_VALID_KINDS` and
`"context_query": "context_query_events"` to `_KIND_TABLE`.

### Producer wiring

- In `scripts/little_loops/cli/history_context.py`, after the
  result-rendering block, capture the structured result and call
  `record_context_query_event(db_path, queried_kind=...,
  queried_id=..., result_tokens=..., hit_rate=...,
  budget_tokens=...)`. Best-effort.
- In `scripts/little_loops/cli/session.py` (the FTS path inside
  `search()`), emit a `context_query_events` row per FTS query with
  `queried_kind="fts"`, `queried_id=<search term>`, `hit_rate=<matches
  / total>`. Best-effort.
- Backfill: walk `search_index` for historical FTS queries (not
  directly possible from JSONL since queries weren't logged; skip).
  Live-only capture is fine.

### Read API

- `history_reader.context_query_curve(session_id)` — list of `(ts,
  result_tokens)` ordered by ts.
- `history_reader.budget_pressure(since=None)` — fraction of queries
  that hit `under_budget=0`. A rising trend means "raise the budget."
- `history_reader.top_queried(since=None, kind=None)` — top-N queried
  IDs (e.g., "BUG-2501 was fetched 14 times this week").
- `history_reader.frequent_fetchers(since=None)` — sessions that
  emitted the most history-context fetches (the "thrashing planner"
  signal).

### CLI surface

- `ll-session recent --kind context_query`.
- `ll-ctx-stats`: add a "History-context fetches" block.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Live `SCHEMA_VERSION` is 20.** `scripts/little_loops/session_store.py:207` defines `SCHEMA_VERSION = 20`. The next free slot at implementation time will be `21` (or whatever other EPIC-2457 siblings claim first — read the live constant at merge time per the existing Scope-Boundary note).

**Add `context_query` to the canonical registry trio.** In `session_store.py`:
- `VALID_KINDS` tuple at lines 209-222 — append `"context_query"`.
- `_KIND_TABLE` dict at lines 223-236 — append `"context_query": "context_query_events"`.
- `__all__` exports (lines 34-90) — add `record_context_query_event` if making it public.

`ll-verify-kinds` (`scripts/little_loops/cli/verify_kinds.py:40-67`) automatically catches any `CREATE TABLE` in `_MIGRATIONS` that isn't in `_KIND_TABLE` or `_KINDLESS_TABLES`, so the migration block and the `_KIND_TABLE` entry must land together.

**Model the new migration and `record_context_query_event()` on `commit_events` (v17, ENH-2458).** The closest structural analogue lives at:
- Migration block: `session_store.py:626-645` — `CREATE TABLE` with indexes, no `_backfill_*` function.
- Writer: `record_commit_event()` at `session_store.py:1222-1272` — idempotent via `INSERT OR IGNORE` on the natural key, with `_index()` FTS call only when `cursor.rowcount` is 1.
- Reader: `recent_commit_events()` at `scripts/little_loops/history_reader.py:651-686` — narrow by session, optional `since`, capped `limit`, return list of dataclass.

For ENH-2510 skip the `_backfill_*` function entirely (issue line 119 says historical backfill isn't possible from JSONL — live-only capture is fine).

**Insert points in the producer CLI `scripts/little_loops/cli/history_context.py`:**
- `--effort` branch end: after line 245.
- `--project` branch end: after line 214.
- Per-issue branch end: after the `## Historical Context` print loop at line 367 (before `lt_section`/`prior_work_section` appends at lines 369-377).
- Skip the `--for-skill` gate branch at lines 217-222 (no DB activity there).

Wrap each `record_context_query_event(...)` call in `contextlib.suppress(Exception)` (per Pattern C in `hooks/user_prompt_submit.py:79-94`) to keep the CLI exit code at 0 even when the DB is locked or absent — matching the existing graceful-degradation contract.

**Insert point in the FTS producer `scripts/little_loops/cli/session.py`:** inside the `search` subcommand handler at lines 378-409, immediately after `history_search(args.fts, kind=args.kind, limit=args.limit, db=args.db)` at line 381. The `args.kind` filter at line 103/115 is built from `VALID_KINDS`, so adding `"context_query"` to the registry wires `ll-session recent --kind context_query` automatically with no CLI-parser change needed.

**Reader-pattern parallels** in `scripts/little_loops/history_reader.py` (all use `_connect_readonly()` at lines 256-275 for graceful-degradation when the DB is absent):
- `context_query_curve(session_id)` → mirror `recent_commit_events()` at line 651 (per-session narrow, `since`, `limit`, return `list[ContextQueryEvent]`).
- `budget_pressure(since=None)` → mirror `aggregate_usage(group_by="model")` at line 596 (single `AVG(result_tokens)` or `SUM(CASE WHEN under_budget=0 THEN 1 ELSE 0 END) / COUNT(*)` ratio).
- `top_queried(since=None, kind=None)` → mirror `summarize_skills()` at line 497 (`GROUP BY queried_id ORDER BY COUNT(*) DESC`).
- `frequent_fetchers(since=None)` → mirror `summarize_skills()` again with `GROUP BY session_id`.

The new `ContextQueryEvent` dataclass lands alongside siblings at lines 67-211 (`CommitEvent`, `UsageEvent`, etc.). Use `_row_to_dataclass()` at line 273 for the row→instance conversion.

**Consumer integration in `scripts/little_loops/cli/ctx_stats.py`:**
- Add an `_aggregate_context_query_events(db_path)` helper next to `_aggregate_usage_events()` at lines 169-257, returning `{"fetch_count": int, "total_result_tokens": int, "by_kind": dict[str, int]}` and `None` on graceful-degradation.
- Add a `"history_context_fetches"` key to `_print_json()` (lines 442-499) — SQLite branch (472-488) and `null` fallback (489-496).
- Extend `_render()` (lines 346-420) with an optional `context_query_stats` kwarg; mirror the "Skill health" section template at lines 404-416 (sort by count descending, print one line per queried_kind with total result_tokens).
- Wire the new aggregator at `main_ctx_stats()` lines 597-606, pass it to both `_print_json(...)` and `_render(...)`.

**`result_tokens` heuristic.** The renderer today just prints `rows` without token accounting (`history_context.py:367`). Use `_estimate_tokens(text) = len(text) // 4` from `session_store.py:2178-2180` over the joined markdown (`"## Historical Context\n" + "\n".join(rows)`) at insert time. `under_budget = 1 if result_tokens <= budget_tokens else 0` is computable then. Read `budget_tokens` via `BRConfig(Path.cwd()).history.compaction.budget_tokens` (the config loader is already imported at `history_context.py:330`).

**`hit_rate` derivation.** Today the FTS path (`session_store.search()` at lines 1434-1459) returns raw BM25-ranked rows up to `limit`. No post-budget filter exists yet, so the simplest honest `hit_rate` is `len(results) / max(args.limit, 1)` (fraction of requested slots that produced a hit); `0.0` for empty results. For the `history_context.py` per-issue path (lines 255-258), the natural derivation is `len(fresh_search) / max(len(search_results), 1)` since `fresh_search` is what survived the stale-cutoff filter.

**Validation gate:** `scripts/tests/test_verify_kinds.py` will catch a missing `_KIND_TABLE` entry on the first test run after migration lands. The `TestValidKindsCentralization` invariant at `test_session_store.py:3409-3418` (`set(VALID_KINDS) == set(_KIND_TABLE.keys())`) continues to hold when adding `context_query` to both.

## Integration Map

_Populated by `/ll:refine-issue` from codebase research:_

### Schema and registry (central)

- `scripts/little_loops/session_store.py:207` — `SCHEMA_VERSION = 20` (next slot = 21 at time of writing; read live constant at implementation).
- `scripts/little_loops/session_store.py:209-222` — `VALID_KINDS` tuple (append `"context_query"`).
- `scripts/little_loops/session_store.py:223-236` — `_KIND_TABLE` dict (append `"context_query": "context_query_events"`).
- `scripts/little_loops/session_store.py:333-734` — `_MIGRATIONS` list (append v21+ block creating `context_query_events` with indexes).
- `scripts/little_loops/session_store.py:940-970` — `record_correction()` pattern (minimal `record_*_event()` template).
- `scripts/little_loops/session_store.py:1222-1272` — `record_commit_event()` (closest structural analogue, with `INSERT OR IGNORE` + FTS index).
- `scripts/little_loops/session_store.py:890-903` — `_index()` FTS helper to reuse.
- `scripts/little_loops/session_store.py:2178-2180` — `_estimate_tokens()` 4-char-per-token heuristic for `result_tokens`.
- `scripts/little_loops/session_store.py:1462-1484` — `recent()` lookup (auto-wires `ll-session recent --kind context_query` once `_KIND_TABLE` is updated).

### Producer CLIs (where `record_context_query_event(...)` is called)

- `scripts/little_loops/cli/history_context.py:173-379` — `main_history_context()` wraps in `cli_event_context(...)` at line 179. Insert `record_context_query_event(...)` at line 367 (per-issue branch), line 214 (--project), line 245 (--effort), each wrapped in `contextlib.suppress(Exception)`.
- `scripts/little_loops/cli/session.py:378-409` — `search` subcommand handler. Insert `record_context_query_event(...)` immediately after `history_search(...)` at line 381.
- `scripts/little_loops/cli/__init__.py:19` — describe entry text (no change needed).

### Reader API (where new query functions land)

- `scripts/little_loops/history_reader.py:7-42` — module docstring (list the four new functions).
- `scripts/little_loops/history_reader.py:67-211` — dataclass declarations (add `ContextQueryEvent` alongside `CommitEvent`/`UsageEvent`).
- `scripts/little_loops/history_reader.py:256-275` — `_connect_readonly()` for graceful-degradation.
- `scripts/little_loops/history_reader.py:497-546` — `summarize_skills()` (template for `top_queried`/`frequent_fetchers`).
- `scripts/little_loops/history_reader.py:549-595` — `recent_usage_events()` (template for `context_query_curve`).
- `scripts/little_loops/history_reader.py:596-648` — `aggregate_usage()` (template for `budget_pressure`).
- `scripts/little_loops/history_reader.py:651-686` — `recent_commit_events()` (template for `context_query_curve`).

### Consumer (rendering block in `ll-ctx-stats`)

- `scripts/little_loops/cli/ctx_stats.py:169-257` — `_aggregate_usage_events()` (template for `_aggregate_context_query_events()`).
- `scripts/little_loops/cli/ctx_stats.py:346-420` — `_render()` end (slot for "History-context fetches" block after Skill health at 404-416).
- `scripts/little_loops/cli/ctx_stats.py:442-499` — `_print_json()` payload (add `"history_context_fetches"` key alongside `"usage_events"`).
- `scripts/little_loops/cli/ctx_stats.py:581-630` — `main_ctx_stats()` orchestrator (call new aggregator at line 604, pass to render/JSON at lines 606/619).

### Dependent files (callers/importers)

- `scripts/little_loops/cli/session.py:45` — already imports `VALID_KINDS` (no change needed; will gain `context_query` automatically).
- `scripts/little_loops/cli/session.py:103,115` — `args.kind` choices built from `VALID_KINDS` (auto-wired).
- `scripts/little_loops/init/writers.py:35,78` — `Bash(ll-history-context:*)` permission allowlist + CLI inventory list (verify but no schema change needed).

### Test files (existing patterns to extend)

- `scripts/tests/test_session_store.py:50-62` — module-level `tmp_path` fixture (use as-is for new tests).
- `scripts/tests/test_session_store.py:3409-3418` — `TestValidKindsCentralization` (auto-passes when adding to both `VALID_KINDS` and `_KIND_TABLE`).
- `scripts/tests/test_session_store.py:3727-3755` — `TestSchemaV14.test_v13_to_v14_migration` (template for new `TestSchemaV21ContextQueryEvents`).
- `scripts/tests/test_session_store.py:3891-3911` — `_bootstrap_schema_at(db, version)` helper for migration tests.
- `scripts/tests/test_session_store.py:4025-4033` — DB-unopenable graceful-degradation test (template for "DB-absent doesn't change exit code" AC).
- `scripts/tests/test_session_store.py:4235-4283` — `TestRecordCommitEvent` (template for new `TestRecordContextQueryEvent`).
- `scripts/tests/test_session_store.py:3224-3243` — `TestSchemaV20UsageEvents.test_usage_events_columns` (template for schema-presence test).
- `scripts/tests/test_history_reader.py:1438,1459` — `test_recent_commit_events_filters` / `test_recent_test_runs_and_pass_rate` (templates for `budget_pressure`, `top_queried`, `frequent_fetchers`).
- `scripts/tests/test_history_context_cli.py` — 19+ classes using `with patch("sys.argv", [...])` + `main_history_context()` pattern (add a `TestContextQueryEventEmission` class driving each `queried_kind`).
- `scripts/tests/test_ll_session.py:64-128` — argparse classes for `search --fts` (template for FTS producer test).
- `scripts/tests/test_verify_kinds.py` — `_KIND_TABLE` lint (auto-catches missing entry).

### Configuration

- `scripts/little_loops/config-schema.json:1787-1796` — `history.compaction.budget_tokens` (default `4096`). This value is what the new telemetry tunes; no schema bump needed.
- `.ll/ll-config.json` — per-project config (no new keys needed unless adding a `history.context_capture.enabled` gate).

### Documentation

- `docs/ARCHITECTURE.md:657-678` — schema-versions table (add one row mirroring v20 wording style).
- `docs/reference/API.md:6847+,7051,7065` — `from little_loops.history_reader import ...` block + per-function reference entries (auto-generated but prose lists need `context_query` added).
- `docs/reference/CLI.md:2427,2435,2509` — `--kind` choice list (auto-generated from `VALID_KINDS`) + examples block (add `recent --kind context_query` example).
- `docs/guides/HISTORY_SESSION_GUIDE.md` — likely needs a note about the new "thrashing planner" diagnostic via `frequent_fetchers()` (verify at write time).

## Implementation Steps

_Concrete phasing from codebase research:_

1. **Migration + registry** (`scripts/little_loops/session_store.py`)
   - Append the v21 (or current-next-open-slot) migration block to `_MIGRATIONS` (currently 20 entries ending at line 733) creating `context_query_events` with the schema in the existing `## Proposed Solution` block, plus three `CREATE INDEX IF NOT EXISTS` statements.
   - Append `"context_query"` to `VALID_KINDS` (lines 209-222).
   - Append `"context_query": "context_query_events"` to `_KIND_TABLE` (lines 223-236).
   - Bump `SCHEMA_VERSION` (line 207) from `20` to the next slot.
   - Verify `ll-verify-kinds` still passes.

2. **Writer helper** (`scripts/little_loops/session_store.py`)
   - Add `record_context_query_event(db_path, *, ts, session_id, queried_kind, queried_id, result_tokens, hit_rate, budget_tokens, under_budget, head_sha=None, branch=None, config=None)` after the v21 migration block.
   - Body: model on `record_correction()` (lines 940-970) for the minimal `INSERT` + `_index()` + `commit()` + `close()` shape; or on `record_commit_event()` (lines 1222-1272) if adding `INSERT OR IGNORE` for de-dup.
   - Add `"record_context_query_event"` to `__all__` (lines 34-90).

3. **Producer wiring** (`scripts/little_loops/cli/history_context.py` + `scripts/little_loops/cli/session.py`)
   - In `history_context.py`: import `record_context_query_event` and `BRConfig` (already imported at line 330). Compute `result_tokens` via `_estimate_tokens("## Historical Context\n" + "\n".join(rows))` (or 0 for empty/early-return paths); compute `hit_rate` from `len(fresh_search) / max(len(search_results), 1)` where the data is available; read `budget_tokens` from `BRConfig(...).history.compaction.budget_tokens`. Wrap each call site in `contextlib.suppress(Exception)`.
   - In `session.py` `search` subcommand (lines 378-409): add `record_context_query_event(...)` immediately after the `history_search(...)` call at line 381 with `queried_kind="fts"`, `queried_id=args.fts`, `hit_rate=len(results) / max(args.limit, 1)`. Wrap in `contextlib.suppress(Exception)`.

4. **Reader API** (`scripts/little_loops/history_reader.py`)
   - Add `ContextQueryEvent` dataclass in the region of lines 67-211.
   - Add `context_query_curve(session_id=None, *, since=None, limit=50, db=DEFAULT_DB_PATH) -> list[ContextQueryEvent]` (model on `recent_commit_events()` at lines 651-686).
   - Add `budget_pressure(since=None, *, db=DEFAULT_DB_PATH) -> float | None` (single value 0.0-1.0; `None` if no rows).
   - Add `top_queried(since=None, kind=None, *, limit=10, db=DEFAULT_DB_PATH) -> list[dict]` (model on `summarize_skills()` at lines 497-546).
   - Add `frequent_fetchers(since=None, *, limit=10, db=DEFAULT_DB_PATH) -> list[dict]` (group-by session_id).
   - Update the module docstring (lines 7-42) to list the four new exports.

5. **Consumer rendering** (`scripts/little_loops/cli/ctx_stats.py`)
   - Add `_aggregate_context_query_events(db_path) -> dict | None` after `_aggregate_usage_events` (lines 169-257) returning `{"fetch_count": int, "total_result_tokens": int, "by_kind": dict[str, int]}` and `None` on DB-absent.
   - Extend `_render()` (lines 346-420) with an optional `context_query_stats` kwarg; print a "History-context fetches" block when non-`None`, mirroring "Skill health" (lines 404-416).
   - Extend `_print_json()` (lines 442-499) with a `"history_context_fetches"` key (SQLite branch 472-488, `null` fallback 489-496).
   - Wire the new aggregator in `main_ctx_stats()` at lines 597-606; pass to `_print_json(...)` and `_render(...)`.

6. **Tests** (`scripts/tests/test_session_store.py`, `scripts/tests/test_history_reader.py`, `scripts/tests/test_history_context_cli.py`, `scripts/tests/test_ll_session.py`)
   - Add `TestSchemaV21ContextQueryEvents` (model on `TestSchemaV20UsageEvents` at lines 3224-3243): assert table exists, columns match the spec, all three indexes exist.
   - Add `TestRecordContextQueryEvent` (model on `TestRecordCommitEvent` at lines 4235-4283): roundtrip, hit-rate computation, FTS-indexed searchability, DB-absent graceful-degradation.
   - Add `test_budget_pressure_returns_fraction_in_[0,1]` and `test_top_queried_group_by_id` to `test_history_reader.py` (model on `test_recent_commit_events_filters` at line 1438).
   - Add `TestContextQueryEventEmission` to `test_history_context_cli.py` (one test per `queried_kind`).
   - Add FTS producer test to `test_ll_session.py:64-128` mirroring the existing FTS argv pattern at line 128.
   - Update the `assert SCHEMA_VERSION == 20` test sites in `test_session_store.py` (lines 1372, 1817, 1984, 2080) to assert the new value.

7. **Verification**
   - Run `python -m pytest scripts/tests/test_session_store.py scripts/tests/test_history_reader.py scripts/tests/test_history_context_cli.py scripts/tests/test_ll_session.py scripts/tests/test_verify_kinds.py -v`.
   - Run `python -m mypy scripts/little_loops/` (no type errors).
   - Manually exercise `ll-history-context ENH-1708 --db /tmp/test.db` followed by `ll-session recent --kind context_query --db /tmp/test.db` to verify the row is written and retrievable.

8. **Documentation**
   - Add a row to `docs/ARCHITECTURE.md` schema-versions table (lines 657-678) mirroring the v20 entry style (column list + writer path + ENH ID).
   - Update `docs/reference/API.md` `from little_loops.history_reader import ...` block + add per-function entries (lines 6847+, 7051+).
   - Update `docs/reference/CLI.md` `--kind` prose list (lines 2427, 2435) + add `recent --kind context_query` example (around line 2509).

## Acceptance Criteria

- Schema migration lands; `context_query_events` exists;
  `SCHEMA_VERSION` bumped.
- An `ll-history-context BUG-2471` invocation writes one row with
  `queried_kind="issue"`, `queried_id="BUG-2471"`, `result_tokens`,
  `budget_tokens`, `under_budget`.
- An `ll-session search --fts "<term>"` invocation writes one row with
  `queried_kind="fts"`, `queried_id="<term>"`, `hit_rate`.
- DB-absent/locked does not change the CLI exit code.
- `ll-session recent --kind context_query` returns rows;
  `budget_pressure()` returns a fraction in [0, 1].
- Tests cover: each `queried_kind`, over-budget vs. under-budget,
  empty result (hit_rate=0), DB-absent graceful degradation.

## Sources

- EPIC-2457 review (third-pass expansion, 2026-07-06) — item from the
  user-reported gap list
- `scripts/little_loops/cli/history_context.py` — producer entry point
- `scripts/little_loops/cli/session.py` — FTS-query producer
- `scripts/little_loops/cli/ctx_stats.py` — consumer (would render the
  block)
- `config-schema.json` — `history.compaction.budget_tokens` is the
  value this issue's telemetry tunes

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | New `ll-session --kind` value |

## Status

**Open** | Created: 2026-07-06 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot
("`context_query_events` exists; `SCHEMA_VERSION` bumped"). Several other
active EPIC-2457 siblings (ENH-2492, ENH-2463, ENH-2464, ENH-2465, ENH-2466,
ENH-2493, ENH-2494, ENH-2495, ENH-2496, ENH-2497, ENH-2498, ENH-2504,
ENH-2506, ENH-2511, and others) independently make the same schema-slot
claim in their own Integration Maps — they cannot all land at the same
version number. Verified against current code
(`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's implied slot;
each child lands its own migration at whatever version is open when it is
implemented (no coordinated release; per EPIC-2457's own "no shared helper
module is required" scope note).

## Session Log
- `/ll:refine-issue` - 2026-07-16T16:57:36 - `f2825a03-9cd8-4b04-9bb3-88ec49c1a255.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:56 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`