---
id: ENH-2740
title: Wire ll-harness producer to write harness_events (signature refactor + DSL
  per-task rows)
type: ENH
priority: P3
status: done
discovered_date: 2026-07-22
completed_at: '2026-07-22T21:05:29Z'
discovered_by: issue-size-review
parent: EPIC-2457
blocked_by:
- ENH-2739
labels:
- enhancement
- history-db
- eval
relates_to:
- ENH-2493
decision_needed: false
confidence_score: 98
outcome_confidence: 87
score_complexity: 18
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 22
---

# ENH-2740: Wire ll-harness producer to write harness_events

## Summary

Child 2 of 3 decomposed from ENH-2493 ("Persist ll-harness / eval outcomes
into history.db"). This child carries the bulk of ENH-2493's outcome risk:
threading `passed`/`eval_result.verdict` out of `_evaluate_and_report()`
(currently an `int`-only return) so `main_harness()`'s callers can call
`record_harness_event()` (landed by ENH-2739) with real data. Depends on
ENH-2739 for the schema and recorder function to exist.

## Current Behavior

`ll-harness` (`scripts/little_loops/cli/harness.py`) evaluates skill/cmd/mcp/
prompt/dsl runs and prints a pass/fail report, but never persists the
outcome. `_evaluate_and_report()` returns a bare `int`, so none of
`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`/`cmd_dsl` has access to the
`passed`/`verdict` data needed to call `record_harness_event()` (the
recorder landed by ENH-2739, which sits unused until this issue wires a
caller to it).

## Expected Behavior

Every `ll-harness` invocation writes one `harness_events` row (or, for
`--dsl` batches, one aggregate row plus one row per task linked via
`parent_id`) capturing `runner`, `target`, `exit_code`, `semantic_verdict`,
`semantic_passed`, `timed_out`, `duration_ms`, `head_sha`, and `branch` —
without changing the harness process's exit code if the write fails (DB
absent/locked degrades silently per the Scope's best-effort guard).

## Impact

- **Priority**: P3 - mid-priority child of EPIC-2457's history-db coverage
  expansion; not user-facing or urgent, but blocks ENH-2741 (the read-side
  API) from having any real data to query.
- **Effort**: Medium - touches 5 call sites plus `main_harness()`'s dispatch
  and ~19 existing test assertions, but the recorder function and schema
  already exist (ENH-2739), and two live codebase precedents
  (`verify_kinds.py::_run()`, `verify_decisions.py::_run()`) establish the
  exact `(rc, obj)`-internal / `int`-external pattern to follow.
- **Risk**: Low - the `(rc, EvalReport)` tuple option (selected via
  `/ll:decide-issue`) keeps `cmd_*` functions' external `-> int` contract
  unchanged, so no caller of these functions outside this file is affected;
  every `record_harness_event()` call is wrapped in
  `contextlib.suppress(Exception)` so a DB failure cannot change harness
  exit codes.
- **Breaking Change**: No.

## Parent Issue

Decomposed from ENH-2493. See ENH-2493 for full motivation and the complete
codebase research trail — anchors have drifted across multiple refine passes
(function/line locations moved repeatedly as the file grew); re-verify every
anchor against live `main` immediately before implementing rather than
trusting any specific line number cited in ENH-2493, including its own
"Anchor Refresh" corrections.

## Scope

- **Signature refactor (Option (a), per ENH-2493's Codebase Research
  Findings)**: change `_evaluate_and_report()` to return a small dataclass
  (`passed: bool`, `verdict: str | None`, `eval_result: EvaluationResult |
  None`) instead of a bare `int`. Keep this dataclass harness-local (or in
  `runner_spec.py` if reuse outside `harness.py` is needed) — do NOT fold new
  fields into `RunnerResult` itself or disturb its re-export identity (`
  test_runner_spec.py::TestRunnerResultReexport` pins `HarnessRunnerResult is
  RunnerResult`; re-run that test after implementation as a cheap regression
  check).
- **Call-site wiring**: update `cmd_skill`, `cmd_cmd`, `cmd_mcp`, `cmd_prompt`
  to consume the new return shape and call `record_harness_event(...)`
  (imported from `session_store.py`) with `runner`, `target`, `exit_code`,
  `semantic_verdict`, `semantic_passed`, `timed_out`, `duration_ms`,
  `head_sha`, `branch` before returning. Capture `head_sha`/`branch` via a
  small local git helper — `git_utils.py` does not exist; either replicate
  the 14-line `_git_output()` helper from `pytest_history_plugin.py:61-74`
  locally in `harness.py`, or factor a new `git_utils.py` if this issue's
  implementer judges a second consumer is imminent (optional, not required).
- **DSL per-task rows**: in `cmd_dsl()`'s per-task loop, write one aggregate
  row (`runner="dsl"`, `parent_id=NULL`, capture `lastrowid`) then one row
  per `DslTask` (`runner="dsl-task"`, `parent_id=<aggregate id>`,
  `target=task_file.name`) — per ENH-2493's Option A (aggregate-first, single
  pass).
