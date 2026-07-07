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
decision_needed: false
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

## Integration Map

### Files to Modify (producers — add per-issue flush)

- `scripts/little_loops/cli/auto.py` — `main_auto()` at line 25 wraps the
  inner `manager.run()` in `cli_event_context(DEFAULT_DB_PATH, "ll-auto", …)`
  at line 33. The driver label is hardcoded `"ll-auto"`; the new flush call
  must use the same label. Source-of-truth state: `manager.state_manager.state`
  (a `ProcessingState` dataclass from `state.py:26`), readable in
  `issue_manager.py:AutoManager.run()` `finally:` (line 1330-1333) immediately
  before `state_manager.cleanup()` wipes the in-memory file.
- `scripts/little_loops/cli/parallel.py` — `main_parallel()` at line 36,
  `cli_event_context(...)` at line 44. Driver label `"ll-parallel"`. The flush
  happens inside `ParallelOrchestrator._on_worker_complete` (see below) — the
  CLI wrapper itself doesn't need changes beyond delegating to the
  orchestrator's per-issue write.
- `scripts/little_loops/cli/sprint/__init__.py` — `main_sprint()` at line 48,
  `cli_event_context(...)` at line 56. Driver label `"ll-sprint"`. Sprint
  composes a `ParallelOrchestrator` per wave with `wave_label=f"Wave
  {wave_num}/{total_waves}"` (`cli/sprint/run.py:607`), so wave attribution
  flows from `self.wave_label` (`parallel/orchestrator.py:103`).
- `scripts/little_loops/parallel/orchestrator.py:_on_worker_complete` (line
  914-1087) — the per-issue finish callback for `ll-parallel` and `ll-sprint`.
  PR URL is known here at line 1044-1045
  (`self._pr_ready_branches[result.issue_id] = branch_state`); timing written
  at line 1066-1070; wave label available as `self.wave_label` (line 103).
  `_open_pr_for_branch` (signature at line 1109-1114; docstring at line 1117
  documents *"Mutates branch_state in place to record pr_url on success"*;
  the `pr_result.returncode == 0` mutation lives inside the function body at
  lines 1109-1160). This is the natural flush point.
- `scripts/little_loops/issue_manager.py:AutoManager.run()` (line 1282-1339)
  — `finally:` block at line 1330-1333 is the natural flush site for
  `ll-auto`. `state_manager.state.completed_issues`, `.failed_issues`,
  `.timing` are all populated at this point.
- `scripts/little_loops/cli/sprint/run.py:_cmd_sprint_run()` (line 232) — for
  single-issue / contention sub-waves (the
  `_run_issue_with_wall_clock_timeout` path at line 44-88), the per-issue
  outcomes are appended to `state.completed_issues` (lines 546, 620, 653),
  `state.failed_issues[…]` (lines 556, 626, 652), and `state.timing[…]`
  (lines 547, 621, 654). Multi-issue waves delegate to
  `ParallelOrchestrator(wave_label=...)` whose flush site is above.

### Files to Modify (store)

- `scripts/little_loops/session_store.py`:
  - Line 60 `__all__` — add `"record_orchestration_run"`.
  - Line 102 `SCHEMA_VERSION = 18` — bump to 19.
  - Line 104 `_VALID_KINDS` — add `"orchestration_run"`.
  - Line 119 `_KIND_TABLE` — add `"orchestration_run": "orchestration_runs"`.
  - Line 208+ `_MIGRATIONS` — append a v19 entry with the issue's proposed
    SQL. Apply via `_apply_migrations()` (line 609-645) under
    `BEGIN IMMEDIATE` with `_split_sql_statements` (line 579-589); bump meta
    via `INSERT OR REPLACE INTO meta(key='schema_version')` (line 635-639).
  - New `record_orchestration_run()` modelled on `record_commit_event`
    (line 1041-1091) — `INSERT OR IGNORE` on the `(run_id, issue_id)` UNIQUE
    constraint, conditional `_index()` only when `cursor.rowcount == 1`.

### Files to Modify (reader)

- `scripts/little_loops/history_reader.py`:
  - Add `@dataclass class OrchestrationRun` near line 124 (mirroring
    `CommitEvent` at line 124 / `RunEvent` at line 138).
  - Add `recent_orchestration_runs(driver=None, issue_id=None, since=None,
    limit=50)` mirroring `recent_commit_events` at line 524-559 (uses
    `_connect_readonly` + `try/except sqlite3.Error → return []`).
  - Add `aggregate_orchestration_runs(group_by=Literal["driver","issue_id",
    "status"], since=None)` mirroring the rollup pattern in
    `summarize_skills` at line 472.
  - Public-API docstring block (lines 1-42) — add new symbols.

