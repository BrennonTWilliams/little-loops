---
id: ENH-2492
title: Capture orchestration run outcomes (ll-auto/ll-parallel/ll-sprint) into history.db
type: ENH
priority: P2
status: open
discovered_date: 2026-07-05
captured_at: '2026-07-05T00:00:00Z'
discovered_by: capture-issue
parent: EPIC-2457
decision_needed: false
labels:
- enhancement
- history-db
- orchestration
- captured
confidence_score: 96
outcome_confidence: 77
score_complexity: 18
score_test_coverage: 23
score_ambiguity: 18
score_change_surface: 18
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
  - Line 60 `__all__` — add `"record_orchestration_run"` (matches older
    convention; v20/ENH-2461's `record_usage_event` is NOT in `__all__`, so
    optional — mirror v20 style for consistency).
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

_Wiring pass added by `/ll:wire-issue`:_

- **Anti-pattern (do NOT add)**: `_REBUILD_TABLES` at
  `session_store.py:2833, 2865, 2886`. The `usage_events` table is the ONLY
  sibling in `_REBUILD_TABLES` because it's parser-derived
  (`_backfill_usage_events` at line 1878-1943). Direct-write tables
  (`commit_events`, `test_run_events`, and the proposed `orchestration_runs`)
  are explicitly excluded — see comment at `session_store.py:2853-2854`
  ("Issue/loop/commit/cli/file/test_run tables are outside raw_events'
  scope"). Adding `orchestration_runs` to `_REBUILD_TABLES` would be a bug.

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

_Wiring pass added by `/ll:wire-issue`:_

- **Correction to "all four locations" claim**: Both argparse `choices=[…]`
  literals at `cli/session.py:103` and `:115` use `list(VALID_KINDS)` (i.e.,
  pull dynamically from `session_store.VALID_KINDS`). Adding `"orchestration_run"`
  to `VALID_KINDS` propagates automatically — the argparse `choices` literals
  do NOT need separate edits. The 3rd-pass Codebase Research Finding
  (lines 266-273) stating a "four-location lockstep" is wrong on current HEAD.
  Only `VALID_KINDS` and `_KIND_TABLE` need the explicit edit.

- **Export parser `--tables` help text** (`cli/session.py:222-232`): The
  `export_parser.add_argument("--tables", ...)` help text lists valid type
  names. Current text omits `commit_event`/`test_run_event`/`usage_event` even
  though they ARE valid via `_EXPORT_TABLE_MAP`. Add `orchestration_run_event`
  here for parity (and optionally close the existing v20 drift by including
  the other three).

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

_Wiring pass added by `/ll:wire-issue`:_

- **Use v20 sibling as the pattern, not v18**. The closest analog is
  `TestUsageEventsSchema` at `test_session_store.py:3215-3245` (not
  `TestRecordTestRunEvent` at line 3549 as the issue cites), since v20 is
  the most-recent house style.
- **`_bootstrap_schema_at(db, N)` correction**: Current `SCHEMA_VERSION` is
  **20** (not 18/19 as the issue cites). The upgrade test should bootstrap
  at the live pre-`orchestration_runs` version and assert the v21 migration:
  `_bootstrap_schema_at(db, 20)` then `ensure_db(db)`. Re-verify the live
  constant at `session_store.py:207` before quoting in a commit.
- `scripts/tests/test_orchestrator.py::TestEpicBranchCompletion::test_on_worker_complete_records_orchestration_run`
  — direct unit test for the orchestrator flush site (the issue's 4th-pass
  finding already flagged this). Use the `orchestrator` fixture at lines
  121-145 and mirror `TestEpicBranchCompletion::test_no_merge_when_epic_branches_disabled`
  at line 1533-1546 pattern (construct `WorkerResult`, mock
  `record_orchestration_run`, call `_on_worker_complete`, assert on the
  writer call). Faster than driving through `test_parallel_cli.py`.
- `scripts/tests/test_cli_sprint.py::TestIssueWallClockTimeout::test_wall_clock_timeout_records_orchestration_run`
  — wall-clock-timeout flush test. Mirror `test_run_issue_with_wall_clock_timeout_catches_timeout_and_returns_failure`
  at `test_cli_sprint.py:654` (patch `signal`, `process_issue_inplace`, raise
  `IssueWallClockTimeout`, assert synthetic failure flushed with
  `failure_reason="WALL_CLOCK_TIMEOUT"`).
- `scripts/tests/test_sprint_integration.py::TestSprintErrorRecovery::test_sprint_sequential_retry_records_orchestration_runs`
  — sequential-retry flush test. Mirror
  `test_sprint_sequential_retry_after_parallel_failure` at line 1046-1070
  (use the `MockQueue`/`MockOrchestrator`/`mock_process_inplace` pattern,
  patch `record_orchestration_run`, assert retry outcomes are recorded
  including success-after-retry).
- `scripts/tests/test_ll_session.py::test_export_includes_orchestration_run_table`
  — explicit test for the `_EXPORT_TABLE_MAP` edit. There is currently no
  `test_export_*` in `test_ll_session.py` (the existing export tests are in
  `test_cli_history.py:198` and `test_issue_history_cli.py:763+`, which
  cover `ll-history` export, NOT `ll-session` table export). Add a new
  test that records a row, runs `ll-session export --tables orchestration_run`,
  and asserts the row appears in the output. Without this, the
  `_EXPORT_TABLE_MAP` edit can regress silently.

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

_Wiring pass added by `/ll:wire-issue`:_

- `docs/guides/HISTORY_SESSION_GUIDE.md` — **NOT** in the issue's docs list
  but is the user-facing guide that lists `--kind` values and the
  schema-versions table. Four locations to update on current HEAD:
  - Schema-versions table (lines 60-76): add v21 row mirroring the new
    `orchestration_runs` migration.
  - "What gets recorded" table (lines 79-99): add `orchestration_runs` row.
  - `--kind` value list in FTS examples (line 170): add `orchestration_run`.
  - `--tables` choices text (line 208): add `orchestration_run_event`.
  Note: this guide already lists `commit, test_run, usage` as `--kind`
  values — confirm `orchestration_run` lands here for consistency with
  `VALID_KINDS`.

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

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/verify_kinds.py:40-46` — explicit gate that
  re-globs `_MIGRATIONS` for every `CREATE TABLE` and asserts the table
  appears in `_KIND_TABLE` OR `_KINDLESS_TABLES`. Adding `orchestration_runs`
  to `_MIGRATIONS` without also updating `_KIND_TABLE` will exit 1 here.
  This gate is **not** named in the issue's Test Files section.
- `scripts/tests/test_verify_kinds.py::TestRun::test_clean_state_returns_zero`
  (line 19-23) — the enforced test for the above gate. Run as part of
  `python -m pytest scripts/tests/`.

### Similar Patterns (Copy-Modify)

- `scripts/little_loops/session_store.py:record_commit_event` (line 1041-1091)
  — direct model for `record_orchestration_run` body. Same
  `INSERT OR IGNORE` + `_index`-on-rowcount idiom.
- `scripts/little_loops/history_reader.py:recent_commit_events` (line 524-559)
  — direct model for `recent_orchestration_runs` SELECT shape.
- `scripts/tests/test_session_store.py:_bootstrap_schema_at` (line 3075-3095)
  — direct model for the v18→v19 upgrade test.

### Codebase Research Findings (Verification Pass)

_Added by `/ll:refine-issue --auto` (verification pass, 2026-07-07) — anchor
corrections and additional file inventory:_

- **Stale anchor — `docs/reference/API.md` heading lines**: The prior
  Implementation Step 10 references `## little_loops.session_store` at line 6970
  and `## little_loops.history_reader` at line 6527. The current `API.md` has
  those headings at **line 7023** and **line 6580** respectively. The 6970/6527
  lines fall inside unrelated sections (a `SectionProvider` dataclass and an
  `import` statement inside a code example). Correct the Implementation Step 10
  doc anchors before quoting them in commits.
- **Stale anchor — `state.py:26`**: `ProcessingState` is at line 25 (off by one);
  the `:26` reference in the Summary section should be `:25`.
- **Off-by-one/two — `cli/session.py` `--kind` choices literals**: The `search`
  `--kind` `choices=[…]` list opens at line **92** (not 90); the `recent`
  `--kind` `choices=[…]` list opens at line **115** (not 114). The `--kind`
  keyword itself is at the lines quoted in the issue body, so the discrepancy is
  literal-vs-keyword, not material.
- **NEW — `_EXPORT_TABLE_MAP` / `_EXPORT_DEFAULT_TABLES`
  (`session_store.py:2791-2814`)**: For `ll-session export` parity, add
  `("orchestration_run", "orchestration_runs", "ended_at")` to the export table
  map. Without this, `orchestration_runs` rows will be invisible to
  `ll-session export` and downstream tooling that consumes those exports. This
  is **not** in the prior Implementation Steps — adding it here.
- **NEW — `_run_issue_with_wall_clock_timeout` flush site
  (`cli/sprint/run.py:44-88`)**: This function returns a synthetic
  `IssueProcessingResult` with `failure_reason="WALL_CLOCK_TIMEOUT"`. It is a
  third exit path distinct from the wave orchestrator and the sequential-retry
  loop, and must be flushed to `orchestration_runs` with `status="failed"` and
  `failure_reason="WALL_CLOCK_TIMEOUT"`. Wire the flush at the call sites (around
  `run.py:88` and any other caller of `_run_issue_with_wall_clock_timeout`).
- **NEW — `WorkerResult` shape (`parallel/types.py:74-99`)**: The full
  per-worker result has `was_corrected`, `corrections`, `should_close`,
  `interrupted`, `was_blocked` fields that the issue's `IssueProcessingResult`
  discussion didn't enumerate. The orchestrator's per-worker flush site has
  access to all of them; pass `status="interrupted"` when
  `result.interrupted is True` (currently orphaned at
  `parallel/orchestrator.py:927-931`).
- **`_VALID_KINDS` has 11 entries, not 12**: The current set is `tool, file,
  issue, loop, correction, message, skill, cli, snapshot, commit, test_run`.
  `snapshot` is a "ghost kind" — present in `_VALID_KINDS` (line 114) but **not**
  in `_KIND_TABLE` (lines 119-130) and **not** in the `cli/session.py --kind`
  argparse `choices` lists. Adding `orchestration_run` brings the count to 12
  matching the issue's claim, but for the wrong reason — the implementer must
  add to **all four** locations in the same commit (`_VALID_KINDS`,
  `_KIND_TABLE`, and **both** `cli/session.py --kind choices` literals).

### Codebase Research Findings (Anchor Drift Verification — 2026-07-11)

_Added by `/ll:refine-issue --auto` (4th pass) — line-number drift check against
current HEAD. No structural drift anywhere: every cited function/class/table
still exists with the same name, signature, and behavior. `SCHEMA_VERSION` is
still `18` — the proposed v19 slot remains open and uncontested. Numeric drift
by file:_

- **`parallel/orchestrator.py` — significant drift (~53–66 lines), re-locate
  by name before citing lines in a commit**:

  | Cited element | Issue's line(s) | Actual line(s) | Drift |
  |---|---|---|---|
  | `_on_worker_complete()` | 914-1087 | **967-1152** | +53 / +65 |
  | `interrupted` early-return | 927-931 | **980-984** | +53 |
  | `self._pr_ready_branches[...] = branch_state` | 1044-1045 | **1102** | +57 |
  | Timing write (`self.state.timing[...] = {...}`) | 1066-1070 | **1132-1135** | +65 |
  | `_open_pr_for_branch` signature | 1109-1114 | **1174-1179** | +65 |
  | `_open_pr_for_branch` docstring | 1117 | **1182** | +65 |
  | `pr_result.returncode == 0` mutation | 1153/1160 | **1217** | +57/+64 |
  | `self.wave_label = wave_label` | 103 | **109** | +6 |

  Control flow is unchanged (overlap unregister → interrupted early-return →
  close-issue branch → success branch → failure branch → EPIC-completion
  check → timing write → cleanup → event emission), and `_open_pr_for_branch`
  still mutates `branch_state["pr_url"]` in place exactly as documented — only
  the absolute line numbers moved, consistent with unrelated code (an
  EPIC-completion merge block) having been inserted above line 967 since the
  last pass. **This means the concrete code blocks in Implementation Steps 15
  and 18 (which say "after the timing write at lines 1066-1070" and "at
  `parallel/orchestrator.py:927-931`") should be inserted at the current
  locations (1132-1135 and 980-984 respectively), not the cited ones.**

- **`cli/sprint/run.py` — moderate drift (~14–22 lines)**: `wave_label=f"Wave
  {wave_num}/{total_waves}"` composition now at **line 629** (issue cited 607).
  Multi-issue wave-average timing overwrite now at **lines 643-645** (issue
  cited 621-623) — still confirmed true. Constant failure-reason string
  `"Issue failed during wave execution"` now at **line 648** (issue cited
  625-626) — still confirmed true. `state.skipped_blocked_issues[...]` now at
  lines 565, 680, 718-719 (issue cited 551, 658-659). Implementation Step 16's
  code block ("after `_save_sprint_state(state, logger)` at line 680") should
  anchor on the current line 680+ location, not 680 from the prior pass
  (coincidentally close but re-verify before committing).

- **Everything else — 0–25 lines of drift, within normal noise**:
  `session_store.py` (`SCHEMA_VERSION`, `_MIGRATIONS`, `record_commit_event`,
  `_EXPORT_TABLE_MAP`, `_apply_migrations`), `state.py`, `issue_manager.py`
  (`AutoManager.run()` finally block, `_process_issue`), `cli/auto.py`,
  `cli/parallel.py`, `cli/sprint/__init__.py`, and `history_reader.py` all
  match within a few lines of the issue's citations — no re-verification
  needed beyond normal implementation-time sanity checks.

- **NEW — `scripts/tests/test_orchestrator.py` exists** as a dedicated
  orchestrator unit-test file, not listed in the issue's Test Files section
  (which only names `test_parallel_cli.py::TestParallelNormalRun` for
  orchestrator-level coverage). Since the primary flush site
  (`_on_worker_complete`) lives in `parallel/orchestrator.py`, a direct unit
  test in `test_orchestrator.py` (mocking `record_orchestration_run` and
  asserting it's called with the right `status`/`wave`/`pr_url` on a
  synthetic `WorkerResult`) would be a faster, more targeted test than driving
  it through the CLI-level `test_parallel_cli.py` test proposed in step 9.
  Consider adding both, or substituting the unit test for the CLI test if the
  CLI-level one proves slow/flaky.

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
    wave TEXT,                        -- e.g. "Wave 1/3"; parallel/sprint only, NULL for ll-auto
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
  existing wave-format.

  > **Selected:** `wave TEXT` — persist `self.wave_label` verbatim; see
  > Decision Rationale below.

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

### Codebase Research Findings (Proposed Solution — verification pass)

_Added by `/ll:refine-issue --auto` (verification pass, 2026-07-07) — refinements
to the proposed solution:_

- **`_EXPORT_TABLE_MAP` must include `orchestration_runs`**: For `ll-session
  export` parity with sibling tables (`commit_events` and `test_run_events`),
  add `("orchestration_run", "orchestration_runs", "ended_at")` to the export
  table map at `session_store.py:2791-2814`. Without this entry, `orchestration_runs`
  rows will be invisible to JSONL/CSV export and to any downstream tooling
  that consumes those exports (e.g., `ll-history`, `ll-ctx-stats` consumers,
  analytics dashboards).
- **Multi-issue wave timing overwrites orchestrator's accurate timing**: The
  claim that `cli/sprint/run.py:622` writes the wave-averaged duration is
  correct, but the framing understates the issue — the orchestrator's
  `_on_worker_complete` already writes the **accurate** `result.duration` into
  `self.state.timing[result.issue_id]` at `parallel/orchestrator.py:1067-1070`,
  and **then** the sprint CLI overwrites it at `run.py:621-623` with the
  wave-average. Both `ParallelOrchestrator.state.timing` and `SprintState.timing`
  end up holding the wave-averaged value. The flush must come from the
  orchestrator's `_on_worker_complete` (which sees `result.duration` accurately)
  rather than post-loop harvest from `SprintState.timing`.
- **Wall-clock timeout is a separate exit path**: `_run_issue_with_wall_clock_timeout`
  (`cli/sprint/run.py:44-88`) returns a synthetic `IssueProcessingResult` with
  `failure_reason="WALL_CLOCK_TIMEOUT"` — a path distinct from the wave
  orchestrator and the sequential-retry loop. The proposed producer-wiring
  must cover this path too: at the caller (around `run.py:88`), emit
  `record_orchestration_run(status="failed", failure_reason="WALL_CLOCK_TIMEOUT")`.
- **`wave TEXT` vs split columns — recommendation refined**: Three grounds for
  `wave TEXT` over `wave INTEGER` (or split): (1) `self.wave_label` is already
  `f"Wave {wave_num}/{total_waves}"` — a string — so persisting verbatim avoids
  a parse step; (2) the "split into `wave_num INTEGER, total_waves INTEGER`"
  alternative would enable aggregations like "median issues per wave," but
  there is no demonstrated query pressure yet — defer to a follow-on if
  aggregations need it; (3) `_VALID_KINDS` and `_KIND_TABLE` migrations are
  already complex — `TEXT` is the lowest-risk v1 choice. Note also: only
  `ll-sprint` populates `wave`; `ll-auto` and `ll-parallel` (when not invoked
  through sprint) leave it `NULL` — design accordingly.
- **PR URL on `_open_pr_for_branch` failure paths**: Verified all early-return
  paths preserve `branch_state["pr_url"] = None`: (a) `gh auth status` fails
  (`orchestrator.py:1127-1129`); (b) `gh pr create` non-zero exit
  (`orchestrator.py:1155-1156`); (c) `FileNotFoundError`/`TimeoutExpired`
  (`orchestrator.py:1157-1160`). The flush must safely handle `pr_url=None`
  (SQL `TEXT` column accepts NULL; tests should assert no PR row but successful
  completion row).
- **`record_*_event` exception model — refined**: Verified that
  `record_commit_event` and `record_test_run_event` do **not** internally catch
  exceptions; the `contextlib.suppress(Exception)` envelope sits at the **call
  site**. The existing `cli_event_context(...)` wrappers at `cli/auto.py:33`,
  `cli/parallel.py:44`, and `cli/sprint/__init__.py:56` already swallow the
  surrounding exception, but the new flush must use `contextlib.suppress`
  at its own call site because (a) `_on_worker_complete` runs inside a worker
  pool thread, and (b) `_cmd_sprint_run`'s post-wave-loop flush happens in a
  long-lived loop where each iteration must be independently guarded.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-11.

**Selected**: `wave TEXT` (option (a) from Implementation Step 13), over splitting
into `wave_num INTEGER, total_waves INTEGER` (option (b)).

**Reasoning**: `ParallelOrchestrator.wave_label` is declared `str | None`
(`parallel/orchestrator.py:90`) and is always constructed as the pre-formatted
string `f"Wave {wave_num}/{total_waves}"` (`cli/sprint/run.py:629`); persisting
it verbatim needs no parse/format step at either write or read time. No caller
in this issue's scope needs numeric wave aggregation ("median issues per
wave"), so the extra schema/query complexity of a split-column design buys
nothing yet — it can be added as a follow-on if that query pressure
materializes. `TEXT` also keeps the v19 migration minimal alongside the
already-nontrivial `_VALID_KINDS`/`_KIND_TABLE` four-location wiring (see
Codebase Research Findings above).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| (a) `wave TEXT` | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| (b) split `wave_num`/`total_waves` INTEGER | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- (a) `wave TEXT`: matches `wave_label`'s existing string type and format
  exactly (`orchestrator.py:90`, `run.py:629`); no parsing needed anywhere in
  the producer wiring (Steps 15–17 already pass `self.wave_label` /
  `wave_label` straight through as a string).
- (b) split columns: would require parsing `"Wave N/M"` back into two ints at
  every flush site (or restructuring `wave_label` itself, a wider blast
  radius), and no acceptance criterion or query in this issue needs the
  numeric form.

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

13. **`wave` column type — decided (see Decision Rationale in Proposed
    Solution)**: `wave TEXT`, not `wave INTEGER`. `self.wave_label` is built
    as `f"Wave {wave_num}/{total_waves}"` (string); persist it verbatim — no
    parse step at any flush site. The split-column alternative
    (`wave_num INTEGER, total_waves INTEGER`) is deferred to a follow-on if
    numeric wave aggregation ever needs it; nothing in this issue's
    acceptance criteria requires it.

### Codebase Research Findings (Implementation Steps — verification pass)

_Added by `/ll:refine-issue --auto` (verification pass, 2026-07-07) — concrete
flush blocks, additional flush sites, and `_EXPORT_TABLE_MAP` wiring:_

14. **`_EXPORT_TABLE_MAP` / `_EXPORT_DEFAULT_TABLES` wiring
    (`session_store.py:2791-2814`)**: Add `("orchestration_run",
    "orchestration_runs", "ended_at")` to the export table map. Without this
    entry, `orchestration_runs` rows are invisible to `ll-session export` and
    any JSONL/CSV-consuming tooling. Implementation:

    ```python
    # in _EXPORT_TABLE_MAP (or _EXPORT_DEFAULT_TABLES, depending on schema):
    ("orchestration_run", "orchestration_runs", "ended_at"),
    ```

    This single edit unblocks downstream consumers (ll-history, ll-ctx-stats,
    analytics dashboards) that read export outputs.

15. **Concrete flush block at `parallel/orchestrator.py:_on_worker_complete`**
    (after the timing write at lines 1066-1070):

    ```python
    # ENH-2492: flush per-issue outcome into history.db (best-effort).
    with contextlib.suppress(Exception):
        from little_loops.session_store import record_orchestration_run

        branch_state = (
            self._pr_ready_branches.get(result.issue_id, {})
            if hasattr(self, "_pr_ready_branches") else {}
        )
        record_orchestration_run(
            resolve_history_db(),
            run_id=f"{self.wave_label or 'wave'}-{result.issue_id}",
            driver="ll-parallel",
            issue_id=result.issue_id,
            status="completed" if result.success else "failed",
            failure_reason=result.error,
            duration_s=result.duration,
            wave=self.wave_label,
            pr_url=branch_state.get("pr_url"),
        )
    ```

    The `hasattr(self, "_pr_ready_branches")` guard handles the case where
    `_pr_ready_branches` was never populated (no `gh` configured, single-issue
    flows). `resolve_history_db()` is the canonical helper that honors the
    `LL_HISTORY_DB` env override.

16. **Concrete flush block at `cli/sprint/run.py:_cmd_sprint_run`**
    (after `_save_sprint_state(state, logger)` at line 680, before the
    `if wave_num < total_waves:` block):

    ```python
    _save_sprint_state(state, logger)
    # ENH-2492: belt-and-suspenders flush of completed/failed issues.
    # The orchestrator's _on_worker_complete is the primary write site;
    # this catches sequential-retry outcomes (cli/sprint/run.py:649) and
    # wall-clock timeouts (cli/sprint/run.py:44-88).
    if wave_ids:
        with contextlib.suppress(Exception):
            from little_loops.session_store import record_orchestration_run

            wave_label = f"Wave {wave_num}/{total_waves}"
            for issue_id in wave_ids:
                status = "completed" if issue_id in actually_completed else "failed"
                record_orchestration_run(
                    resolve_history_db(),
                    run_id=f"{wave_label}-{issue_id}",
                    driver="ll-sprint",
                    issue_id=issue_id,
                    status=status,
                    failure_reason=state.failed_issues.get(issue_id),
                    duration_s=state.timing.get(issue_id, {}).get("total"),
                    wave=wave_label,
                )
    if wave_num < total_waves:
        ...
    ```

    Note: `state.timing[issue_id]` here may be the wave-averaged duration
    (`orchestrator.execution_duration / len(wave)`) rather than the per-worker
    accurate value — the orchestrator's `_on_worker_complete` flush (step 15)
    is the more accurate path. This post-loop flush is a fallback / safety net
    for sequential-retry outcomes that don't pass through `_on_worker_complete`.

17. **`_run_issue_with_wall_clock_timeout` flush site
    (`cli/sprint/run.py:44-88`)**: This function returns a synthetic
    `IssueProcessingResult` with `failure_reason="WALL_CLOCK_TIMEOUT"`. It is
    a third exit path distinct from the wave orchestrator and the
    sequential-retry loop. At the call site (around `run.py:88`), wrap the
    result handling in:

    ```python
    result = _run_issue_with_wall_clock_timeout(...)
    if result.failure_reason == "WALL_CLOCK_TIMEOUT":
        with contextlib.suppress(Exception):
            from little_loops.session_store import record_orchestration_run

            record_orchestration_run(
                resolve_history_db(),
                run_id=f"wall-clock-{result.issue_id}",
                driver="ll-sprint",
                issue_id=result.issue_id,
                status="failed",
                failure_reason="WALL_CLOCK_TIMEOUT",
                duration_s=result.duration,
                wave=f"Wave {wave_num}/{total_waves}",
            )
    ```

18. **Interrupted-run flush at `_on_worker_complete` early-return
    (`parallel/orchestrator.py:927-931`)**: The early-return for
    `result.interrupted=True` currently leaves no `orchestration_runs` row.
    Insert a flush before the `return` so interrupted runs are recorded:

    ```python
    if result.interrupted:
        with contextlib.suppress(Exception):
            from little_loops.session_store import record_orchestration_run

            record_orchestration_run(
                resolve_history_db(),
                run_id=f"{self.wave_label or 'wave'}-{result.issue_id}",
                driver="ll-parallel",
                issue_id=result.issue_id,
                status="interrupted",
                failure_reason="Worker interrupted",
                duration_s=result.duration,
                wave=self.wave_label,
            )
        self._interrupted_issues.append(result.issue_id)
        return
    ```

    Note: the issue's prior text described this as a separate harvest — but
    `_on_worker_complete` is the only place that sees interrupted
    `WorkerResult`s before they're aggregated, so the flush MUST live here,
    not at a wave-final harvest.

19. **Test for `_EXPORT_TABLE_MAP` parity**: Add to `test_ll_session.py`:

    ```python
    def test_export_includes_orchestration_run_table(self, tmp_path: Path) -> None:
        """ENH-2492: ll-session export includes orchestration_runs rows."""
        from little_loops.session_store import record_orchestration_run

        db = tmp_path / "history.db"
        record_orchestration_run(
            db, run_id="r1", driver="ll-auto", issue_id="ENH-2492",
            status="completed", duration_s=10.0,
        )
        # run `ll-session export --tables orchestration_run` and assert row appears
    ```

    Without this test, the `_EXPORT_TABLE_MAP` edit (step 14) can regress
    silently.

### Codebase Research Findings (Anchor Drift Verification — 2026-07-16, pass 6)

_Added by `/ll:refine-issue --auto` (6th pass, same-day) — focused re-verification
after the 5th pass shipped. The 5th pass's verification already recorded all
material drifts through that point; this pass is a no-net-new-findings
confirmation, plus one minor line-number update that the 5th pass did not pin._

- **Material drift on `cli/sprint/run.py` (~+95 lines since the 4th/5th pass
  citations)**. The 5th pass cited `wave_label=f"Wave {wave_num}/{total_waves}"`
  at `run.py:629`. Current HEAD has this composition at **`run.py:724`**
  (`ParallelOrchestrator(wave_label=…)` is invoked there). The other two sites
  that compose the same wave label string are now at `run.py:671` (the
  warning path) and `run.py:674, 792, 796` (the completed-logging paths), all
  of which use the same `f"Wave {wave_num}/{total_waves}"` template. The
  ~95-line jump is most likely an artifact of the same ENH-2581 work that
  widened `_EXPORT_TABLE_MAP` (the file gained an unrelated sprint/state
  block above the wave loop). Re-locate every `run.py` citation by the
  function name (`_cmd_sprint_run`, `_run_issue_with_wall_clock_timeout`,
  `ParallelOrchestrator(...)` call site) rather than the line number when
  implementing — concrete line numbers from prior passes have all moved
  inside this file but the function-level structure is unchanged.
- **Minor drift on `parallel/orchestrator.py` (+2–4 lines since the 5th pass)**:
  `_on_worker_complete` def now at **line 969** (5th pass cited 967);
  `self._interrupted_issues.append(result.issue_id)` at **line 984**
  (5th pass cited 980); `self.wave_label = wave_label` at **line 109**
  (unchanged). Within normal noise band; the 5th pass's "re-locate by name"
  guidance still applies.
- **`state.py:26` is correct** for `class ProcessingState` (the 4th pass's
  off-by-one note that said `:26` should be `:25` appears to have been
  re-corrected by subsequent edits — re-verify before quoting in a commit,
  but `:26` matches HEAD today). `mark_completed` at `state.py:188` and
  `mark_failed` at `state.py:203` match the 3rd pass's citations exactly
  (no drift).
- **`record_orchestration_run` is still unimplemented** — confirmed by a
  negative grep across `scripts/little_loops/` and `docs/`. The `Issue`
  is therefore still actionable; the 5th pass's `_EXPORT_TABLE_MAP`
  dict-shape finding (at `session_store.py:3304`) and `SCHEMA_VERSION = 20`
  finding (at `session_store.py:207`) both still hold on HEAD.
- **`decision_needed` is correctly `false`**: only the `wave TEXT` vs
  split-columns alternative remains from prior passes, and `/ll:decide-issue`
  on 2026-07-11 already selected `wave TEXT` with rationale recorded under
  `## Decision Rationale`. No new options were introduced by this pass.

---



_Added by `/ll:refine-issue --auto` (5th pass) — re-verified against current HEAD.
Two **material** drifts since the 2026-07-11 pass that change the implementation,
not just line numbers:_

- **`SCHEMA_VERSION` is now `20`, not `18` (`session_store.py:207`)**. The v17
  (`commit_events`), v18 (`test_run_events`), v19 (`raw_events`/ENH-2581), and v20
  (`usage_events`/ENH-2461) slots are all taken. **The next-open slot is v21.**
  Every "18→19" / "bump to 19" / `SCHEMA_VERSION = 19` literal in this issue's
  Integration Map, Proposed Solution, and Implementation Steps is stale — treat
  them as "append a new `_MIGRATIONS` entry at the current next-open index and
  bump `SCHEMA_VERSION` to whatever is live at implementation time" (the Scope
  Boundary note already records this; this finding pins the concrete current
  value). The `TestOrchestrationSchema` upgrade test must `_bootstrap_schema_at(db, 20)`
  and assert the v21 upgrade, not v18→v19.

- **`_EXPORT_TABLE_MAP` moved AND changed shape — step 14's code block is now
  wrong (`session_store.py:3304-3316`)**. It is no longer the tuple-list at
  `2791-2814`; it is now a `dict[str, tuple[str, str]]` keyed on the export
  type-name, with a **2-tuple** value `(table_name, timestamp_col)`. The correct
  addition is:

  ```python
  # in _EXPORT_TABLE_MAP (session_store.py:3304):
  "orchestration_run": ("orchestration_runs", "ended_at"),
  ```

  **NOT** the 3-tuple `("orchestration_run", "orchestration_runs", "ended_at")`
  that Implementation Step 14 currently shows — that form no longer matches the
  dict schema and would be a bug. Additionally, `_EXPORT_DEFAULT_TABLES` is now a
  **separate list** (`session_store.py:3318-3329`) of type-name strings; add
  `"orchestration_run"` there too if orchestration rows should appear in the
  default (no-`--tables`) export, mirroring `commit_event` / `test_run_event` /
  `usage_event` which are all present in both structures.

- **`session_store.py` record-fn anchors drifted ~180 lines** (unrelated
  ENH-2461/ENH-2581 code landed above them): `record_commit_event` now at
  **line 1222** (issue cites 1041-1091), `record_test_run_event` at **line 1352**
  (issue cites 1171-1233). Re-locate by name before quoting lines in a commit.
  `record_usage_event` (v20/ENH-2461) is a newer sibling to also model against —
  it is the most recent `record_*_event` and reflects the current house style.

- **`parallel/orchestrator.py` — minor further drift, control flow unchanged**:
  `wave_label` assignment at **line 109** (matches last pass); `_on_worker_complete`
  at **line 969**; `self._pr_ready_branches[result.issue_id] = branch_state` at
  **line 1104**; `_open_pr_for_branch` def at **line 1176**, its docstring
  reference to `_on_worker_complete` at **line 1232**. All within a few lines of
  the 4th pass's numbers — no structural change; re-locate by name as before.

- **No new schema-slot conflict**: no other EPIC-2457 sibling has landed a v21
  migration; the next-open slot is uncontested at this moment, but read the live
  `SCHEMA_VERSION` at implementation time per the Scope Boundary note (siblings
  land in whatever order they're implemented).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation. Order matches the natural commit sequence — registry + export before
producer wiring, docs/tests after._

20. **`_EXPORT_TABLE_MAP` / `_EXPORT_DEFAULT_TABLES` wiring**
    (`session_store.py:3304-3329`). The current shape is
    `dict[str, tuple[str, str]]` keyed on the export type-name (2-tuple value),
    NOT the 3-tuple `list[tuple]` form shown in Implementation Step 14. Add
    `"orchestration_run": ("orchestration_runs", "ended_at")` to the dict AND
    `"orchestration_run"` to `_EXPORT_DEFAULT_TABLES`. Without both entries,
    `ll-session export` silently logs "unknown type" and skips the table.

21. **`docs/guides/HISTORY_SESSION_GUIDE.md`** — user-facing guide (NOT in the
    issue's docs list). Four locations: schema-versions table (lines 60-76),
    "what gets recorded" table (lines 79-99), `--kind` FTS examples
    (line 170), `--tables` choices text (line 208).

22. **`cli/session.py:222-232` export-parser help text** — `export_parser.add_argument`
    `--tables` help string omits `commit_event`/`test_run_event`/`usage_event`
    even though they're valid via `_EXPORT_TABLE_MAP`. Add `orchestration_run_event`
    for parity; optionally close the existing v20 drift on the other three.

23. **`cli/verify_kinds.py:40-46` + `tests/test_verify_kinds.py::TestRun::test_clean_state_returns_zero`**
    — explicit gate that the new `_MIGRATIONS` entry must be paired with
    `_KIND_TABLE`. The gate runs under `python -m pytest scripts/tests/`
    (ENH-2581). If `_KIND_TABLE` is missing the entry, exit 1.

24. **New unit tests** (not in the issue's test list):
    - `test_orchestrator.py::test_on_worker_complete_records_orchestration_run`
      — direct callback test, mirrors `TestEpicBranchCompletion::test_no_merge_when_epic_branches_disabled`
      pattern at line 1533-1546.
    - `test_cli_sprint.py::test_wall_clock_timeout_records_orchestration_run`
      — flush test for `_run_issue_with_wall_clock_timeout`, mirrors
      `test_run_issue_with_wall_clock_timeout_catches_timeout_and_returns_failure`
      at line 654.
    - `test_sprint_integration.py::test_sprint_sequential_retry_records_orchestration_runs`
      — retry-flush test, mirrors `test_sprint_sequential_retry_after_parallel_failure`
      at line 1046-1070.
    - `test_ll_session.py::test_export_includes_orchestration_run_table` —
      explicit `_EXPORT_TABLE_MAP` regression guard. Currently no
      `test_export_*` exists in `test_ll_session.py` (the existing
      export tests cover `ll-history`, not `ll-session` table export).

25. **Schema version correction**: Live `SCHEMA_VERSION` is **20** at
    `session_store.py:207`; the upgrade test must use
    `_bootstrap_schema_at(db, 20)` and assert the v21 migration lands, NOT
    the v18→v19 the issue body cites. Re-verify at implementation time.

26. **Anti-pattern (do NOT add)**: `_REBUILD_TABLES`
    (`session_store.py:2833, 2865, 2886`). Only parser-derived tables
    (`usage_events`/`_backfill_usage_events` at line 1878-1943) are rebuilt;
    direct-write tables (`commit_events`, `test_run_events`, and the
    proposed `orchestration_runs`) are explicitly excluded — see comment at
    `session_store.py:2853-2854`. Adding `orchestration_runs` here would
    be a bug.

### Codebase Research Findings (Wiring Pass — 2026-07-16)

_Added by `/ll:wire-issue --auto` (1st wiring pass) — corrects three stale
claims in the prior research findings and adds six new findings not in the
issue body:_

- **STALE — "four-location lockstep" claim** (lines 266-273 of original
  issue body). Both `cli/session.py:103` and `:115` argparse `choices=[…]`
  literals use `list(VALID_KINDS)` and pull dynamically from
  `session_store.VALID_KINDS`. Adding `"orchestration_run"` to
  `VALID_KINDS` propagates automatically to both argparse `choices` — no
  separate argparse edits required. The 4-location claim is wrong on
  current HEAD.

- **STALE — `_EXPORT_TABLE_MAP` code block** (Implementation Step 14).
  Verified on HEAD: `_EXPORT_TABLE_MAP` is now
  `dict[str, tuple[str, str]]` keyed on type-name with a 2-tuple value,
  not the old `list[tuple[str, str, str]]`. The 3-tuple
  `("orchestration_run", "orchestration_runs", "ended_at")` form no
  longer matches the schema and would be a bug. Use
  `"orchestration_run": ("orchestration_runs", "ended_at")` instead.
  `_EXPORT_DEFAULT_TABLES` is a separate `list[str]` at
  `session_store.py:3318-3329` that needs `"orchestration_run"` appended.

- **STALE — `SCHEMA_VERSION = 18`/`19`** in Integration Map and Implementation
  Steps. Live value is `SCHEMA_VERSION = 20` (`session_store.py:207`). The
  v19/`raw_events` (ENH-2581) and v20/`usage_events` (ENH-2461) slots are
  taken. Next-open is **v21**. Every "18→19" / "bump to 19" literal is
  stale — substitute "live SCHEMA_VERSION" at implementation time.

- **NEW — `cli/verify_kinds.py` gate** (not in issue). Re-globs `_MIGRATIONS`
  for every `CREATE TABLE` and asserts membership in `_KIND_TABLE` OR
  `_KINDLESS_TABLES`. Adding `orchestration_runs` to `_MIGRATIONS` without
  also updating `_KIND_TABLE` will fail
  `test_verify_kinds.py::TestRun::test_clean_state_returns_zero`.

- **NEW — `docs/guides/HISTORY_SESSION_GUIDE.md`** (not in issue). User-facing
  guide with schema-versions table (lines 60-76), "what gets recorded" table
  (lines 79-99), `--kind` value list in FTS examples (line 170), `--tables`
  choices text (line 208). Should list `orchestration_run` for parity.

- **NEW — `cli/session.py:222-232` `export_parser` help text** (not in issue).
  The `--tables` help string currently omits `commit_event`/`test_run_event`/
  `usage_event` even though they're valid via `_EXPORT_TABLE_MAP`. Add
  `orchestration_run_event` for parity (closing the existing v20 drift at
  the same time is recommended).

- **NEW — `_REBUILD_TABLES` anti-pattern** (not in issue). Orchestration runs
  are direct-write, NOT parser-derived. Only `usage_events` lives in
  `_REBUILD_TABLES` because it's rebuilt from `raw_events` via
  `_backfill_usage_events` (`session_store.py:1878-1943`). Adding
  `orchestration_runs` to `_REBUILD_TABLES` would be a bug — the comment at
  `session_store.py:2853-2854` explicitly excludes direct-write tables.

- **NEW — `test_orchestrator.py::test_on_worker_complete_records_orchestration_run`**
  (not in issue). The issue's 4th-pass Codebase Research Finding already
  flagged `test_orchestrator.py` as the dedicated orchestrator unit-test
  file (marked `pytest.mark.integration` at line 44). The
  `TestEpicBranchCompletion::test_no_merge_when_epic_branches_disabled`
  pattern at line 1533-1546 (construct `WorkerResult`, mock collaborators,
  call `_on_worker_complete`, assert on side effects) is the closest
  template. Faster than driving through `test_parallel_cli.py`.

- **NEW — `test_cli_sprint.py::TestIssueWallClockTimeout` flush test** (not
  in issue). Existing `TestIssueWallClockTimeout` at `test_cli_sprint.py:611`
  exercises `_run_issue_with_wall_clock_timeout`. The flush should be tested
  at the caller path with the same patch-`signal`/patch-`process_issue_inplace`
  pattern.

- **NEW — `test_sprint_integration.py::TestSprintErrorRecovery` retry-flush
  test** (not in issue). Existing `test_sprint_sequential_retry_after_parallel_failure`
  at `test_sprint_integration.py:1046-1070` uses `MockQueue`/`MockOrchestrator`/
  `mock_process_inplace` — extend with retry-flush assertions.

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

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("bump
`SCHEMA_VERSION = 18` → `19`"). At least ten other active EPIC-2457 siblings
(ENH-2463, ENH-2464, ENH-2465, ENH-2493, ENH-2494, ENH-2495, ENH-2496,
ENH-2497, ENH-2498, ENH-2511) independently make the same "18→19" claim in
their own Integration Maps — they cannot all be v19. Verified against current
code (`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's stale "19"
literal; each child lands its own migration at whatever version is open when
it is implemented (no coordinated release; per EPIC-2457's own "no shared
helper module is required" scope note).

## Session Log
- `/ll:wire-issue` - 2026-07-16T20:31:05 - `c6dd324d-abd2-4bf0-a5ac-0b0bfc188270.jsonl`
- `/ll:refine-issue` - 2026-07-16T14:18:50 - `ec721603-845a-43dc-9920-57ba425890cc.jsonl`
- `/ll:refine-issue` - 2026-07-16T14:08:02 - `4bc98e28-d432-4a7a-ab1f-dcf602e3157c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:23:47 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:decide-issue` - 2026-07-11T18:09:15 - `37898a30-ea4e-4972-91db-a694a29a9e31.jsonl`
- `/ll:refine-issue` - 2026-07-11T18:00:48 - `626e1d2e-171d-437d-99d2-c692ad2d4a44.jsonl`
- `/ll:refine-issue` - 2026-07-07T06:46:32 - `42c45b6b-5e64-42fb-a77f-fff3dfa85679.jsonl`
- `/ll:refine-issue` - 2026-07-06T23:47:05 - `8b0fb94d-2a13-40c0-a03a-0886bca177ac.jsonl`
- `/ll:refine-issue` - 2026-07-06T19:14:36 - `29927953-330a-400d-9d73-7c6c5c33aac1.jsonl`
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
