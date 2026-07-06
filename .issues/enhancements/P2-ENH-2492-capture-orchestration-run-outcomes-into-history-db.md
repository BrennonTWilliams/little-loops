---
id: ENH-2492
title: Capture orchestration run outcomes (ll-auto/ll-parallel/ll-sprint) into history.db
type: ENH
priority: P2
status: open
discovered_date: 2026-07-05
captured_at: "2026-07-05T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - orchestration
  - captured
---

# ENH-2492: Capture orchestration run outcomes (ll-auto/ll-parallel/ll-sprint) into history.db

## Summary

`ll-auto`, `ll-parallel`, and `ll-sprint` each wrap their **entire batch** in a
single coarse `cli_event` (`cli_event_context(DEFAULT_DB_PATH, "ll-auto", …)` at
`cli/auto.py:33`, `cli/parallel.py:44`, `cli/sprint/__init__.py:56`). A 12-issue
auto run that completes 9 and fails 3 lands as **one row with one exit code** —
per-issue success/failure, duration, failure reason, and (for parallel) wave
number are all lost. Yet that data already exists in memory and on disk:
`ProcessingState` (`scripts/little_loops/state.py:26`) tracks
`completed_issues`, `failed_issues` (id → reason), `attempted_issues`, and
per-issue `timing`, persisted to `.ll/ll-auto-state.json` /
`.ll/ll-sprint-state.json`. This is the Python-orchestration analog of what
ENH-2458 (commits) and ENH-2459 (test runs) did for their layers: capture
execution ground-truth. Add an `orchestration_runs` table populated at batch
completion (one row per issue processed) so "which issues did last night's
`ll-auto` actually land, and how long did each take?" is a query, not a JSONL
replay.

This is **distinct from ENH-2463** (`loop_runs`): that covers FSM loops; the
Python orchestration layer has no FSM equivalent (see `docs/ARCHITECTURE.md`
§ Orchestration Layers) and is not reachable from `loop_events`.

## Motivation

- **The highest-frequency automation surface is the least observable.** `ll-auto`
  and `ll-sprint` are the primary batch drivers, but the DB can't answer
  "success rate per issue over the last week," "which issues repeatedly fail
  automation," or "median cycle time per issue" without re-parsing state files
  that are overwritten each run.
- **State files are ephemeral.** `.ll/ll-auto-state.json` is overwritten on the
  next run and swept by cleanup; there's no historical record once a batch
  finishes.
- **Parallel waves are invisible.** `ll-parallel` orders issues into
  dependency-aware waves; nothing records which wave an issue ran in or whether
  a worktree PR was opened.
- **Correlates with existing ground-truth tables.** Joining `orchestration_runs`
  against `commit_events` (ENH-2458) and `test_run_events` (ENH-2459) answers
  "did this automated fix commit and keep the suite green?" end-to-end.

## Current Behavior

- `ll-auto` / `ll-parallel` / `ll-sprint` open one `cli_event_context` for the
  whole invocation; the resulting `cli_events` row carries `(binary, args,
  exit_code, duration_ms)` for the batch, not per issue.
- `ProcessingState.completed_issues`, `.failed_issues`, `.timing` live only in
  `.ll/*-state.json` and are overwritten/swept.
- `ll-session recent --kind cli` shows the batch invocation but no per-issue
  outcome; there is no `--kind orchestration_run`.

## Expected Behavior

- An `orchestration_runs` table exists with one row per issue processed by a
  batch, carrying the driver, run id, issue id, status, duration, failure
  reason, wave number (parallel only), and PR URL when one was opened.
- At batch completion each driver flushes its `ProcessingState` into
  `orchestration_runs` (best-effort, `contextlib.suppress(Exception)`-guarded per
  the EPIC-1707 contract — a DB write failure never affects the batch).
- `ll-session recent --kind orchestration_run` returns rows;
  `ll-session search --fts "<issue_id>" --kind orchestration_run` matches.
