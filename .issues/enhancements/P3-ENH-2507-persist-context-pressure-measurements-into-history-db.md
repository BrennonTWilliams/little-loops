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
decision_needed: true
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

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify

- `scripts/little_loops/session_store.py` — append the next migration to `_MIGRATIONS`, register `context_pressure` in the live `VALID_KINDS` tuple and `_KIND_TABLE`, export `record_context_pressure_event()`, and add the recorder beside `record_test_run_event()` / `record_commit_event()`. `recent()` already dispatches generically through the kind map.
- `hooks/scripts/context-monitor.sh` — `main()` computes the authoritative `USAGE_PERCENT` and token estimate; add the best-effort persistence call after the measurement is finalized and outside the state-file lock. Extend the existing `.ll/ll-context-state.json` bookkeeping for per-level crossing state rather than introducing a second unsynchronized state file.
- `scripts/little_loops/history_reader.py` — add a context-pressure row dataclass and `context_pressure_curve(session_id)`, `pressure_crossings(session_id, since=None)`, and `pressure_summary(session_id)` beside `UsageEvent` / `recent_usage_events()` / `aggregate_usage()`.
- `scripts/little_loops/cli/ctx_stats.py` — add the context-pressure aggregation to `main_ctx_stats()`, render a `Context pressure curve` block in text output, and expose the summary in JSON output alongside the existing usage summary.
- `scripts/little_loops/hooks/post_tool_use.py` — only if Option B below is selected; this handler already writes `tool_events` and extracts `payload.session_id`, but it does not currently receive the shell monitor's computed percentage.
- `scripts/tests/test_session_store.py` — add migration, recorder, FTS, kind-registration, and duplicate/sampling persistence coverage modeled on the existing usage/commit/test-run tests.
- `scripts/tests/test_history_reader.py` — add curve ordering/filter, crossing, summary, and missing-database tests modeled on `TestRecentUsageEvents` / `aggregate_usage()`.
- `scripts/tests/test_hooks_integration.py` and `scripts/tests/test_hook_post_tool_use.py` — cover context-monitor threshold state, sampling, session identity, and DB-absent/unwritable graceful degradation.
- `scripts/tests/test_cli_ctx_stats.py` and `scripts/tests/test_ll_session.py` — cover the new rendering block and `--kind context_pressure` acceptance. `cli/session.py` currently derives both parser `choices` lists from `VALID_KINDS`, so it may not need a source edit once the kind map is updated.

### Dependent Files (Callers/Importers)

- `hooks/hooks.json` — already invokes `hooks/scripts/context-monitor.sh` for every `PostToolUse` and does not require new registration; preserve that hook's exit-code contract.
- `hooks/scripts/context-handoff-sentinel.sh` — reads the same `.ll/ll-context-state.json` measurement and uses a distinct sentinel threshold; keep its consumer behavior unchanged while sharing threshold-state semantics.
- `scripts/little_loops/cli/verify_kinds.py` — `ll-verify-kinds` scans every migration `CREATE TABLE`; the new table must be reachable through `_KIND_TABLE` or the gate fails.
- `scripts/little_loops/context_window.py` — shared model context-window resolution to consult if the producer is refactored; the shell monitor currently owns the final limit calculation.
- `scripts/little_loops/session_store.py:connect()` / `resolve_history_db()` — existing `LL_HISTORY_DB` and `.ll/history.db` resolution and migration bootstrap should be reused rather than adding a new path.

### Similar Patterns

