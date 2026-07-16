---
id: ENH-2507
title: Persist context-window pressure measurements into history.db
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
  - context-monitor
  - captured
---

# ENH-2507: Persist context-window pressure measurements into history.db

## Summary

`hooks/scripts/context-monitor.sh` runs on every `PostToolUse` and knows
exactly when the agent crosses the 50% / 75% / 90% of its context
budget — but the measurements only land in stderr. There is no record of
"session X hit 75% at timestamp T" or "session Y oscillated between 60%
and 80% for 12 minutes." Combined with `tool_events`'s existing
`bytes_in` / `bytes_out` / `cache_hit` columns, this is the missing
end-of-pipeline signal: pressure *and* what was pushing it. Add a
`context_pressure_events` table with `(session_id, ts, used_pct,
used_tokens_est)` rows. Cheap — about one row per PostToolUse fire.

## Motivation

- **The trigger that matters isn't recorded.** Crossing the
  `auto_handoff_threshold` (default 80) is exactly when work fragments
  across sessions; ENH-2495 will record *that the threshold was crossed*
  (`handoff_needed` event) but not the *continuous signal* leading up to
  it.
- **End-of-pipeline join.** `tool_events` already carries
  `bytes_in` / `bytes_out` / `cache_hit`. Without the pressure reading,
  you can't answer "did the Read of file X push us from 71% to 78%, or
  did the previous Edit do it?" The join is one SQL away once both
  columns exist.
- **Cost / cache-hit analysis.** A pressure-over-time chart makes it
  obvious whether cache hits are reducing pressure growth or whether
  fresh bytes are dominating. Right now you'd have to reconstruct this
  from session start + tool counts.
- **Cheap.** Roughly one row per PostToolUse fire; ~10/minute per
  active session. The producer is already running and already measuring.

## Current Behavior

- `hooks/scripts/context-monitor.sh` writes its reading to stderr on
  every PostToolUse (PostToolUse fires on every tool call).
- The measurement is consumed by `context-handoff-sentinel.sh` (Stop
  hook) to decide whether to write `.ll/ll-context-handoff-needed`.
  Both run, but neither persists the reading to `.ll/history.db`.
- `ll-session` / `ll-ctx-stats` cannot answer "show me this session's
  context-pressure curve."

## Expected Behavior

- A `context_pressure_events` table records one row per PostToolUse with
  `session_id`, `ts`, `used_pct` (0–100), `used_tokens_est` (integer
  est.), and `head_sha` / `branch`.
- Either `context-monitor.sh` shells out to `python -c '...'` after
  computing the percentage, or the Python post-tool-use handler reads
  the same sources (`CLAUDE_CONTEXT_USAGE_PERCENT`, etc.) and writes the
  row directly.
- Threshold crossings (50 / 75 / 90 / 100) emit a `threshold_crossed`
  discriminator on the row (`threshold_crossed INTEGER` 0/1 +
  `crossed_level TEXT`) so the trend queries don't have to re-derive
  it.
- `ll-session recent --kind context_pressure` returns rows;
  `ll-ctx-stats` adds a "Context pressure curve" rendering block.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS context_pressure_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    used_pct REAL,                -- 0.0–100.0
    used_tokens_est INTEGER,      -- estimated token count
    threshold_crossed INTEGER,    -- 0/1; 1 if this row's pct crossed a new threshold
    crossed_level TEXT,           -- "50" | "75" | "90" | "100" | NULL
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_pressure_session ON context_pressure_events(session_id);
CREATE INDEX IF NOT EXISTS idx_pressure_ts ON context_pressure_events(ts);
CREATE INDEX IF NOT EXISTS idx_pressure_crossed ON context_pressure_events(threshold_crossed);
```

Bump `SCHEMA_VERSION`. Add `"context_pressure"` to `_VALID_KINDS` and
`"context_pressure": "context_pressure_events"` to `_KIND_TABLE`.

### Producer wiring

- In `hooks/scripts/context-monitor.sh`, after computing
  `USAGE_PERCENT` and `TOKEN_COUNT`, shell out to:
  ```bash
  python -c "from little_loops.session_store import record_context_pressure_event; record_context_pressure_event(...)" \
    2>/dev/null || true
  ```
  Wrapped in `|| true` to preserve the "never fails" contract.
- Threshold-cross detection: track the previous level in a small state
  file (`.ll/context-pressure-state.json`); emit
  `threshold_crossed=1` + `crossed_level="80"` (or whatever) only on the
  first crossing. The handoff-sentinel logic at lines 76-81 of
  `context-handoff-sentinel.sh` already uses this state-file pattern.
- Alternative producer: extend `scripts/little_loops/hooks/post_tool_use.py`
  to read the same percentage env vars and write the row alongside the
  `tool_events` insert. Single Python call site, no shell-out, cleaner.

### Read API

- `history_reader.context_pressure_curve(session_id)` — list of
  `(ts, used_pct)` ordered by ts.
- `history_reader.pressure_crossings(session_id, since=None)` — list of
  threshold-cross events (50/75/90/100).
- `history_reader.pressure_summary(session_id)` — peak pct, average
  pct, time-at-each-level.

### CLI surface

- `ll-session recent --kind context_pressure`.
- `ll-ctx-stats`: add a "Context pressure curve" rendering block
  (ASCII chart or JSON).

## Acceptance Criteria

- Schema migration lands; `context_pressure_events` exists;
  `SCHEMA_VERSION` bumped.
- Every PostToolUse writes one row (sampled at most once per second to
  avoid row-bomb during tight loops).
- Crossing 80% (the auto-handoff threshold) writes a row with
  `threshold_crossed=1, crossed_level="80"`.
- DB-absent/locked does not change the hook exit code.
- `ll-session recent --kind context_pressure` returns rows; FTS works.
- Tests cover: typical session, threshold crossing, sampling rate
  limit, DB-absent graceful degradation.

## Sources

- `hooks/scripts/context-monitor.sh` — the producer script already
  computes `USAGE_PERCENT` and `TOKEN_COUNT`; this is a persistence
  add-on, not a measurement change
- `hooks/scripts/context-handoff-sentinel.sh` — Stop-hook consumer of
  the same measurement
- `ll-ctx-stats` (`scripts/little_loops/cli/ctx_stats.py`) — the
  consumer that would render the curve
- ENH-2495 — sibling lifecycle *events* (this issue records the
  underlying measurement; ENH-2495 records the threshold-cross event
  it produces)
- ENH-2494 / `tool_events.bytes_in` — the join partner

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table; hook write-paths note |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | New `ll-session --kind` value |

## Status

**Open** | Created: 2026-07-06 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot. Several
other active EPIC-2457 siblings (ENH-2492, ENH-2463, ENH-2464, ENH-2465,
ENH-2466, ENH-2493, ENH-2494, ENH-2495, ENH-2496, ENH-2497, ENH-2498,
ENH-2504, ENH-2506, ENH-2511, and others) independently make the same
schema-slot claim in their own Integration Maps — they cannot all land at
the same version number. Verified against current code
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