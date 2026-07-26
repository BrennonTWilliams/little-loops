---
id: ENH-2814
type: ENH
priority: P1
status: done
captured_at: '2026-07-25T22:08:07Z'
completed_at: '2026-07-26T05:24:45Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels:
- fsm
- loops
- persistence
- cli
- exit-codes
relates_to:
- BUG-2813
decision_needed: false
reconcile_attempted: true
confidence_score: 96
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 14
---

# ENH-2814: Make FSM failure terminals observable end-to-end (exit code, persistence, history)

## Summary

A loop that lands on a `failed` terminal exits **0** and is persisted as
`final_status: "completed"`. The `done`-vs-`failed` distinction is a pure naming
convention with no schema backing, honored by some consumers and ignored by
others — including the persistence layer that feeds `.loops/runs` archives and
the session store. Audit §1.2 /
`thoughts/builtin-loops-audit-2026-07-24.md`.

## Motivation

Every external consumer — shell scripts, cron wrappers, the local test gate,
`ll-queue run` — sees exit 0 when a loop fails. Run archives and
`loop_runs` history record failures as successes, corrupting any downstream
analysis of loop health. Production code already carries a workaround for this
footgun (`parallel/worker_pool.py`), which is the clearest evidence the current
design is wrong.

## Current Behavior

`cli/loop/_helpers.py:64-77` maps `terminated_by` → exit code; `"terminal": 0`
for *any* terminal state (applied at `:1905`). `ExecutionResult` records only
`terminated_by="terminal"` (`fsm/types.py:24`); there is no schema-level failure
flag (`StateConfig.terminal` is a plain bool).

Consumer split:

- **Sub-loop routing honors it**: `fsm/executor.py:1012-1018` (child ends on
  `done` → `on_yes`, any other terminal → `on_no`).
- **CLI display color honors it**: `cli/loop/_helpers.py:1829-1836`.
- **History queries re-derive it in SQL**: `history_reader.py:982-990`
  (`terminated_by = 'terminal' AND final_state != 'done'` → failed).
- **Persistence does NOT**: `fsm/persistence.py:891` and `:943` stamp
  `final_status = "completed" if terminated_by == "terminal" else "failed"` — a
  run that lands on `failed` is persisted as `"completed"` into `.loops/runs`
  archives and the session store's `loop_runs` table.
- **`parallel/worker_pool.py:120-133`** carries a written acknowledgment: *"All
  terminal states (done, blocked, impl_failed) exit 0 — distinguish blocked from
  done by reading the state file left after execution"* — a state-file workaround.
- **`ll-queue run`** (`cli/queue.py:246-257`) judges success purely by exit code
  for the kinds it dispatches; loops stay on `PersistentExecutor` and inherit
  persistence's blind `"completed"`.

## Expected Behavior

- A loop ending on a non-`done` terminal exits with a distinct, documented exit
  code.
- `fsm/persistence.py` stamps `final_status: "failed"` for those runs, so
  archives and the session store are truthful.
- Sub-loop routing keys off the same explicit signal rather than re-deriving it
  from the state name.
- `parallel/worker_pool.py`'s state-file workaround can be deleted.

## Proposed Solution

Two viable approaches — prefer (B):

**(A) Name-based:** map non-`done` terminals to a distinct exit code (e.g. 2) in
`EXIT_CODES`, and apply the same name check in `persistence.py`. Cheap, but keeps
the convention implicit and leaves `history_reader`'s SQL duplication.