### Files to Modify (CLI)

- `scripts/little_loops/cli/session.py` — extend `search` `--kind` `choices`
  at line 90 and `recent` `--kind` `choices` at line 114 to include
  `"orchestration_run"`. Routing flow-through is automatic: `_VALID_KINDS` →
  `recent()` (`session_store.py:1268`) → table from `_KIND_TABLE`.

### Test Files (additive)

- `scripts/tests/test_session_store.py` — add `TestRecordOrchestrationRun`
  (mirroring `TestRecordCommitEvent` at line 3416, `TestRecordTestRunEvent`
  at line 3549): round-trip, dedupe on `(run_id, issue_id)`, FTS-searchable
  by `failure_reason`. Add `TestOrchestrationSchema` for v18→v19
  upgrade (mirror `test_v14_db_upgrades_gains_test_run_events` at line
  3607-3619) using `_bootstrap_schema_at(db, 18)` helper at line 3075-3095.
- `scripts/tests/test_history_reader.py` — add to `TestNewEventReaders`
  (line 1378-1523): `test_recent_orchestration_runs_filters` (mirror line
  1421), `test_recent_orchestration_runs_empty_on_missing_db` (mirror the
  graceful-degradation test at lines 1511-1521; the earlier `1508` anchor
  referenced the section header, not the test body).
- `scripts/tests/test_ll_session.py` — add `test_recent_kind_orchestration_run_accepted`
  (mirror `test_recent_subcommand_commit_accepted` line 78).
- `scripts/tests/test_cli.py::TestMainAutoIntegration` (line 279) — add a
  graceful-degradation test that points `LL_HISTORY_DB` at an unwritable
  path and asserts `main_auto` still exits 0.
- `scripts/tests/test_parallel_cli.py::TestParallelNormalRun` (line 183) —
  add `test_parallel_records_wave_and_pr_url` (mock `_on_worker_complete`;
  assert PR URL propagates into `orchestration_runs` row).

### Documentation

- `docs/ARCHITECTURE.md` — add v19 row to schema-versions table at lines
  614-633: `| v19 | orchestration_runs | per-issue batch results | ENH-2492 |`.
- `docs/reference/API.md` — in `## little_loops.session_store` (line 6970):
  bump "Current schema version: **18**" → **19** at line 6972; add
  `record_orchestration_run` to import block at line 6975; add subsection
  after line 7048. In `## little_loops.history_reader` (line 6527): add the
  two new functions to import block at line 6534; add subsections.
- `docs/reference/CLI.md` — extend `--kind` flag tables at lines 2245 and
  2253; add `ll-session recent --kind orchestration_run` example near
  line 2283.

### Configuration

- No `config-schema.json` or `.ll/ll-config.json` change required. Mirrors
  ENH-2458/2459's decision to skip the `analytics.capture.X` gate;
  `record_orchestration_run` accepts a `config=None` forward-compatibility
  stub parameter (matches `record_commit_event`'s `config=None` signature).

### Dependent Files (Callers/Importers)

- `scripts/little_loops/pytest_history_plugin.py:120` — sibling best-effort
  wrap; same `contextlib.suppress(Exception)` envelope.
- `scripts/little_loops/hooks/post_commit.py:85-101` — sibling whole-main
  `try/except Exception: return 0` wrap; same EPIC-1707 contract.
- `scripts/little_loops/hooks/user_prompt_submit.py:78-94` — sibling
  per-event `with contextlib.suppress(Exception):` pattern.

### Similar Patterns (Copy-Modify)

- `scripts/little_loops/session_store.py:record_commit_event` (line 1041-1091)
  — direct model for `record_orchestration_run` body. Same
  `INSERT OR IGNORE` + `_index`-on-rowcount idiom.
- `scripts/little_loops/history_reader.py:recent_commit_events` (line 524-559)
  — direct model for `recent_orchestration_runs` SELECT shape.
- `scripts/tests/test_session_store.py:_bootstrap_schema_at` (line 3075-3095)
  — direct model for the v18→v19 upgrade test.

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

### Codebase Research Findings (Proposed Solution)

_Added by `/ll:refine-issue --auto` — based on codebase analysis:_

- **Schema migration DDL position**: append v19 as the last entry of
  `_MIGRATIONS` (`session_store.py:208-545`). The block is a raw SQL string
  matching the issue's proposal verbatim. The runner
  `_apply_migrations()` (line 609-645) iterates `range(version,
  len(_MIGRATIONS))` and runs each under `BEGIN IMMEDIATE` with
  `_split_sql_statements` (line 579-589); meta is bumped via
  `INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)`
  (line 635-639). Reference DDL: v17 `commit_events` at lines 501-520,
  v18 `test_run_events` at lines 521-544.

- **Upsert choice**: the issue's `UNIQUE(run_id, issue_id)` maps onto the
  codebase's `INSERT OR IGNORE` convention (see `record_commit_event` at
  `session_store.py:1041-1091` for the canonical pattern: open a fresh
  `connect(db_path)`, run `INSERT OR IGNORE`, only call `_index()` when
  `cursor.rowcount == 1` to prevent FTS duplicates on retry, return
  `bool(cursor.rowcount)`). Mirror that exactly for `record_orchestration_run`.