- `scripts/little_loops/session_store.py:record_test_run_event()` — keyword-only scalar recorder with FTS indexing and no backfill path; closest shape for a live pressure measurement.
- `scripts/little_loops/session_store.py:record_commit_event()` — `INSERT OR IGNORE`, connection lifecycle, and indexing only after a successful insert.
- `scripts/little_loops/history_reader.py:UsageEvent`, `recent_usage_events()`, and `aggregate_usage()` — column-mirroring dataclass, optional `since` filtering, and graceful empty-result behavior.
- `scripts/little_loops/hooks/post_tool_use.py:handle()` — `contextlib.suppress(Exception)` around best-effort database writes; use the same non-blocking failure contract at the selected producer boundary.
- `scripts/little_loops/pytest_history_plugin.py:pytest_sessionfinish()` — `contextlib.suppress(Exception)` around a history write, with `resolve_history_db()`, `head_sha`, and `branch` metadata.
- `scripts/little_loops/session_store.py:rebuild()` — live-only tables are deliberately excluded from `_REBUILD_TABLES`; pressure rows cannot be reconstructed from `raw_events` because the raw transcript does not contain the monitor's percentage readings.

### Tests

- `scripts/tests/test_session_store.py:TestSchemaV20UsageEvents` — schema migration and exact column assertions to mirror for the next live schema version.
- `scripts/tests/test_session_store.py:TestRecordTestRunEvent` and commit-event tests — recorder round-trip, multiple rows, FTS search, and deduplication patterns.
- `scripts/tests/test_history_reader.py:TestRecentUsageEvents` — newest-first ordering, `session_id`/`since` filtering, and missing-DB behavior.
- `scripts/tests/test_hooks_integration.py:TestContextMonitorConcurrent` and threshold tests — shell-hook locking and threshold state patterns.
- `scripts/tests/test_hook_post_tool_use.py:test_writes_row_when_analytics_enabled` / `test_graceful_when_store_unwritable` — Python hook persistence and graceful-degradation patterns.
- `scripts/tests/test_cli_ctx_stats.py` — existing text/JSON rendering fixtures for the new summary block.

### Documentation