**(B) Schema flag (recommended):** add an explicit `failure: true` flag to
`StateConfig` and key exit code, sub-loop routing, and `persistence.py`'s
`final_status` off it. Default it from the existing name convention so no loop
YAML must change on day one, then migrate loops to declare it explicitly (pairs
with the audit §2.2 / rec #8 `failed`-terminal sweep, not yet captured).
Collapses three independent re-derivations into one source of truth.

> **Selected:** (B) Schema flag — collapses 4–5 independent name-based
> re-derivations into one source of truth, using the exact three-site
> round-trip pattern already proven by `StateConfig.terminal`.

The §1.2 consumer sites are fully enumerated above, so the migration surface is
known.

### Decision Rationale

**Selected: (B) Schema flag**

Codebase evidence shows the name-convention (Option A) is already duplicated
across at least 5 independent sites (`fsm/validation.py`'s
`FAILURE_TERMINAL_NAMES`, `cli/loop/_helpers.py`'s inline check,
`history_reader.py`'s SQL predicate, `fsm/persistence.py`'s simpler
`terminated_by`-only check which already disagrees with the others, and
`fsm/executor.py`'s sub-loop routing) — and is demonstrably leaky: known
failure-shaped terminal names (`blocked`, `impl_failed`, `input_missing`,
`not_installed`, `perm_denied`, `finalize_incomplete`, `finalize_failed`) are
absent from `FAILURE_TERMINAL_NAMES`. Extending Option A would require
threading a `final_state` check into `EXIT_CODES` (which today only sees
`terminated_by`), without fixing the underlying duplication.

Option B's schema flag has a direct, already-proven precedent:
`StateConfig.terminal`'s three-site round-trip (field declaration at
`schema.py:607`, `to_dict()` omit-if-falsy at `:670-671`, `from_dict()` default
at `:791`), and `get_terminal_states()` (`schema.py:1476-1482`) is a one-line
comprehension that `get_failure_states()` mirrors trivially. The
default-from-`FAILURE_TERMINAL_NAMES` fallback means no existing loop YAML
needs to change on day one, while collapsing every consumer onto one flag.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A: Name-based | 1 | 2 | 2 | 1 | 6/12 |
| B: Schema flag | 3 | 1 | 2 | 2 | **8/12** |

Option B scores lower on raw simplicity (more call sites touch real logic, not
just renames) but wins decisively on consistency and risk: it removes the
duplication that is the issue's core motivation, rather than adding a sixth
independent re-derivation.

**Key evidence:**
- `fsm/persistence.py`'s current mapping (`terminated_by == "terminal"` only,
  no `final_state` check) already diverges from the other four sites —
  concrete proof the name-convention has drifted and needs a single source of
  truth, not another parallel implementation.
- `StateConfig.terminal`'s three-site pattern is a direct, low-risk template
  already exercised by existing tests.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` (`EXIT_CODES`, `:64-77`; apply site now `:1834-1840`, display-color check also here)
- `scripts/little_loops/fsm/persistence.py` (mapping blocks now `:891-904` and `:943-951`)
- `scripts/little_loops/fsm/schema.py` (`StateConfig` — new `failure` field via the same three-site round-trip pattern as `terminal`: declare `:607`, `to_dict()` conditional emit `:670-671`, `from_dict()` default `:791` keyed off `FAILURE_TERMINAL_NAMES` for backward compat; add `get_failure_states()` alongside `get_terminal_states()` at `:1476-1482`, same shape, filtering on `failure` instead of `terminal`)
- `scripts/little_loops/fsm/types.py` (`ExecutionResult`)
- `scripts/little_loops/fsm/executor.py` (sub-loop routing, now `:1014-1020`; switch from name-check to `get_failure_states()`/`failure` flag)
- `scripts/little_loops/fsm/validation.py` (`_validate_failure_terminal_action`, `:1100-1143`, wired into `validate_fsm()` at `:1343` — this near-precedent already re-derives failure-ness from `FAILURE_TERMINAL_NAMES`; once `failure` exists it should read the flag instead of re-testing the name, superseding rather than duplicating this logic)
- `scripts/little_loops/parallel/worker_pool.py` (`_read_loop_final_state()` helper `:47-57`; workaround comment `:121-133` — retire)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/history_reader.py` (`_WASTED_RUN_PREDICATE`, now `:992-1000` — SQL re-derivation, simplify to read the persisted `final_status`/flag directly)
- `scripts/little_loops/cli/queue.py:246-257`