- **PR URL is not in `OrchestratorState.to_dict()`** — see
  `parallel/types.py:251-262`. PR URLs live in `self._pr_ready_branches`
  (`parallel/orchestrator.py:134`), populated at line 1044-1045 from
  `branch_state["pr_url"]` which `_open_pr_for_branch` mutates in place at
  `orchestrator.py:1153` (note: function signature is at lines 1109-1114; the
  actual `pr_result.returncode == 0` mutation is at line 1153). Read from
  `self._pr_ready_branches.get(issue_id, {}).get("pr_url")`, NOT from
  `self.state`.

- **Wave label is a string**, not an int — `self.wave_label` is built as
  `f"Wave {wave_num}/{total_waves}"` at `cli/sprint/run.py:607` and passed
  into `ParallelOrchestrator(wave_label=…)`. Persist the label verbatim;
  the issue's `wave INTEGER` proposal is more SQL-friendly but breaks the
  existing wave-format. Recommend either changing the SQL to `wave TEXT`
  (matches reality) or pre-parsing to an int. **Open design choice** — see
  the open question in `Sources`/Implementation Steps below.

- **EPIC-1707 best-effort wrapping**: `record_*_event` functions do NOT
  internally catch exceptions. The `contextlib.suppress(Exception)` wrapper
  is applied at the **call site** (the CLI driver, the pytest plugin, or the
  hook). Canonical examples: `pytest_history_plugin.py:120-125` (single
  row), `hooks/user_prompt_submit.py:78-94` (multi-row, in-loop),
  `hooks/post_commit.py:85-101` (whole-main `try/except Exception: return 0`).
  Apply the same wrap at each flush point (the `finally:` block in
  `AutoManager.run`, in `_on_worker_complete`, and in
  `_cmd_sprint_run`).

- **Status mapping back from `IssueProcessingResult`**: `mark_completed`
  (`state.py:188-201`) does not preserve whether the outcome was
  `result.was_closed` (`done` vs `closed`), `result.was_blocked`, or
  `result.plan_created`. To capture this faithfully, flush from inside
  `AutoManager._process_issue` (`issue_manager.py:1385-1444`) — right after
  the `mark_completed`/`mark_failed` dispatch (line 1424-1442) — passing
  `status` explicitly from `result.was_closed` / `.success` /
  `.failure_reason` / `.was_blocked`. Batch-final flush (in `run()`'s
  `finally:`) is a workable fallback if the per-issue site proves too
  intrusive.

- **`IssueProcessingResult` shape** (`issue_manager.py:545-557`) carries
  `success: bool`, `duration: float`, `issue_id: str`, `was_closed: bool =
  False`, `was_blocked: bool = False`, `failure_reason: str = ""`,
  `corrections: list[str] = []`, `plan_created: bool = False`, `plan_path: str
  = ""`. The `_process_issue` dispatch at `issue_manager.py:1424-1442`
  chooses exactly one terminal action per call:
  - `was_closed` → `mark_completed(issue_id)` (no timing persisted)
  - `was_blocked` → log only, **no state mutation** (skipped/pending — flush
    with `status="skipped"` from `_process_issue`)
  - `success` → `mark_completed(issue_id, {"total": result.duration})`
  - `plan_created` → log only (awaiting approval — flush with
    `status="plan_created"`)
  - `failure_reason` → `mark_failed(issue_id, result.failure_reason)`