- `docs/ARCHITECTURE.md` — schema-version table, bootstrap range, and history-db hook write-path notes.
- `docs/reference/API.md` — `session_store.record_context_pressure_event()` and the three `history_reader` pressure APIs.
- `docs/reference/CLI.md` — `ll-session recent/search --kind context_pressure` and the `ll-ctx-stats` pressure block.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` and `docs/guides/SESSION_HANDOFF.md` — context-monitor persistence and threshold semantics, if the feature is user-visible there.

### Configuration

- No new setting is required for the issue's always-best-effort behavior: reuse `resolve_history_db()` and the existing `LL_HISTORY_DB` override.
- If an opt-out or capture gate is added during implementation, update `scripts/little_loops/config/features.py:AnalyticsCaptureConfig` and its schema entry together; do not silently invent a second configuration path.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Kind-map correction**: the current module exposes `VALID_KINDS` (without a leading underscore) and `_KIND_TABLE`; `cli/session.py` builds both `search --kind` and `recent --kind` parser choices from `VALID_KINDS`. The implementation must update the live symbol, not the `_VALID_KINDS` name used in the original issue prose.
- **Schema-slot correction**: the live `session_store.SCHEMA_VERSION` is currently 20. Append the migration at the next available slot when implementing, and do not hard-code a sibling issue's version. `ll-verify-kinds` requires `context_pressure_events` to be mapped by `_KIND_TABLE`.
- **Threshold correction**: `context-monitor.sh`'s `auto_handoff_threshold` defaults to 80, while `context-handoff-sentinel.sh` uses a separate `sentinel_threshold` default of 50. The existing monitor state has a single `threshold_crossed_at`; supporting 50/75/80/90/100 crossings requires an explicit emitted-level set and a decision about whether compaction resets that set. Do not describe 50 as the auto-handoff threshold.
- **Measurement ownership**: `context-monitor.sh:main()` is the only current path that has the finalized `USAGE_PERCENT`, token estimate, resolved `CONTEXT_LIMIT`, and compaction-reset behavior in one place. `post_tool_use.py:handle()` has `payload.session_id` and an existing `tool_events` write, but does not currently receive the monitor's computed pressure. A Python-only producer therefore requires a shared measurement/refactor or a state-file handoff.
- **Session and repository identity**: the shell monitor currently does not extract `session_id` from its input, and neither producer currently supplies `head_sha`/`branch` as part of the measurement. A shell producer must parse `.session_id` from the hook JSON and either gather Git metadata best-effort or persist NULL when unavailable; the row should still be useful for sessions without a repository.
- **Sampling and locking**: `context-monitor.sh` uses a short state lock around read-modify-write. Put the database write after releasing that lock, and track `last_persisted_at` (or equivalent) in the locked state so concurrent PostToolUse invocations cannot exceed the one-row-per-second cap.
- **Compaction/context-limit discontinuities**: compaction resets the estimated token state, and a transcript-baseline upgrade can change `CONTEXT_LIMIT` mid-session. Persist `used_tokens_est` and, if possible, the resolved limit or a segment marker so a sharp percentage drop is interpretable rather than mistaken for lower usage.
- **FTS and rebuild behavior**: `recent()` becomes available automatically after kind registration, while FTS requires calling the shared `_index()` helper with a sanitized content string containing session ID, percentage, token estimate, and crossing level. `context_pressure_events` should remain outside `rebuild()` because no raw-event source can re-derive these live measurements.
- **Graceful degradation**: record helpers propagate SQLite errors; hook callers must suppress them. Match the existing `post_tool_use.py` / `pytest_history_plugin.py` `contextlib.suppress(Exception)` pattern, and retain the shell hook's `|| true`/exit-0 behavior for missing, locked, or read-only databases.

**Option A**: Persist from `context-monitor.sh` immediately after it computes the finalized percentage and token estimate, calling a small best-effort Python recorder and passing the extracted session ID plus optional Git metadata. This preserves the authoritative measurement and avoids a second computation, at the cost of one guarded Python call per sampled event.

**Option B**: Persist from `scripts/little_loops/hooks/post_tool_use.py` alongside `tool_events`, refactoring the measurement/state calculation into a shared Python path or explicit handoff so the handler receives the same percentage. This centralizes database writes but expands the refactor surface and can otherwise observe stale state.

**Recommended**: Option A for the first implementation — retain `context-monitor.sh` as the measurement owner, reuse `session_store.record_context_pressure_event()` for the database contract, and keep the call outside the state lock. Revisit Option B only if profiling shows the guarded Python subprocess is materially expensive.

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

## Implementation Steps

1. Read the live `SCHEMA_VERSION`, append a `CREATE TABLE IF NOT EXISTS context_pressure_events` migration, register `context_pressure` in `VALID_KINDS` / `_KIND_TABLE`, and implement `record_context_pressure_event()` with `_index()` FTS coverage. Keep the table out of `rebuild()` because pressure readings are live-only.
2. Implement the recommended Option A in `hooks/scripts/context-monitor.sh`: extract `session_id`, persist the finalized percentage/token estimate after the state lock is released, enforce the one-second sampling cap under the existing lock, and record optional `head_sha`/`branch` without making Git or SQLite failures affect the hook exit code.
3. Extend the existing context state to track emitted threshold levels, define the exact crossing set (including the 80% auto-handoff threshold), and reset or segment crossing state when compaction or a context-limit change occurs. Keep the sentinel's separate 50% threshold semantics intact.
4. Add `ContextPressureEvent` readers and curve/crossing/summary queries in `history_reader.py`, returning empty/None results for missing or locked databases; verify generic `ll-session recent/search --kind context_pressure` behavior through the updated kind map.
5. Add the `ll-ctx-stats` text and JSON rendering block, then add migration, recorder, FTS, sampling, threshold, session identity, graceful-degradation, reader, CLI, and rendering tests using the patterns listed in the Integration Map.
6. Update schema/API/CLI and hook guidance documentation, run `ll-verify-kinds`, the focused history/hook/CLI tests, and finally `python -m pytest scripts/tests/`.

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
- `/ll:refine-issue` - 2026-07-16T16:28:14 - `84cbedd9-ee11-4708-8a40-0cc984c6fcac.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-16T02:57:56 - `7922438e-e1f4-488a-8722-8f3940ef4e97.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`