### Similar Patterns
- Existing `EXIT_CODES` entries (`max_steps: 1`) as the precedent for a nonzero mapping

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **A near-precedent already exists and should be superseded, not duplicated**:
  `fsm/validation.py:1100-1143` (`_validate_failure_terminal_action`, wired into
  `validate_fsm()` at `:1343`) already defines
  `FAILURE_TERMINAL_NAMES: frozenset[str] = frozenset({"failed", "error", "aborted", "finalize_aborted"})`
  and warns (severity WARNING, not ERROR — "so existing loops with bare failure
  terminals continue to load") when a terminal state's name falls in that set
  but the state has no distinguishing action. This is the exact
  name-convention logic Option B's schema flag would replace as the source of
  truth — once `failure: true` exists and is defaulted from this same name
  set, this validator should read the flag instead of re-testing the name.
- **Helper to model a new accessor after**: `FSMLoop.get_terminal_states()`
  (`schema.py:1476-1482`) returns `{name for name, state in self.states.items() if state.terminal}`.
  A `get_failure_states()` following the identical shape (filtering on the new
  `failure` flag instead of `terminal`) is the natural counterpart, and other
  consumers (executor sub-loop routing, `history_reader.py`) could call it
  instead of re-deriving the set inline.
- **`StateConfig.terminal` three-site round-trip pattern** (field decl →
  `to_dict()` conditional emit → `from_dict()` default) to copy for the new
  `failure` field: `schema.py:607` (declare), `:670-671` (`to_dict`, only
  emits when truthy), `:791` (`from_dict`, `data.get("failure", False)` default
  keyed off the name-convention set for backward compat).
- **Terminal state names beyond `done`/`failed` in built-in loops**: `blocked`
  (`proof-first-task.yaml`, `ready-to-implement-gate.yaml`), `impl_failed`
  (`proof-first-task.yaml`, named in `worker_pool.py`'s workaround comment but
  not in `FAILURE_TERMINAL_NAMES`), `input_missing`, `not_installed`,
  `perm_denied` (`cua-agent-desktop.yaml`), `finalize_incomplete`
  (`auto-refine-and-implement.yaml`), `finalize_failed` (`brainstorm.yaml`).
  Several of these are failure-shaped but neither `"done"` nor in
  `FAILURE_TERMINAL_NAMES` — evidence the name-convention approach (A) is
  already leaky, reinforcing the recommendation for Option B.
- **Line drift since capture** (git may have shifted by a few lines; verify at
  implementation time): sub-loop routing is now at `executor.py:1014-1020`
  (not 1012-1018); `persistence.py` mapping blocks span `:891-904` and
  `:943-951`; `history_reader.py`'s predicate (`_WASTED_RUN_PREDICATE`) is at
  `:992-1000`; CLI display color check is at `_helpers.py:1834-1840`;
  `worker_pool.py`'s `_read_loop_final_state()` helper is defined at `:47-57`
  and the workaround comment at `:121-133`.

### Files to Modify (added by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json:449-453` — hand-maintained JSON Schema for loop YAML declares `"terminal": {"type": "boolean", ...}` at the state-def level; needs a paired `"failure": {"type": "boolean", "default": false}` property or the schema drifts from `StateConfig`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py` — reads `final_status`/`ExecutionResult` for display; behavioral consumer of the corrected status values (no code change expected, but currently-mislabeled `"failed"` runs will start showing correctly — smoke-check).
- `scripts/little_loops/cli/loop/lifecycle.py` — branches on persisted `status` (same value space as `persistence.py`'s `final_status`); `ll-loop resume`'s auto-select-latest-resumable logic is a behavioral consumer of the fix.
- `scripts/little_loops/cli/logs.py` — reads `final_status` for log filtering/display; behavioral consumer.
- `scripts/little_loops/parallel/orchestrator.py` — calls `worker_pool._read_loop_final_state()`, the workaround this issue plans to delete; must be updated in lockstep with the `worker_pool.py` change (Step 6), not just have the workaround removed underneath it.
- `scripts/little_loops/session_store.py` — the `loop_runs` table has its own `terminated_by` column (with dedicated index `idx_loop_runs_terminated_by`) but **no `final_status`/`failure` column** — a separate persistence surface from `fsm/persistence.py`'s archive `final_status` stamping, not previously distinguished in the issue text. Resolve during implementation whether `history_reader.py`'s simplified predicate can read `loop_runs.terminated_by` alone or needs a new column here.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — 5 sections will drift: `:4961` (`get_terminal_states()` — needs paired `get_failure_states()` row), `:5022-5040` (`StateConfig` field list — needs new `failure` field), `:5428/:5438` (`ExecutionResult.terminated_by` value set), `:5599-5604` (`validate_fsm()` WARNING behavior description — needs updating once `_validate_failure_terminal_action` reads the flag instead of the name set), `:7401-7402` (session-store wasted-run predicate description).
- `docs/generalized-fsm-loop.md:328` — schema reference table lists `terminal: boolean`; needs a `failure: boolean` row.
- `docs/generalized-fsm-loop.md:1702-1706` — "failure terminal must pair with diagnose state" section describes the *name-based* convention Option B supersedes; update to describe the `failure: true` flag as the actual mechanism.
- `skills/review-loop/reference.md:845-847` — documents current `EXIT_CODES` semantics ("exit code 1 covers `max_steps`, `timeout`, and `cycle_detected`... exit code 1 is non-unique"); needs updating once a new failure exit code is introduced, or `debug-loop-run` reasoning goes stale.
- `skills/audit-loop-run/SKILL.md:305,313` — verdict-determination logic re-derives outcome from `terminated_by` + `final_state` in prose form, a sixth site carrying the same re-derivation logic (in skill-instruction form, not code); reconcile to reference the new flag or it teaches a superseded heuristic.

### Tests
- `scripts/tests/test_builtin_loops.py`, FSM executor/persistence tests
- New: a loop landing on `failed` exits nonzero and persists `final_status: "failed"`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_display.py:2823-2849` (`TestExitCodeMapping`) — **will break**: hard-asserts `EXIT_CODES["terminal"] == 0` and parametrizes `test_zero_exit_code_for_graceful_termination`/`test_nonzero_exit_code_for_limit_termination` purely off `terminated_by`, not which terminal state was reached. Needs a new case for a failure-terminal `final_state` asserting the new nonzero code.
- `scripts/tests/test_fsm_executor.py:5470` (`TestSubLoopExecution`) — `test_sub_loop_terminal_failed_routes_to_on_no` (5542-5566) currently passes only because the child terminal is *named* `failed`; add a case where a differently-named terminal (e.g. `blocked`) with `failure: true` still routes to `on_no`, proving name-independence.
- `scripts/tests/test_fsm_schema.py:4081-4116` (`TestTerminalActionOk`, BUG-2813 pattern) — clone this exact three-test skeleton (round-trip / omitted-when-false / defaults-false) for the new `StateConfig.failure` field. Sibling accessor test at `:774` (`test_get_terminal_states`) to model `get_failure_states()`'s test after.
- `scripts/tests/test_worker_pool.py` — **no existing test** for `_read_loop_final_state()`; write one before deleting the workaround so removal isn't unverified.
- `scripts/tests/test_history_reader.py:265-308` (`test_success_and_wasted_runs_split_by_loop`) — fixture literals hardcode `final_state="done"`/`"failed"` string checks; re-validate against the new `final_status` stamping semantics once `_WASTED_RUN_PREDICATE` is simplified.
- `scripts/tests/test_cli_queue_run.py:70-182` — no test dispatches `RunnerType.LOOP` specifically; today a loop landing on a failure terminal still returns `exit_code == 0`, so `ll-queue run` would wrongly mark it `"done"` — new test needed once `EXIT_CODES` differentiates failure terminals.
- No end-to-end test runs a real `ll-loop run` subprocess to a failure terminal and asserts the OS exit code, nor one that runs `ll-queue run` against a queued `LOOP` target reaching a failure terminal — integration-test gap.

_Codebase Research Findings — test patterns to model new tests after:_
- `scripts/tests/test_fsm_persistence.py:898-927` — table-driven
  `test_archive_run_only_maps_terminated_by_to_status` (list of
  `(terminated_by, expected_status)` tuples); extend with a `failure`-flagged
  terminal case.
- `scripts/tests/test_fsm_persistence.py:1149-1187` —
  `test_final_status_completed_on_terminal` /
  `test_final_status_interrupted_on_max_steps`: single-scenario tests that
  build an inline `FSMLoop`/`StateConfig` fixture (not a YAML file on disk) —
  the pattern for a new `test_final_status_failed_on_failure_terminal`.
- `scripts/tests/test_fsm_validation.py:2601-2690` (MR-5 test class) — the
  four-part structure (direct `_validate_*` call, suppression-flag variant,
  `validate_fsm()` end-to-end wiring, YAML round-trip for "Unknown top-level
  key") to copy for a new validator test on the `failure` flag / updated
  `_validate_failure_terminal_action`.

### Documentation
- `docs/reference/CLI.md` (`ll-loop run` exit codes)
- `docs/generalized-fsm-loop.md` (schema flag, if B)
- `docs/ARCHITECTURE.md` § Orchestration Layers (worker_pool workaround removal)

### Configuration
- N/A

## Implementation Steps

1. Add the `failure` flag to `StateConfig` following the existing `terminal`
   field's three-site round-trip pattern (declare / `to_dict()` / `from_dict()`
   default), defaulted from `FAILURE_TERMINAL_NAMES` so no loop YAML must
   change on day one.
2. Add `get_failure_states()` to `FSMLoop`, mirroring `get_terminal_states()`,
   filtering on the new `failure` flag.
3. Key `EXIT_CODES`, sub-loop routing (`executor.py`), and `persistence.py`'s
   `final_status` off the flag/accessor instead of the terminal state name.
4. Update `fsm/validation.py`'s `_validate_failure_terminal_action` to read the
   `failure` flag instead of re-testing the name against
   `FAILURE_TERMINAL_NAMES`, superseding rather than duplicating that logic.
5. Simplify `history_reader.py`'s `_WASTED_RUN_PREDICATE` SQL to read the
   persisted `final_status` directly.
6. Delete `worker_pool.py`'s state-file workaround (`_read_loop_final_state()`
   and the `:121-133` comment block).
7. Audit callers that assume exit-0-means-success for loops (`ll-queue run`, docs, wrappers).
8. Document the new exit code.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Add a paired `"failure"` property to `scripts/little_loops/fsm/fsm-loop-schema.json:449-453` alongside `"terminal"`.
10. Resolve whether `session_store.py`'s `loop_runs` table (separate from `fsm/persistence.py`'s archive `final_status`) needs a new column, or whether `history_reader.py`'s simplified predicate can read the existing `terminated_by` column alone.
11. Write a new test for `_read_loop_final_state()` in `test_worker_pool.py` before deleting it (no coverage exists today).
12. Update `test_ll_loop_display.py:2823-2849`, `test_fsm_executor.py:5542-5566`, and `test_history_reader.py:265-308` fixtures/assertions that hardcode the pre-fix behavior being changed.
13. Add a `RunnerType.LOOP`-specific test in `test_cli_queue_run.py` proving a failure-terminal loop is recorded as `"failed"`, not `"done"`.
14. Update `docs/reference/API.md` (5 sections), `docs/generalized-fsm-loop.md` (`:328`, `:1702-1706`), `skills/review-loop/reference.md:845-847`, and `skills/audit-loop-run/SKILL.md:305,313` to reflect the flag-based mechanism instead of the name convention.

## Acceptance Criteria

- [x] `StateConfig` has a `failure` bool field, defaulted from
      `FAILURE_TERMINAL_NAMES` when absent (no existing loop YAML needs edits).
- [x] `FSMLoop.get_failure_states()` exists and mirrors `get_terminal_states()`.
- [x] A loop landing on a `failure`-flagged terminal exits with a distinct,
      documented nonzero exit code (not the current unconditional `0`).
- [x] `fsm/persistence.py` stamps `final_status: "failed"` (not `"completed"`)
      for runs ending on a `failure`-flagged terminal.
- [x] Sub-loop routing (`executor.py`) keys off the `failure` flag /
      `get_failure_states()`, not a re-derived name check.
- [x] `fsm/validation.py`'s `_validate_failure_terminal_action` reads the
      `failure` flag instead of re-testing terminal state names.
- [x] `history_reader.py`'s `_WASTED_RUN_PREDICATE` reads the persisted status
      instead of re-deriving it in SQL.
- [x] `parallel/worker_pool.py`'s state-file workaround is deleted.
- [x] New/updated tests per `### Tests` pass, including a table-driven case
      extending `test_archive_run_only_maps_terminated_by_to_status` and a new
      `test_final_status_failed_on_failure_terminal`.

## Impact

- **Severity**: High — silent failure across every automation surface.
- Sequenced **before** the audit §2.2 / rec #8 sweep (adding `failed` terminals
  is pointless while they are unobservable), and complements BUG-2813 (dead
  terminal actions).
- Behavior change: scripts currently treating any loop exit as success will begin
  seeing nonzero — intended, but call it out in the changelog.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/builtin-loops-audit-2026-07-24.md` §1.2, rec #3 | Source finding, full consumer-site enumeration |
| `docs/ARCHITECTURE.md` § Orchestration Layers | worker_pool context |

## Scope Boundaries

**In scope:**
- Exit-code mapping for non-`done` terminals (`cli/loop/_helpers.py` `EXIT_CODES`).
- `fsm/persistence.py`'s `final_status` stamp (`:891`, `:943`).
- The `failure: true` schema flag and its defaulting from the name convention.
- Sub-loop routing (`executor.py:1012-1018`) and `history_reader.py:982-990`
  keying off the single source of truth.
- Retiring `parallel/worker_pool.py:120-133`'s state-file workaround.

**Out of scope:**
- Adding `failed` terminals to the ~41 loops that lack one (audit §2.2 /
  rec #8) — sequenced *after* this issue.
- Moving dead terminal actions into penultimate states (BUG-2813).
- Backfilling or correcting historical `loop_runs` rows already persisted as
  `"completed"`; this issue fixes forward only.
- Any change to `max_steps` / `error` exit-code semantics, which already work.

## Resolution

Implemented via Option (B), the schema flag.

**Single source of truth.** `StateConfig.failure: bool` (`fsm/schema.py`) follows
the `terminal` three-site round-trip (declare / `to_dict()` omit-if-falsy /
`from_dict()` default). `FAILURE_TERMINAL_NAMES` moved from a function-local in
`fsm/validation.py` to a module constant in `fsm/schema.py`, where it now serves
only as the *parse-time default* for the flag — no consumer re-tests names.
`FSMLoop.get_failure_states()` mirrors `get_terminal_states()`.
`StateConfig.from_dict()` gained an optional `name=` parameter (the state name is
needed to apply that default; `FSMLoop.from_dict()` passes it).

**Consumers collapsed onto the flag.** `FSMExecutor._finish()` computes
`failure_terminal` once and stamps it on `ExecutionResult`, the `loop_complete`
event, and the `loop_runs` row. From there: `ll-loop run`/`resume` exit
`FAILURE_TERMINAL_EXIT_CODE` (2, defined in `fsm/types.py` so non-CLI callers can
import it without the CLI package); `fsm/persistence.py` stamps
`final_status: "failed"`; sub-loop routing takes `on_no`; the CLI display colours
the state as a failure. The two duplicated `terminated_by` → `final_status`
mapping blocks in `persistence.py` were factored into one `_map_final_status()`
helper so `run()` and `archive_run_only()` cannot drift again.

**Workarounds retired.** `parallel/worker_pool.py`'s `_read_loop_final_state()`
and its comment block are gone. `learning_tests/gate.py` carried a byte-identical
copy of the same workaround (not listed in the issue) — removed in lockstep,
since leaving it would have been half a fix. Both now read the exit code.

### Deviations from the plan

- **Step 10 (session-store column) — resolved as "new column needed."**
  `loop_runs` gained a `failure_terminal INTEGER` column (schema v37).
  `final_status` was not reusable for `_WASTED_RUN_PREDICATE`: that predicate
  deliberately excludes `user_stopped`, which maps into the same `"failed"`
  `final_status` bucket. Legacy rows have `NULL` and fall back to the old name
  check, which is documented inline and covered by a test.

- **Step 13 (`ll-queue run` LOOP test) — premise was wrong.** The issue assumed a
  queued loop reaching a failure terminal would be recorded `"done"`. In fact
  `run_action()` does not dispatch `RunnerType.LOOP` at all (deliberate, per
  FEAT-2684 / `runner_spec.py`), so it raises and the entry is already recorded
  `"failed"`. No production change was needed. Added two tests instead: one
  proving a nonzero exit code yields `"failed"`, and one pinning the
  not-dispatched contract so a future LOOP handler can't be wired up without
  revisiting the verdict.

- **`docs/ARCHITECTURE.md` not updated.** The wiring pass predicted the
  worker_pool workaround was described there; it is not (only a one-line file
  index and a class table), so there was nothing to correct.

- **Loop YAML edits were required, not optional.** The issue expected day-one to
  need no YAML changes. That holds for the *exit code and persistence* (the name
  default covers them), but not for *sub-loop routing*: routing changed from
  "any terminal not named `done`" to "any terminal flagged `failure`". 15
  built-in loops with failure-shaped terminals outside the name convention
  (`blocked`, `impl_failed`, `input_missing`, `not_installed`, `perm_denied`,
  `plan_failed`, `abort_*`, `build_failed`, `refine_failed`, `sprint_failed`,
  `unevaluated`, `incomplete`, `handle_sub_loop_*`, `fail_missing_input`) were
  marked `failure: true` to preserve behaviour. Non-failure terminals
  (`present_result`, `done_empty`, `partial_done`, `report`, `await_confirmation`,
  `no_external_deps`, `max_steps_summary`) were deliberately left unflagged —
  they are now correctly treated as successes, which is a behaviour *fix*.
  All 15 edited loops still pass `ll-loop validate`.

- **One extra validator fix.** Widening `_validate_failure_terminal_action` to
  flag-driven coverage surfaced a real gap: its "diagnostic predecessor" check
  recognised `action` and `loop` states but not `learning` states, so
  `ready-to-implement-gate`'s `blocked` terminal warned spuriously. Added
  `state.learning` to the check.

### Verification

- `python -m pytest scripts/tests/` — **16,374 passed, 38 skipped**.
- `ruff check scripts/` — clean; `ruff format` applied to touched files.
- Live smoke: a shell-only loop landing on a `failure: true` terminal exits `2`.
- **Pre-existing, not introduced:** `python -m mypy` reports one error at
  `fsm/validation.py:1172` (`set[str | None]` vs `set[str]` in
  `_validate_terminal_action_ok`, from BUG-2813). Confirmed present before this
  change by stashing; left alone as out of scope.

### Test updates

New coverage: `test_enh2814_failure_terminal_e2e.py` (real `ll-loop run`
subprocess asserting OS exit codes — the integration gap the issue named),
`TestStateConfigFailureFlag`, `TestFailureTerminalActionFlagDriven`,
failure-terminal cases in persistence/executor/display/history_reader/queue
tests. Fixtures encoding the old behaviour were updated: `MagicMock`-based
execution results in `test_cli_loop_lifecycle.py` and `test_cli.py` needed
`failure_terminal = False` pinned (auto-attributes are truthy), and the
`SCHEMA_VERSION` guards across the session-store tests moved 36 → 37.

## Session Log
- `/ll:ready-issue` - 2026-07-26T04:44:20 - `a4976fac-4ce5-429d-9add-b54df4058cd7.jsonl`
- `/ll:wire-issue` - 2026-07-26T04:39:57 - `622cdcbb-3796-4f47-84b9-d723b9ea3f0b.jsonl`
- `/ll:decide-issue` - 2026-07-26T04:10:36 - `51375cc3-34a6-4a02-b462-e8b812da1ff0.jsonl`
- `/ll:reconcile-issue` - 2026-07-26T04:02:35 - `90bcac60-952b-45ec-82a0-b5049b072dd8.jsonl`
- `/ll:refine-issue` - 2026-07-26T03:53:30 - `582d5c2f-cc5f-45d0-86c7-dcb427dec2a9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-26T00:54:34 - `1286c2b1-65d4-4230-b501-25c3ae70b53c.jsonl`
- `/ll:capture-issue` - 2026-07-25T22:08:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a36a68e-d365-4ea1-9394-a9e5904b5739.jsonl`

---

## Status

- **Current**: open