- **`AutoManager.run()` exit-code contract**: returns `0` for success / empty
  queue / all-skip, or `1` for fatal exception at `issue_manager.py:1328` or
  all `--only` issues gate-blocked at `issue_manager.py:1337-1338`. The
  `finally:` block at `issue_manager.py:1330-1333` runs in both branches and
  is the safe flush site regardless of return value.

- **Multi-issue wave timing is approximate**: at `cli/sprint/run.py:622` the
  multi-issue path writes `state.timing[issue_id] = {"total":
  orchestrator.execution_duration / len(wave)}` — wave duration divided by
  issue count, **not** per-issue worker duration. The orchestrator's
  `_on_worker_complete` flush (`parallel/orchestrator.py:1066-1070`) has
  `result.duration` available and is more accurate; for ll-sprint multi-issue
  waves, prefer the orchestrator's per-worker flush over a post-loop harvest
  from `state.timing`.

- **Multi-issue failure reason is constant string**: `run.py:625-626` writes
  `state.failed_issues[issue_id] = "Issue failed during wave execution"` —
  the per-issue `result.failure_reason` from the orchestrator is dropped at
  this boundary. Same fix as above (orchestrator's per-worker flush preserves
  `result.error`).

- **Sprint `state.skipped_blocked_issues` is sprint-only**: this field exists
  on the sprint state but not on the base `ProcessingState`. Sprint-only
  flush sites (`run.py:551`, `:658-659`) can use it for additional status
  fidelity — `status="skipped"` with `failure_reason=reason` if the issue was
  blocked.

- **Sequential-retry path** in `cli/sprint/run.py:630-660` calls
  `process_issue_inplace(info=issue, ...)` for each issue still in
  `actually_failed`. On retry success it `state.failed_issues.pop(...)` and
  re-appends to `state.completed_issues`; on retry blocked it pops and writes
  to `state.skipped_blocked_issues`. A retry-flush inside this loop captures
  the *final* outcome (success-after-retry), not the initial failure.

- **PR URL is `None` when `gh auth status` fails** (`orchestrator.py:1121-1128`):
  `_open_pr_for_branch` early-returns without populating `branch_state["pr_url"]`.
  The flush must handle `pr_url=None` cleanly (SQL accepts NULL on a `TEXT`
  column without an index collision; tests should assert no PR row but
  successful completion row).

