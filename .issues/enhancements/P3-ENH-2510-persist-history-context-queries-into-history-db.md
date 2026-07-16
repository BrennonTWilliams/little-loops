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
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:56 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`