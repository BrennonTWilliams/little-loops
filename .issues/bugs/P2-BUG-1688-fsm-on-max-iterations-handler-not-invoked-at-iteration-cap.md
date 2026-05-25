---
captured_at: '2026-05-24T22:52:33Z'
completed_at: 2026-05-25T01:50:59Z
discovered_date: 2026-05-24
discovered_by: capture-issue
status: done
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1688: FSM `on_max_iterations` handler not invoked when iteration cap is reached

## Summary

The `on_max_iterations` top-level FSM hook — added in commit
[`931db9e9`](../../../../../../../../) ("feat(fsm): add on_max_iterations summary
hook to FSM runtime + general-task loop") — does not fire when a loop terminates
at `max_iterations`. Confirmed in the `2026-05-24T204014` `general-task` run:
`general-task.yaml` declares `on_max_iterations: summarize_partial` (line 7) and
defines a `summarize_partial` state (lines 285-298), but the run terminated
directly from `count_done` with `terminated_by: max_iterations` and zero events
for `summarize_partial`. The human-readable partial-progress summary the hook is
designed to produce is silently dropped.

## Steps to Reproduce

1. Use `scripts/little_loops/loops/general-task.yaml` (or any loop whose
   top-level declares `on_max_iterations: <state>` and whose `<state>` is
   defined in `states:`).
2. Run with a task that will not reach `done` within the iteration budget:
   `ll-loop run general-task --input "<unfinishable in N iters>" --max-iterations 5`
3. Wait for termination.
4. Inspect the event log
   (`.loops/runs/<run-id>/events.jsonl` or equivalent):
   - Expected: a transition into `summarize_partial`, then `loop_complete`.
   - Actual: `loop_complete` fires directly from the last `count_done`
     (or wherever the iteration cap was reached); `summarize_partial` is
     never entered. No `summarize_partial.action` invocation, no
     `general-task-summary.md` artifact.

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `FSMExecutor.run()` — iteration-cap check at line 284
- **Cause**: Pre-commit `931db9e9`, the cap check was a bare
  `return self._finish("max_iterations")` with no `on_max_iterations`
  consultation. The handler lookup code path did not exist.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Confirmed pre-fix code** (from `git show 931db9e9 -- executor.py`):
```python
if self.iteration >= self.fsm.max_iterations:
    return self._finish("max_iterations")   # ← no on_max_iterations check
```

**Post-fix code** (commit `931db9e9`, now in `executor.py:284–302`):
```python
if self.iteration >= self.fsm.max_iterations:
    if (
        self.fsm.on_max_iterations is not None
        and not self._summary_state_executed
    ):
        self._emit("max_iterations_summary", {...})
        self._summary_state_executed = True
        self.current_state = self.fsm.on_max_iterations
        # Fall through — let the summary state run in this iteration.
    else:
        return self._finish("max_iterations")
```

**Status**: Commit `931db9e9` appears to contain the full fix. Unit tests in
`TestMaxIterationsSummaryHook` (`scripts/tests/test_fsm_executor.py:6525`)
all pass. The confirming run (`2026-05-24T204014`) preceded the commit and
used the pre-fix code. Remaining work is end-to-end verification.

## Current Behavior

- Loop runs until `iterations == max_iterations`.
- Runtime emits `loop_complete` with `terminated_by: max_iterations`.
- `on_max_iterations` handler state is never entered; its `action` never runs;
  any artifact it was supposed to write is missing.

## Expected Behavior

When `iterations == max_iterations` is reached AND a top-level
`on_max_iterations: <state>` is declared AND `<state>` exists in `states:`:

1. Runtime routes to the named state instead of emitting `loop_complete`.
2. That state's `action` runs (typically a single-shot summarizer).
3. The state's `next:` (e.g. `next: done`) is honored, after which the loop
   terminates normally with `terminated_by: max_iterations` still recorded.

If the named state does not exist, log a clear validator warning at load time
(not silently fall through).

## Proposed Solution

1. Read `executor.py` (or the file touched by `931db9e9`) and identify where
   the iteration-cap termination decision is made. Likely candidates:
   the per-iteration top of the run loop, the `count_done`-style evaluator
   exit, and any short-circuit on `max_iterations` in the router.
2. Add a single branch: when the cap is reached and
   `self.loop.on_max_iterations` is set and the named state exists, set
   `next_state = self.loop.on_max_iterations` instead of breaking out of
   the loop.
3. Bypass the iteration-cap check for the handler state itself (run it
   once even at the boundary), then break on whatever `next:` the handler
   declares.
4. Add `ll-loop validate` rule: warn if `on_max_iterations: X` references
   a state not present in `states:`.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.run()` lines 284–302
  (iteration-cap dispatch); `FSMExecutor.__init__()` line 206 (`_summary_state_executed` flag)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/general-task.yaml` line 7 — `on_max_iterations: summarize_partial`
- Any loop YAML declaring `on_max_iterations:` (general-task is currently the only one)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py` — `FSMLoop.on_max_iterations: str | None = None` field at line 876; `get_all_referenced_states()` adds it to refs; `to_dict()`/`from_dict()` round-trip it [Agent 1/2 finding — updated in commit 931db9e9]
- `scripts/little_loops/cli/loop/_helpers.py` — display branch for `max_iterations_summary` at line 966–971 prints orange warning `"iteration cap reached ({iters}); running summary state '{summary_state}'"` [Agent 2 finding — updated in commit 931db9e9]
- `scripts/little_loops/session_store.py` — `_LOOP_EVENT_TYPES` frozenset at line 66 already includes `"max_iterations_summary"` so SQLiteTransport records these rows [Agent 2 finding — updated in commit 931db9e9]
- `scripts/little_loops/cli/loop/run.py` — primary `ll-loop run` entry point; invokes `FSMExecutor.run()` via `PersistentExecutor` [Agent 1 finding]
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor` wraps `FSMExecutor`; no direct on_max_iterations handling needed but integration-test gap exists (see Tests) [Agent 1/3 finding]

### Similar Patterns
- `FSMExecutor.run()` lines 369–392 — `on_retry_exhausted` per-state dispatch (same
  redirect-and-continue pattern; model for routing logic)
- `FSMExecutor._finish()` — only place `loop_complete` is emitted; all termination
  paths go through it
- `_execute_sub_loop()` lines 590–603 — when general-task runs nested inside autodev,
  `terminated_by: "max_iterations"` maps to the parent's `on_no` branch (line 603)

### Tests
- `scripts/tests/test_fsm_executor.py:6525` — `TestMaxIterationsSummaryHook` (5 tests,
  all passing): `test_summary_state_runs_on_cap`, `test_max_iterations_summary_event_emitted`,
  `test_terminated_by_max_iterations_after_summary`, `test_no_summary_state_without_on_max_iterations`,
  `test_summary_state_executes_only_once`
- `scripts/tests/test_general_task_loop.py:627` — `TestENH1631SummarizePartial` validates
  `on_max_iterations: summarize_partial` in general-task YAML
- `scripts/tests/test_fsm_validation.py:909` — `TestOnMaxIterationsValidation` (validator checks)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_execution.py::TestEndToEndExecution` — existing `test_exits_on_max_iterations` (line 155) uses a loop *without* `on_max_iterations`; **new test needed** that sets `on_max_iterations: summarize`, mocks Popen, calls `main_loop()`, and asserts summary-state output is present [Agent 3 finding — gap]
- `scripts/tests/test_fsm_persistence.py` — `test_final_status_interrupted_on_max_iterations` (line 882) uses a loop without `on_max_iterations`; **new variant needed** that sets `on_max_iterations` and verifies `result.terminated_by == "max_iterations"` AND `state.status == "interrupted"` after summary runs through `PersistentExecutor` [Agent 3 finding — gap]

### Validation
- `scripts/little_loops/fsm/validation.py:959` — `_validate_on_max_iterations()` already
  rejects unknown state refs at load time; wired into `validate_fsm()` at line 851

### Documentation
- `docs/reference/API.md` — `FSMLoop` dataclass documents `on_max_iterations` field
- `docs/reference/EVENT-SCHEMA.md` — documents `max_iterations_summary` event
- `docs/guides/LOOPS_GUIDE.md` — documents the field in loop-type table

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — no entry for ENH-1631 (`on_max_iterations` feature) or BUG-1688 fix; most recent entry is `[1.109.0] - 2026-05-24`; needs a concrete version-section entry at release prep time [Agent 2 finding]

### Configuration
- N/A

### Schema Files

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/schemas/max_iterations_summary.json` — **absent from disk**; `max_iterations_summary` is in `SCHEMA_DEFINITIONS` in `scripts/little_loops/generate_schemas.py` (35 entries) but `ll-generate-schemas` has not been re-run since the event was added; run `ll-generate-schemas` to materialize the file [Agent 2 finding]

## Implementation Steps

_Steps 1–5 are complete via commit `931db9e9`. Remaining work is step 6:
end-to-end verification that the fix produces the expected artifact._

1. ~~Locate the iteration-cap termination branch in the FSM runtime~~
   → `executor.py:284` in `FSMExecutor.run()` — confirmed.
2. ~~Wire `on_max_iterations` dispatch into that branch~~
   → done in `931db9e9`: emits `max_iterations_summary`, sets
   `_summary_state_executed = True`, routes to handler state (fall-through,
   not `continue`).
3. ~~Add a one-shot guard so the handler state itself isn't re-capped~~
   → `FSMExecutor._summary_state_executed` flag (`executor.py:206`).
4. ~~Add `ll-loop validate` check for unresolved handler-state name~~
   → `_validate_on_max_iterations()` in `validation.py:959`.
5. ~~Add regression test for the cap-with-handler path~~
   → `TestMaxIterationsSummaryHook` in `test_fsm_executor.py:6525` (5 tests, all pass).
6. **[TODO]** End-to-end verification: run `ll-loop run general-task
   --input "<unfinishable task>" --max-iterations 5` and confirm:
   - `max_iterations_summary` event appears in the event log
   - `summarize_partial` state is entered
   - `.loops/tmp/general-task-summary.md` is written with partial-progress content
   - Final `loop_complete` carries `terminated_by: max_iterations`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included alongside the E2E verification in step 6:_

7. **[TODO]** Run `ll-generate-schemas` to write `docs/reference/schemas/max_iterations_summary.json` — the event is registered in `SCHEMA_DEFINITIONS` but the physical file was never generated after commit `931db9e9`
8. **[TODO]** Add a new test to `scripts/tests/test_ll_loop_execution.py::TestEndToEndExecution` — use inline YAML with `on_max_iterations: summarize`, mock `subprocess.Popen` to always fail, call `main_loop()`, assert summary-state output appears (follow the `test_exits_on_max_iterations` pattern at line 155)
9. **[TODO]** Add a new test to `scripts/tests/test_fsm_persistence.py` — variant of `test_final_status_interrupted_on_max_iterations` (line 882) that sets `on_max_iterations` on the FSM and verifies `result.terminated_by == "max_iterations"` AND `state.status == "interrupted"` after the summary state executes through `PersistentExecutor`
10. **[TODO]** Add `CHANGELOG.md` entry for ENH-1631 / BUG-1688 at release prep time (no `[Unreleased]` section — promote to a concrete `[X.Y.Z] - DATE` version section)

## Impact

- **Priority**: P2 — Silently drops a feature that just landed
  (`931db9e9`). The partial-progress summary is the only signal a human
  operator gets when a long-running loop runs out of budget; without it,
  the operator has to read the raw event log. Not P1 because the failure
  is loss-of-feature, not loss-of-data — the loop still terminates cleanly
  and on-disk work is intact.
- **Effort**: Small — likely a one-branch wiring fix plus a regression test.
- **Risk**: Low — `on_max_iterations` is opt-in (loops without it stay on
  the current termination path). Worst case is a runtime crash if the
  handler state mis-routes, but a `validate` check at load time mitigates.
- **Breaking Change**: No

## Related Key Documentation

- Commit [`931db9e9`](`git log 931db9e9`) — `feat(fsm): add on_max_iterations summary hook to FSM runtime + general-task loop`
- [[BUG-1687]] — sibling defect in the same `general-task` loop; both surfaced in
  the `2026-05-24T204014` audit. Fixing 1687 reduces how often this handler is
  needed, but does not address this bug.

## Labels

`bug`, `captured`, `fsm-runtime`, `regression`, `general-task`

## Resolution

Core fix (executor.py dispatch + validation + unit tests) landed in commit `931db9e9`.
Remaining steps completed in this session:

- Generated `docs/reference/schemas/max_iterations_summary.json` via `ll-generate-schemas`
- Added `TestEndToEndExecution::test_runs_summary_state_on_max_iterations` to `scripts/tests/test_ll_loop_execution.py`
- Added `TestPersistentExecutor::test_final_status_interrupted_with_on_max_iterations_summary` to `scripts/tests/test_fsm_persistence.py`
- All 34 related tests pass

## Session Log
- `/ll:manage-issue` - 2026-05-25T01:50:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/563f1f37-7ecf-468a-aff8-fe95c01b8246.jsonl`
- `/ll:ready-issue` - 2026-05-25T01:45:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/563f1f37-7ecf-468a-aff8-fe95c01b8246.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00dd214e-21f4-4853-b307-06bad0e24d20.jsonl`
- `/ll:wire-issue` - 2026-05-25T01:40:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7d694883-29f9-4b64-81ff-f0a075e5216f.jsonl`
- `/ll:refine-issue` - 2026-05-25T01:34:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a56fddde-c519-4734-949d-5f8dcca5921f.jsonl`
- `/ll:format-issue` - 2026-05-24T23:53:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3421ff4b-05fc-4e80-bb1d-cb7ee266a185.jsonl`
- `/ll:capture-issue` - 2026-05-24T22:52:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b11535be-d77b-46f8-a622-5a6525775721.jsonl`

---

**Done** | Created: 2026-05-24 | Priority: P2