- **`was_interrupted` branch orphans** at `parallel/orchestrator.py:927-931`:
  an interrupted worker appends to `self._interrupted_issues` but does **not**
  mark failed and does **not** mutate timing. To capture interrupted runs,
  emit a `orchestration_runs` row with `status="interrupted"` here (or
  post-loop in the orchestrator's main flow at the wave-final harvest).

- **`record_*_event` return values**: `record_commit_event` returns `bool`
  (`session_store.py:1041`); `record_test_run_event` returns `None`
  (`session_store.py:1171`). For idempotent tables (`commit_events`,
  `orchestration_runs` — both have UNIQUE constraints), the bool-of-insert
  style is appropriate; `record_orchestration_run` should follow that.

- **`_index()` truncates content to 512 chars at producer side**: the
  `content=f"{...}".strip()[:512]` pattern in both `record_commit_event`
  (line 1081) and `record_test_run_event` (line 1224). For
  `record_orchestration_run`, a meaningful `content` would be
  `f"{driver} {run_id} {issue_id} {status} {failure_reason or ''}".strip()[:512]`
  — captures enough for FTS to find rows by driver or status without
  bloating the search index.

- **Three `--kind` locations must stay in lockstep**: `_VALID_KINDS`
  (`session_store.py:104-118`), `_KIND_TABLE` (`session_store.py:119-130`),
  and **both** `cli/session.py` `--kind` `choices=[...]` literals (search at
  line 90, recent at line 114). Adding `"orchestration_run"` requires all
  four edits in the same commit, or `argparse` / `recent()` will reject the
  new kind. `_VALID_KINDS` currently has 12 entries (tool, file, issue, loop,
  correction, message, skill, cli, snapshot, commit, test_run, …) — verify
  the issue's addition is consistent with the surrounding literals.

- **`_apply_migrations` re-checks version under lock and stamps per-entry**:
  after `BEGIN IMMEDIATE` (line 625) it re-reads the version (line 633) to
  handle a fresh-DB race, then `for index in range(version, len(_MIGRATIONS)):`
  (line 635) advances the `meta(key='schema_version')` stamp *after each
  migration* (line 638-641). Crash before any statement leaves the stamp
  unchanged; crash mid-loop leaves the stamp at the last completed entry.
  This is why v18→v19 upgrade tests can rely on
  `_bootstrap_schema_at(db, 18)` + `ensure_db(db)` to land the new table.

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

### Codebase Research Findings (Implementation Steps)

_Added by `/ll:refine-issue --auto` — based on codebase analysis:_

1. **Schema migration lands**: append v19 block to `_MIGRATIONS`
   (`scripts/little_loops/session_store.py:208-545`); bump `SCHEMA_VERSION =
   19` (`session_store.py:102`). Verification test: add
   `TestOrchestrationSchema.test_v18_db_upgrades_gains_orchestration_runs`
   mirroring `test_v14_db_upgrades_gains_test_run_events`
   (`test_session_store.py:3607-3619`); use `_bootstrap_schema_at(db, 18)`
   (line 3075-3095), then `ensure_db(db)` and assert
   `"orchestration_runs" in {r[0] for r in conn.execute("SELECT name FROM
   sqlite_master WHERE type='table'")}`.

2. **Kind registry**: add `"orchestration_run"` to `_VALID_KINDS`
   (`scripts/little_loops/session_store.py:104`) and
   `"orchestration_run": "orchestration_runs"` to `_KIND_TABLE`
   (`scripts/little_loops/session_store.py:119`). Also add `"orchestration_run"`
   to `__all__` (line 60).

3. **Record function**: add `record_orchestration_run` to
   `scripts/little_loops/session_store.py`. Mirror `record_commit_event`
   (line 1041-1091) — own `connect()`, `INSERT OR IGNORE INTO
   orchestration_runs(...)` keyed on `UNIQUE(run_id, issue_id)`, conditional
   `_index()` on `cursor.rowcount == 1`. Keyword-only args after `db_path`
   match the `record_test_run_event` style (line 1171-1233). Returns `bool`.

4. **`ll-auto` flush**: in `scripts/little_loops/issue_manager.py:AutoManager.run()`
   `finally:` block (line 1330-1333), iterate
   `state_manager.state.completed_issues` and
   `state_manager.state.failed_issues`; for each, emit a row with
   `driver="ll-auto"`, `status` derived from the underlying
   `IssueProcessingResult` (best fidelity — pass `status` through
   `_process_issue`'s `mark_*` path), `duration_s=state.timing[issue_id]["total"]`,
   `failure_reason=state.failed_issues.get(issue_id)`. Wrap entire loop in
   `with contextlib.suppress(Exception): manager.logger.warning(...)`.

5. **`ll-sprint` flush**: in `scripts/little_loops/cli/sprint/run.py:_cmd_sprint_run()`
   post-wave-loop (after line 680 `_save_sprint_state`, before line 710
   `_cleanup_sprint_state`). For each issue processed in this batch, write a
   row with `driver="ll-sprint"`,
   `wave=self.wave_label` (`f"Wave {wave_num}/{total_waves}"`). Best-effort
   wrapped.

6. **`ll-parallel` flush**: at
   `scripts/little_loops/parallel/orchestrator.py:_on_worker_complete()`
   (line 914-1087). After `self.queue.mark_completed/mark_failed` and the
   `self.state.timing[result.issue_id] = {...}` write (line 1066-1070), also
   call `record_orchestration_run(driver="ll-parallel", wave=self.wave_label,
   pr_url=self._pr_ready_branches.get(result.issue_id, {}).get("pr_url"),
   ...)`. Wrap in `with contextlib.suppress(Exception):` so a DB failure
   never derails the worker.

7. **Reader functions**: in `scripts/little_loops/history_reader.py` add
   `recent_orchestration_runs(driver=None, issue_id=None, since=None,
   limit=50) -> list[OrchestrationRun]` mirroring `recent_commit_events`
   (line 524-559); add `aggregate_orchestration_runs(group_by=Literal["driver",
   "issue_id","status"], since=None)` mirroring `summarize_skills`
   (line 472). Define `@dataclass class OrchestrationRun` near
   `CommitEvent` (line 124) / `RunEvent` (line 138). Update public-API
   docstring (lines 1-42).

8. **CLI**: in `scripts/little_loops/cli/session.py` add `"orchestration_run"`
   to the `choices=[…]` list at line 90 (`search` `--kind`) and at line 114
   (`recent` `--kind`). No argparse code change beyond the choices list —
   routing flows through `_VALID_KINDS` → `recent()`
   (`session_store.py:1268`) → table from `_KIND_TABLE`. Users can now run
   `ll-session recent --kind orchestration_run` and
   `ll-session search --fts "<issue_id>" --kind orchestration_run`.

9. **Tests** (additive, no existing tests modified):
   - `scripts/tests/test_session_store.py`: add
     `TestRecordOrchestrationRun` (round-trip, dedupe on `(run_id, issue_id)`,
     FTS-searchable by `failure_reason`); add `TestOrchestrationSchema`
     (v18→v19 upgrade).
   - `scripts/tests/test_history_reader.py`: add to `TestNewEventReaders`
     (line 1378+) two tests: `test_recent_orchestration_runs_filters` and
     `test_recent_orchestration_runs_empty_on_missing_db` (mirrors line
     1508-1523).
   - `scripts/tests/test_ll_session.py`: add
     `test_recent_kind_orchestration_run_accepted` (mirrors line 78);
     add `test_recent_kind_orchestration_run_outputs_row` (mirrors line
     949); add `test_search_kind_orchestration_run_filters` (mirrors line
     977).
   - `scripts/tests/test_cli.py::TestMainAutoIntegration` (line 279): add
     `test_main_auto_db_absent_still_succeeds` — point `LL_HISTORY_DB` at an
     unwritable path and assert exit 0.
   - `scripts/tests/test_parallel_cli.py::TestParallelNormalRun` (line 183):
     add `test_parallel_records_wave_and_pr_url` — mock `_on_worker_complete`;
     assert PR URL propagates into `orchestration_runs` row.

10. **Docs** (additive):
    - `docs/ARCHITECTURE.md` — add v19 row to schema-versions table at lines
      614-633: `| v19 | orchestration_runs | per-issue batch results | ENH-2492 |`.
    - `docs/reference/API.md` — in `## little_loops.session_store` (line 6970):
      bump "Current schema version: **18**" → **19** at line 6972; add
      `record_orchestration_run` to import block at line 6975; add subsection
      after line 7048. In `## little_loops.history_reader` (line 6527): add
      the two new functions to import block at line 6534; add subsections.
    - `docs/reference/CLI.md` — extend `--kind` choices tables at lines 2245
      and 2253; add `ll-session recent --kind orchestration_run` example near
      line 2283.

11. **Status fidelity for `ll-auto`** (per-issue flush alternative): the
    `run()` finally-block flush loses `result.was_closed` /
    `result.was_blocked` / `result.plan_created` discrimination because
    `mark_completed` (`state.py:188-201`) does not persist those states.
    For higher fidelity, add a `record_orchestration_run(status=..., ...)`
    call **inside** `AutoManager._process_issue`
    (`issue_manager.py:1385-1444`) immediately after the dispatch at line
    1424-1442 — passing `status` explicitly derived from
    `result.was_closed` / `result.was_blocked` / `result.plan_created` /
    `result.success` / `result.failure_reason`. If the per-issue site proves
    too intrusive, the `finally:`-block fallback is acceptable but only
    emits `status="completed"` or `status="failed"` (binary partition).

12. **Sprint retry flush** (additive): inside the sequential-retry loop at
    `cli/sprint/run.py:630-660`, each retry's `IssueProcessingResult` is
    the *final* outcome. To preserve retry semantics, emit
    `record_orchestration_run` inside that loop after `process_issue_inplace`
    returns — `run.py:649` is the natural insertion point — with
    `status` derived from the retry's `result` (success-after-retry writes
    `status="completed"`, retry-blocked writes `status="skipped"`). Wrap in
    `contextlib.suppress(Exception)` so a DB failure doesn't abort the retry
    loop.

13. **`wave` column type decision** (open design choice): the proposed
    schema has `wave INTEGER` but `self.wave_label` is built as
    `f"Wave {wave_num}/{total_waves}"` (string). Two viable resolutions:
    (a) change schema column to `wave TEXT` — preserves human-readable label
    without parsing; or (b) split into two columns `wave_num INTEGER,
    total_waves INTEGER` — more SQL-friendly for aggregations like
    "median issues per wave". Recommendation: `wave TEXT` for v1
    (lower-risk, matches existing display format); defer the split to a
    follow-on if aggregations need it.

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
- `/ll:refine-issue` - 2026-07-06T23:47:05 - `8b0fb94d-2a13-40c0-a03a-0886bca177ac.jsonl`
- `/ll:refine-issue` - 2026-07-06T19:14:36 - `29927953-330a-400d-9d73-7c6c5c33aac1.jsonl`
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
