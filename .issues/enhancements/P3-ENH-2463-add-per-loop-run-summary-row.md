---
id: ENH-2463
title: Add per-loop-run summary row to history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - loops
  - captured
---

# ENH-2463: Add per-loop-run summary row to history.db

## Summary

`loop_events` records per-transition FSM state (`loop_start`, `state_enter`, `route`, `loop_complete`, `retry_exhausted`, …) but no single row summarises a run. To answer "what was the iteration count, final state, and evaluator score of `rn-implement` last Tuesday?" requires replaying the entire `loop_events` stream for that run. Add a `loop_runs` table populated at run completion via a side-effect of `loop_complete` (or a new `loop_run_summary` event) carrying `(run_id, loop_name, started_at, ended_at, final_state, iterations, terminated_by, error, evaluator_score, diagnostics_path)`. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #6: *"one row per completed loop run (final state, iteration count, evaluator score if any, path to `.loops/diagnostics/*.md`), rather than only per-transition events — makes loop health queryable without replaying the whole event stream."*

## Motivation

Loop health is the project's most heavily-instrumented surface, yet it lacks a rollup query:

- **No "best/worst loop last week" without scanning JSONL** — `ll-loop history` exists but is event-stream oriented; users want a summary view.
- **No correlation with diagnostic artifacts** — `loop-specialist` writes `.loops/diagnostics/<loop>-<ts>.md`, but the link between that path and the run row is implicit.
- **No aggregate evaluator score trend** — `mr-baseline`-style comparisons need per-run scores surfaced without per-event reconstruction.
- **Existing close-neighbour fixes are insufficient**:
  - `BUG-2304` (done) fixed the missing `error` field on `loop_complete` events; that's per-transition, not per-run.
  - `ENH-2428` (done) added a `score_stall` evaluator; that's intra-loop, not a rollup.

`loop_runs` is the missing rollup.

## Current Behavior

- `loop_events` carries `(ts, loop_name, state, transition, retries, ...)` rows per transition.
- `loop_complete` events carry `(final_state, iterations, terminated_by, error)` (after BUG-2304).
- `.loops/diagnostics/<loop>-<ts>.md` exists if `loop-specialist` ran, but isn't DB-linked.
- `ll-loop history` prints the event stream; `ll-loop promote-baseline` operates on baselines; neither surfaces a per-run summary.
- `ll-session search --fts "<loop_name>"` returns transition rows, not summary rows.

## Expected Behavior