- **Best-effort guard (hard requirement)**: wrap every
  `record_harness_event(...)` call site in `contextlib.suppress(Exception)`.
  `cli_event_context`'s `__exit__` does NOT swallow `sqlite3.Error` (verified
  in ENH-2493), so this is the only thing that makes "DB absent/locked does
  not change the harness exit code" true — it is not optional.
- **Test-assertion updates**: the signature change from `int` to a dataclass
  breaks return-value assertions in `test_cli_harness.py` — enumerated
  exhaustively in ENH-2493's "Notable Risks" #5 (18 sites across
  `TestCmdSkill`, `TestCmdCmd`, `TestCmdMcp`, `TestCmdPrompt`, plus
  `cmd_dsl`'s internal `cmd_prompt` call and its own aggregate assertions).
  Update each to unpack the dataclass (`result.rc` or equivalent) instead of
  comparing directly to an int. `capsys`-based stdout assertions are
  unaffected (confirmed safe in ENH-2493) — only return-value assertions
  need touching.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis re-verified against
live `main` on 2026-07-22 (`ENH-2739`'s commit `564a1205` has landed):_

- **Anchors re-confirmed current** (superseding all line numbers cited
  anywhere above/in ENH-2493): `_evaluate_and_report()` at
  `scripts/little_loops/cli/harness.py:183-243` (returns bare `int` at
  `:191`, `:194`, `:243`); `cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt` at
  `:268-336`; `cmd_dsl` at `:339-384` (per-task call `rc = cmd_prompt(task_args)`
  at `:377`); `main_harness()` at `:387-406`. `record_harness_event()` is
  live at `scripts/little_loops/session_store.py:1826-1892`.

- **Test-site count is 19, not 18**, in the four named classes
  (`TestCmdSkill` 5: `:199,233,245,261,273`; `TestCmdCmd` 6:
  `:333,345,355,367,382,393`; `TestCmdMcp` 5: `:420,443,449,461,473` — ENH-2493's
  enumeration only listed 3 of these 5, missing `test_mcp_invalid_target_format:443`
  and `test_mcp_invalid_json_args:449`, both early `return 2` short-circuits
  before a spec is built; `TestCmdPrompt` 3: `:502,517,529`). Budget for 19
  production-class sites, not 18; `cmd_dsl`'s own 5 int-comparison sites
  (`TestCmdDsl`, `:863,879,898,906,912`) are separate and already implied by
  "cmd_dsl's internal cmd_prompt call and its own aggregate assertions."

- **`main_harness()`'s dispatch is not covered by the Scope's "Call-site
  wiring" bullet but must change too.** `main_harness()` (`:394-403`)
  currently does `return cmd_skill(args)` / `return cmd_cmd(args)` / etc.
  directly — if `cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt` return the new
  dataclass instead of an `int`, these 5 dispatch lines must extract an
  int-compatible value (e.g. `return cmd_skill(args).rc`) so
  `main_harness()` keeps its `-> int` contract. `TestMainHarness`
  (`scripts/tests/test_cli_harness.py:665-793`) asserts `result == 0`/`1`
  directly against `main_harness(...)`'s return and does **not** need
  updating itself as long as the dataclass exposes an int field — but the
  dispatch body does need a one-line change per branch. This was missed by
  ENH-2493's own risk enumeration (which covers only the 4 `cmd_*` classes).

- **Decision needed: the proposed 3-field dataclass (`passed: bool`,
  `verdict: str | None`, `eval_result: EvaluationResult | None`, per this
  issue's Scope) has no field `main_harness()` can return as the int exit
  code.** ENH-2493's own Option (a) text (`.issues/enhancements/P3-ENH-2493-...md:218`)
  proposed a `(rc, EvalReport)` tuple specifically to solve this, but this
  child issue's Scope narrowed it to a single dataclass and dropped `rc`.
  Two ways to close the gap:

  **Option A**: Add a 4th field `rc: int` to the dataclass (e.g.
  `HarnessEvalOutcome(rc, passed, verdict, eval_result)`). Every caller
  (`cmd_skill` etc.) returns the dataclass as-is; `main_harness()`'s 5
  dispatch lines become `return cmd_skill(args).rc`. Single return type,
  no tuple-unpacking noise at call sites.

  **Option B**: Revert to ENH-2493's original `(rc, EvalReport)` tuple
  return from `_evaluate_and_report()`. Each `cmd_*` function unpacks
  `rc, outcome = _evaluate_and_report(...)`, calls
  `record_harness_event(..., semantic_passed=outcome.passed, ...)`, then
  `return rc` (unchanged from today) — meaning `cmd_skill`/`cmd_cmd`/`cmd_mcp`/
  `cmd_prompt`'s own external return type stays `int`, and the 19
  `test_cli_harness.py` assertions currently pinned to `int` do **not**
  break at all (only `TestSemanticEvaluator`'s direct calls to
  `_evaluate_and_report()`, if any exist, would need tuple-unpacking).

  > **Selected:** Option B — matches two live `(rc, obj)`-internal /
  > `int`-external precedents already in this codebase
  > (`cli/verify_kinds.py::_run()`, `cli/verify_decisions.py::_run()`) and
  > requires zero changes to the 19 existing `test_cli_harness.py` assertions.

  **Original recommendation (superseded below)**: Option A — for v1, prefer
  a single dataclass with an explicit `rc` field over a tuple return; it
  matches this issue's own Scope wording (a dataclass, not a tuple) and
  keeps `main_harness()`'s fix mechanical (`.rc` suffix) while still
  requiring the 19 `test_cli_harness.py` sites to move to
  dataclass-attribute assertions as this issue's Acceptance Criteria
  already accounts for. See `### Decision Rationale` below — codebase
  evidence favors Option B instead.

- **Timing/git instrumentation does not exist anywhere in this code path
  today.** Neither `RunnerResult` (`scripts/little_loops/runner_spec.py:54-62`,
  fields: `stdout`, `stderr`, `exit_code`, `timed_out`, `error` — no
  `duration_ms`) nor `run_action()`/its per-runner dispatch functions
  measure wall-clock time. `duration_ms` and `head_sha`/`branch` (required
  `record_harness_event()` kwargs per this issue's Scope) must be captured
  freshly inside each `cmd_*` function: wrap the `run_action(spec)` call
  with `time.monotonic()` before/after, and call a locally-replicated
  `_git_output()` (copied from `scripts/little_loops/pytest_history_plugin.py:61-74`,
  confirmed there — no `git_utils.py` exists) for `head_sha`/`branch`. This
  is implied by the Scope's "Call-site wiring" bullet but not spelled out.

- **`record_harness_event()` returns `None`, not the inserted row id**
  (`scripts/little_loops/session_store.py:1845`, `-> None`) — `cmd_dsl`'s
  aggregate-then-per-task wiring needs the aggregate row's id to set as
  `parent_id` on each per-task call, but the recorder gives no way to get it
  back directly. The existing recorder-level test
  `scripts/tests/test_session_store.py:5723-5742`
  (`test_parent_id_round_trips_for_dsl_subtasks`) demonstrates the
  workaround: after calling `record_harness_event()` for the aggregate row,
  open a separate connection via `little_loops.session_store.connect()` and
  query `SELECT id FROM harness_events ORDER BY id DESC LIMIT 1` (or filter
  on `runner`/`target`/`ts` for safety under concurrent writers) to recover
  the aggregate id before looping over per-task calls. This is a small but
  easy-to-miss step since `record_harness_event`'s recorder-level tests
  already exist and pass — the producer-level gap is invisible until
  `cmd_dsl` is actually wired.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-22.

**Selected**: Option B — `(rc, EvalReport)` tuple return from
`_evaluate_and_report()`, `cmd_*` functions stay `-> int` externally.

**Reasoning**: The codebase already contains two live, tested precedents for
exactly this `(rc, obj)`-tuple-internal / `int`-external shape
(`cli/verify_kinds.py::_run()` → `main_verify_kinds()`,
`cli/verify_decisions.py::_run()` → `main_verify_decisions()`), including a
matching test-unpacking idiom (`test_verify_kinds.py::TestRun`). Every one of
the 50+ `cmd_*`-style functions in this repo returns a bare `int` today —
Option A would make `cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt` the first to
break that convention externally and would force all 19 `test_cli_harness.py`
int-assertion sites plus `main_harness()`'s 5 dispatch lines to change. Option
B touches none of that: `TestSemanticEvaluator` (`test_cli_harness.py:584-658`)
already calls the public `cmd_cmd()` wrapper, not `_evaluate_and_report()`
directly, so it is unaffected either way, and no dataclass field named `rc`
exists anywhere in the codebase (the established convention is `exit_code`).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Option A (dataclass w/ `rc`) | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |
| Option B (tuple return) | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |

**Key evidence**:
- Option A: No `cmd_*` function in the repo returns anything but a bare
  `int` today (50+ sites); `rc` would be a novel field name (convention is
  `exit_code`, 15+ occurrences). Breaks 19 existing test assertions plus 5
  `main_harness()` dispatch lines.
- Option B: Matches `cli/verify_kinds.py::_run()` and
  `cli/verify_decisions.py::_run()` exactly, including the test-unpacking
  idiom in `test_verify_kinds.py::TestRun`; zero of the 19 existing
  `test_cli_harness.py` assertions change; `main_harness()` untouched.

## Acceptance Criteria

- A `ll-harness run skill format-issue …` invocation writes one
  `harness_events` row with correct `runner="skill"`, `target`,
  `semantic_passed`, `exit_code`.
- A timing-out run records `timed_out=1`.
- A `--dsl` batch writes one aggregate row + one row per task, each per-task
  row's `parent_id` pointing at the aggregate row's id.
- `LL_HISTORY_DB` pointed at an unopenable path does not change the harness
  process exit code (`TestHarnessEventPersistence.test_main_harness_succeeds_when_db_unopenable`).
- All 18 previously-`int`-typed return-value assertions in
  `test_cli_harness.py` pass against the new dataclass shape.
- `test_runner_spec.py::TestRunnerResultReexport` still passes unchanged
  (`RunnerResult` re-export identity undisturbed).
- Tests: PASS run, FAIL run, timeout, DSL multi-row + parent_id linkage,
  graceful degradation — new `TestHarnessEventPersistence` class in
  `test_cli_harness.py`.

## Explicitly Out of Scope

- `harness_events` schema/migration, kind registration, `record_harness_event()`
  itself — landed by ENH-2739 (this child depends on it existing).
- `history_reader` read API, `ll-session recent/search --kind harness`,
  reader/CLI docs — ENH-2741.

## Status

**Open** | Created: 2026-07-22 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-07-22T21:05:00Z - `de1fb169-0b9b-4d2f-beff-6c80f31e58e3.jsonl`
- `/ll:ready-issue` - 2026-07-22T20:50:39 - `500bcf8a-e4b7-4f2e-bc0d-421942521112.jsonl`
- `/ll:confidence-check` - 2026-07-22T21:00:00Z - `40a1b9c9-ce59-43bd-ba76-e126bbde204b.jsonl`
- `/ll:decide-issue` - 2026-07-22T20:46:04 - `042e092a-c4e0-45ae-9e05-50cff423a36b.jsonl`
- `/ll:refine-issue` - 2026-07-22T20:41:27 - `63f6310d-260a-455e-8d51-7361c73ba954.jsonl`
- `/ll:issue-size-review` - 2026-07-22T00:00:00Z - `5a7a2fd0-cba1-488a-89c7-36283dba4691.jsonl`