- Interrupted batches still flush whatever issues completed/failed before the
  interrupt (write on the same path that already persists `ProcessingState`).

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS orchestration_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,             -- batch id: driver + start ts
    driver TEXT NOT NULL,             -- "ll-auto" | "ll-parallel" | "ll-sprint"
    issue_id TEXT,
    status TEXT,                      -- "completed" | "failed" | "skipped"
    failure_reason TEXT,
    duration_s REAL,
    wave INTEGER,                     -- parallel only; NULL otherwise
    pr_url TEXT,                      -- when a worktree PR was opened
    started_at TEXT,
    ended_at TEXT,
    head_sha TEXT,
    branch TEXT,
    UNIQUE(run_id, issue_id)
);
CREATE INDEX IF NOT EXISTS idx_orch_runs_driver ON orchestration_runs(driver);
CREATE INDEX IF NOT EXISTS idx_orch_runs_issue ON orchestration_runs(issue_id);
CREATE INDEX IF NOT EXISTS idx_orch_runs_status ON orchestration_runs(status);
```

Bump `SCHEMA_VERSION`. Add `"orchestration_run"` to `_VALID_KINDS` and
`"orchestration_run": "orchestration_runs"` to `_KIND_TABLE`
(`session_store.py:104`/`:119`).

### Producer wiring

- Add `record_orchestration_run(db_path, *, run_id, driver, issue_id, status,
  failure_reason=None, duration_s=None, wave=None, pr_url=None, started_at=None,
  ended_at=None, head_sha=None, branch=None)` to `session_store.py`, idempotent
  on `(run_id, issue_id)` (UPSERT), indexing `issue_id` into `search_index` with
  `kind="orchestration_run"`.
- At the end of each driver's run — the same site that writes the final
  `ProcessingState` — iterate `completed_issues` + `failed_issues` + `timing`
  and emit one `record_orchestration_run()` call per issue. Best-effort guarded.
  - `ll-auto`: `cli/auto.py` / `issue_manager.py` completion path.
  - `ll-sprint`: `cli/sprint/__init__.py` after the wave loop.
  - `ll-parallel`: `parallel/orchestrator.py` per-issue finish (`_run_issue`);
    populate `wave` and `pr_url` there (PR URL is already produced/printed).

### Read API

Add to `history_reader.py`:
- `recent_orchestration_runs(driver=None, issue_id=None, since=None, limit=50)`.
- `aggregate_orchestration_runs(group_by: Literal["driver","issue_id","status"], since=None)`
  — success-rate / median-duration rollups.

### CLI surface

- `ll-session recent --kind orchestration_run` (new `--kind` value).
- `ll-history` / `ll-ctx-stats`: optionally surface automation success-rate from
  the new table (follow-on, not required for this issue).

## Acceptance Criteria

- Schema migration lands; `orchestration_runs` exists; `SCHEMA_VERSION` bumped.
- A completed `ll-auto` batch over N issues writes N `orchestration_runs` rows
  with correct `status` and `duration_s`; a failed issue carries its
  `failure_reason`.
- An `ll-parallel` run populates `wave` and, when a PR is opened, `pr_url`.
- Writes are best-effort: with the DB absent or locked the batch still runs to
  completion and exits with its normal code (no raised exception surfaces).
- `ll-session recent --kind orchestration_run` returns rows; FTS matches an
  `issue_id`.
- Re-running the same `run_id` UPSERTs rather than duplicating rows.
- Tests cover: all-success batch, mixed success/failure, parallel wave/PR
  population, DB-absent graceful degradation, UPSERT idempotency.

## Implementation Steps

1. Schema migration for `orchestration_runs`; bump `SCHEMA_VERSION`.
2. Add `"orchestration_run"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_orchestration_run()` in `session_store.py` (UPSERT on
   `(run_id, issue_id)`, best-effort guarded); export it.
4. Wire the `ll-auto` completion path to flush `ProcessingState` per issue.
5. Wire `ll-sprint` post-wave-loop flush.
6. Wire `ll-parallel` `_run_issue` finish, populating `wave` + `pr_url`.
7. `history_reader.recent_orchestration_runs()` + `aggregate_orchestration_runs()`.
8. CLI: `ll-session recent --kind orchestration_run`.
9. Tests: `TestRecordOrchestrationRun`, `TestOrchestrationSchema`,
   `TestAutoFlushesRuns`, `TestParallelWaveAndPr`, graceful-degradation test.
10. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md`,
    `docs/reference/CLI.md`.

## Sources

- `thoughts/history-db-expand-wiring.md` — §2 gap surface (execution outcomes)
- EPIC-2457 review (2026-07-05) — item #1, ranked highest-value new sibling
- `scripts/little_loops/state.py:26` — `ProcessingState` fields
- `scripts/little_loops/cli/auto.py:33`, `cli/parallel.py:44`,
  `cli/sprint/__init__.py:56` — current coarse `cli_event_context` wrap
- `scripts/little_loops/parallel/orchestrator.py` — per-issue finish + PR create
- ENH-2458 / ENH-2459 — sibling execution-ground-truth tables to join against

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Orchestration Layers; schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader`, `state` modules |
| `docs/reference/CLI.md` | New `ll-session --kind` value |

## Status

**Open** | Created: 2026-07-05 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