- `loop_runs` table exists with columns: `id`, `run_id` (UNIQUE), `loop_name`, `started_at`, `ended_at`, `final_state`, `iterations`, `terminated_by`, `error`, `evaluator_score REAL`, `diagnostics_path`, `head_sha`, `branch`.
- A side-effect of `loop_complete` event processing (or a new writer at the same `_finish()` site) inserts a `loop_runs` row keyed by `run_id`.
- `ll-session recent --kind loop_run` returns rows; `ll-session search --fts "<loop_name>" --kind loop_run` returns matches.
- `ll-loop history --summary` (new flag, optionally) prints a table from `loop_runs` instead of (or in addition to) the event stream.
- Diagnostic artifact linkage: when `loop-specialist` writes a `.loops/diagnostics/<loop>-<ts>.md`, update the matching `loop_runs.diagnostics_path` column.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS loop_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,         -- e.g. "rn-implement-20260702T101530"
    loop_name TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    final_state TEXT,
    iterations INTEGER,
    terminated_by TEXT,
    error TEXT,
    evaluator_score REAL,
    diagnostics_path TEXT,
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_loop_runs_loop_name ON loop_runs(loop_name);
CREATE INDEX IF NOT EXISTS idx_loop_runs_terminated_by ON loop_runs(terminated_by);
CREATE INDEX IF NOT EXISTS idx_loop_runs_evaluator_score ON loop_runs(evaluator_score);
```

Bump `SCHEMA_VERSION`. Add `"loop_run"` to `_VALID_KINDS` and `"loop_run": "loop_runs"` to `_KIND_TABLE`.

### Producer wiring

- In `scripts/little_loops/fsm/executor.py::_finish()` (where `loop_complete` is emitted per BUG-2304), after the existing `_emit("loop_complete", payload)` call, write a `loop_runs` row keyed by `run_id`:
  - `run_id` is the run's timestamped identifier (already used in `.loops/runs/<loop-name>-<timestamp>/events.jsonl`).
  - Populate `final_state`, `iterations`, `terminated_by`, `error` from the existing `_finish()` locals.
  - `started_at` is the run's first `loop_start` event ts (`loop_events` is the source; query for `ts ORDER BY ts ASC LIMIT 1 WHERE loop_name=? AND run_id=?`).
  - `evaluator_score`: if the loop ran an `output_numeric` evaluator with a numeric score, capture it. Defer deeper score-extraction work to follow-on; start with `NULL`.
- Hook into the FSM event ingest path (`scripts/little_loops/session_store.py`) so ingested `loop_complete` JSONL events also upsert into `loop_runs` (idempotent on `run_id`).
- Update `loop-specialist` (`agents/loop-specialist.md`) artifact write to also call `update_loop_run_diagnostics(run_id, diagnostics_path)` when it writes `.loops/diagnostics/<loop>-<ts>.md`.

### Read API

Add to `history_reader.py`:
- `recent_loop_runs(loop_name=None, since=None, limit=50)` — list summaries.
- `find_loop_run(run_id)` — single record by id.
- `aggregate_loop_runs(group_by: Literal["loop_name","terminated_by"], since=None)` — pass-rate / iteration-count rollups.

### CLI surface

- `ll-session recent --kind loop_run` — new `--kind` option.
- `ll-loop history --summary` — render from `loop_runs` instead of events.
- `ll-loop runs --since YYYY-MM-DD` — new subcommand listing recent runs.

## Acceptance Criteria

- Schema migration lands; `loop_runs` table exists with `SCHEMA_VERSION` bumped.
- A run of `ll-loop run oracles/generator-evaluator` produces one `loop_runs` row at completion, with correct `final_state`, `iterations`, `terminated_by`, `error` (per BUG-2304 fix).
- The `started_at` column matches the run's actual `loop_start` ts (within 1 second).
- An interrupted run (`Ctrl-C`) still writes a `loop_runs` row with `terminated_by="error"` and a populated `error`.
- `ll-session recent --kind loop_run` returns rows; FTS search matches `loop_name`.
- Diagnostic-path update: when `loop-specialist` writes its artifact, the matching `loop_runs.diagnostics_path` is updated.
- Tests cover: normal completion, error termination, evaluator-score field (even if `NULL`), diagnostic-path linkage.

## Implementation Steps

1. Schema migration for `loop_runs`; bump `SCHEMA_VERSION`.
2. Add `"loop_run"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_loop_run_summary()` in `session_store.py` (idempotent on `run_id`); export.
4. Wire `_finish()` in `fsm/executor.py` to call `record_loop_run_summary()` after `loop_complete` emit.
5. Wire `session_store` JSONL event ingest so backfills populate `loop_runs` from historical events.
6. Update `loop-specialist` agent to call `update_loop_run_diagnostics(run_id, path)` when writing a diagnostic artifact.
7. Extend `history_reader.recent_loop_runs()` (and `find_loop_run`, `aggregate_loop_runs`).
8. CLI: `ll-session recent --kind loop_run`; new `ll-loop runs --since ...` subcommand; `ll-loop history --summary` flag.
9. Tests: `TestRecordLoopRun`, `TestSchemaV15`, `TestLoopSpecialistUpdatesDiagnostics`, `TestHistoryLoopRunsRead`.
10. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md` for new functions, `docs/reference/CLI.md` for new flags.

## Sources

- `thoughts/history-db-expand-wiring.md` — recommendations §2 row 3 ("Loop run final outcomes / evaluator scores"), §3 ranked recommendation #6
- `.issues/bugs/P2-BUG-2304-loop-complete-event-omits-error-field.md` — `loop_complete` `error` field reference
- `.issues/enhancements/P3-ENH-2428-score-plateau-early-stop-for-generator-evaluator.md` — sibling evaluator work
- `scripts/little_loops/fsm/executor.py::_finish()` — emit site for `loop_complete`
- `scripts/little_loops/agents/loop-specialist.md` — diagnostic artifact writer

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` module references |
| `docs/reference/CLI.md` | New `ll-session`, `ll-loop` flags |
| `docs/guides/LOOPS_GUIDE.md` | Loops debugging section |

## Status

**Open** | Created: 2026-07-02 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
