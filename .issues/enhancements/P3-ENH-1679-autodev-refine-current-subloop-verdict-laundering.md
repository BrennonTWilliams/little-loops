---
discovered_date: 2026-05-24
discovered_by: audit-loop-run
status: done
decision_needed: false
confidence_score: 100
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-24T20:52:39Z
---

# ENH-1679: Fix sub-loop verdict laundering in autodev `refine_current` state

## Summary

The `refine_current` state in `loops/autodev.yaml` invokes `refine-to-ready-issue` as a sub-loop
but sets `on_yes`, `on_no`, and `on_error` identically to `copy_broke_down`. The FSM verdict from
the sub-loop is silently discarded. A sub-loop that exits via its `failed` terminal (after
`diagnose → failed`) is treated identically to one that exits via `done`, because both produce
`on_yes` routing in the parent. The flag-file mechanism (`.loops/tmp/recursive-refine-broke-down`)
partially compensates, but if the sub-loop reaches `failed` without executing `write_broke_down`,
no flag is written and autodev proceeds as if refinement succeeded.

## Motivation

This enhancement would:
- **Fix silent correctness failures**: when `refine-to-ready-issue` exits via `failed` (after `diagnose → failed`), `autodev` currently routes identically to a successful refinement — issues silently bypass the `implement_current` quality gate.
- **Reduce wasted work**: unrefined issues that fail refinement should be skipped or logged as errors, not passed to the implementation phase where they produce low-quality output.
- **Improve observability**: distinguishing `done` vs `failed` sub-loop exits enables accurate per-issue failure accounting in autodev run audits.

## Current Behavior

```yaml
refine_current:
  loop: refine-to-ready-issue
  on_yes: copy_broke_down    # sub-loop reached done terminal
  on_no: copy_broke_down     # sub-loop never started / queue empty
  on_error: copy_broke_down  # signal or executor crash
```

All three routes lead to `copy_broke_down`, which copies `.loops/tmp/recursive-refine-broke-down`
to `.loops/tmp/autodev-broke-down`. If the sub-loop exits via `failed` without writing the flag
file (e.g. an early `diagnose → failed` path), `autodev-broke-down` is absent or stale and
`check_broke_down` routes via `recheck_scores` as if refinement was attempted normally.

## Expected Behavior

The parent loop should distinguish:
- Sub-loop `done` terminal (successful refinement or broke-down) → proceed to `copy_broke_down` (current)
- Sub-loop `failed` terminal (unrecoverable error in `diagnose`) → write a failure sentinel and route to `dequeue_next` or a dedicated error state, skipping `implement_current`
- `on_error` (signal/executor crash) → same skip path

One clean approach: ensure `refine-to-ready-issue`'s `diagnose → failed` path always writes a
distinct failure flag (e.g. `.loops/tmp/refine-failed-hard`) so `copy_broke_down` can detect it.
An alternative: add a `write_refine_failed` state in `autodev` that the `on_error` path hits,
setting a flag before routing to `dequeue_next`.

## Discovered Via

`/ll:audit-loop-run autodev` on run `2026-05-24T140508` — sub-loop terminated by SIGKILL at
`confidence_check` (depth=1, iteration 7). The laundering defect was flagged during the sub-loop
verdict laundering check step.

## Proposed Solution

Option A — write a hard-failure flag in the sub-loop before `failed` terminal:

```yaml
# In loops/refine-to-ready-issue.yaml (or _subloop definition)
diagnose:
  action_type: prompt
  action: "..."
  next: write_diagnose_failed    # NEW

write_diagnose_failed:           # NEW
  action: printf '1' > .loops/tmp/refine-failed-hard
  action_type: shell
  on_error: failed
  next: failed

failed:
  terminal: true
```

Then in `autodev.yaml`, `copy_broke_down` reads the new flag and routes differently.

Option B — route `on_error` in `refine_current` to a dedicated state:

> **Selected:** Option B — route `on_error` in `refine_current` to a dedicated state — Single-file change matching the `skip_and_continue` pattern from sibling loops; highest codebase fit (10/12).

```yaml
refine_current:
  loop: refine-to-ready-issue
  on_yes: copy_broke_down
  on_no: dequeue_next      # sub-loop queue was empty — skip this issue
  on_error: skip_inflight  # signal or crash — mark inflight as skipped, move on

skip_inflight:             # NEW
  action: |
    echo "${captured.input.output}" >> .loops/tmp/autodev-skipped.txt
    rm -f .loops/tmp/autodev-inflight
  action_type: shell
  on_error: dequeue_next
  next: dequeue_next
```

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-24.

**Selected**: Option B — route `on_error` in `refine_current` to a dedicated state

**Reasoning**: Option B scores 10/12 because it matches the `skip_and_continue` pattern established in both `auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml` (consistency 3/3), limits changes to a single file (`autodev.yaml`), and the new `skip_inflight` state is a near-direct copy of an already-established pattern. Option A requires modifying two files and adding conditional branching to `copy_broke_down`, a state with no existing template for that pattern, yielding 7/12.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |
| Option B | 3/3 | 3/3 | 2/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: `write_broke_down` at `refine-to-ready-issue.yaml:341` is a template for `write_diagnose_failed`, but `copy_broke_down` needs a new conditional branch with no existing precedent; `test_diagnose_routes_to_failed` at `test_builtin_loops.py:771` breaks and must be updated.
- Option B: `skip_and_continue` in `auto-refine-and-implement.yaml:114` and `sprint-refine-and-implement.yaml:122` are direct structural templates; `rm -f .loops/tmp/autodev-inflight` already appears three times in `autodev.yaml`.

## Acceptance Criteria

- [ ] If `refine-to-ready-issue` exits via `failed` terminal, `autodev` does NOT route the issue to `implement_current`
- [ ] If `refine_current` receives `on_error` (signal/crash), the in-flight issue is recorded as skipped and the queue continues
- [ ] Existing behavior for the `on_yes` (done terminal) path is unchanged
- [ ] `autodev` tests updated to cover `refine_current on_error → dequeue_next` path

## Scope Boundaries

- **In scope**: Differentiating `done` vs `failed` sub-loop exit routing in `refine_current`; ensuring `on_error` skips the inflight issue; adding a test for the new failure path.
- **Out of scope**: Refactoring the broader `autodev` loop structure; changing `refine-to-ready-issue` internal logic beyond the `diagnose → failed` path; implementing retry logic for issues that fail refinement.

## Integration Map

### Files to Modify
- `loops/autodev.yaml` — `refine_current` state (differentiate `on_yes`/`on_no`/`on_error` routes), `copy_broke_down` state (detect new hard-failure flag), optional new `skip_inflight` state (Option B)
- `loops/refine-to-ready-issue.yaml` — add `write_diagnose_failed` shell state before `failed` terminal, writing `.loops/tmp/refine-failed-hard` (Option A)

### Dependent Files (Callers/Importers)
- `loops/autodev.yaml` — sole consumer of `refine-to-ready-issue` sub-loop exit verdict

_Wiring pass added by `/ll:wire-issue`:_
- `loops/issue-refinement.yaml` — also invokes `refine-to-ready-issue` via `run_refine_to_ready` state with `context_passthrough: true`; already uses differentiated routing (`on_yes: check_commit`, `on_no: handle_failure`). Under Option A, verify `write_diagnose_failed` writes `.loops/tmp/refine-failed-hard` (a file this loop never reads) so no routing change is needed here.
- `loops/recursive-refine.yaml` — invokes `refine-to-ready-issue` via `run_refine` state; already differentiated (`on_success: check_passed`, `on_failure: detect_children`); unaffected by either option.

### Similar Patterns
- Other sub-loop invocations in `loops/autodev.yaml` — audit for similar `on_yes`/`on_no`/`on_error` uniformity

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Tests that WILL BREAK and need updating:**
- `scripts/tests/test_builtin_loops.py` → `TestAutodevLoop.test_refine_current_has_on_no_route` (line 1381) — asserts `on_no == "copy_broke_down"`; under Option B this will fail since `on_failure`/`on_no` routes to `skip_inflight`. Update assertion to reflect new target.
- `scripts/tests/test_builtin_loops.py` → `TestRefineToReadyIssueLoop.test_diagnose_routes_to_failed` (~line 771) — asserts `diagnose.next == "failed"`; under Option A this fails since `diagnose.next` changes to `"write_diagnose_failed"`. Update to assert new intermediate state.
- `scripts/tests/test_builtin_loops.py` → `TestAutodevLoop.test_refine_current_has_success_and_failure_routes` (line 1375) — asserts only key presence; update to also assert `on_failure != on_success` to prevent regression.

**Existing tests to update (per Acceptance Criteria):**
- `scripts/tests/test_builtin_loops.py` → `TestAutodevLoop.test_refine_current_has_success_and_failure_routes` (~line 1375): currently checks presence; update to assert `on_failure != on_success`
- New: `TestAutodevLoop.test_refine_current_failure_routes_to_skip_not_copy_broke_down()` — assert `on_failure` routes to the new skip/error state (not `copy_broke_down`)
- New: `TestAutodevLoop.test_skip_inflight_state_exists()` — assert `"skip_inflight"` in `data["states"]` (Option B)
- New: `TestAutodevLoop.test_skip_inflight_writes_skipped_file_and_clears_inflight()` — shell-action test using `_bash()` helper from `scripts/tests/test_loops_recursive_refine.py` (line 14); set up `.loops/tmp/autodev-inflight` and `.loops/tmp/autodev-skipped.txt`, run `skip_inflight` action body, assert `autodev-inflight` cleared and skipped file updated. Model on `TestAutoRefineAndImplementLoop.test_skip_and_continue_*` pattern (line 1053).
- If Option A: New `TestRefineToReadyIssueLoop.test_write_diagnose_failed_state_exists()` and `test_diagnose_routes_to_write_diagnose_failed()` — assert `write_diagnose_failed` state exists and `diagnose.next == "write_diagnose_failed"`

**Smoke / validation tests (will exercise changes automatically):**
- `scripts/tests/test_fsm_fragments.py` → `test_builtin_loops_load_after_migration` — smoke-loads both `autodev.yaml` and `refine-to-ready-issue.yaml` via `load_and_validate()`; will catch undefined state references if new states (`skip_inflight`, `write_diagnose_failed`) are referenced but not declared.

**Executor-level test (no change needed, documents existing correct behavior):**
- `scripts/tests/test_fsm_executor.py` → `TestSubLoopExecution.test_sub_loop_terminal_failed_routes_to_on_no` (~line 3817) — confirms executor already correctly routes `failed` terminal → `on_no`; the bug is purely in the YAML routing, not the executor.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Executor routing (root cause anchor):**
- `scripts/little_loops/fsm/executor.py:562-576` — `FSMExecutor._execute_sub_loop()`: `final_state == "failed"` (non-done terminal) routes to `on_no`; `terminated_by == "error"` routes to `on_error`. Both currently resolve to `copy_broke_down`, making them indistinguishable from `on_yes`.

**Current `refine_current` exact YAML (4 routing slots, all identical):**
- `scripts/little_loops/loops/autodev.yaml` — `refine_current` uses `on_success`/`on_failure`/`on_error`/`on_no` all set to `copy_broke_down`; only `on_rate_limit_exhausted: dequeue_next` is differentiated. `scripts/little_loops/fsm/schema.py` maps `on_success` → `on_yes` and `on_failure` → `on_no` at parse time (`StateConfig.from_dict` lines ~510-511).

**`diagnose → failed` path confirmation — no flag is written:**
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `diagnose` state has `action_type: prompt`, `next: failed`; `failed` state is `terminal: true`. The `write_broke_down` state (which writes `printf '1' > .loops/tmp/recursive-refine-broke-down`) is only reachable via `breakdown_issue`, not via `diagnose`. On a `diagnose → failed` exit, `recursive-refine-broke-down` stays `'0'` (set by `resolve_issue` at loop start), so `copy_broke_down` copies `'0'` → `autodev-broke-down`, and `check_broke_down` routes to `recheck_scores` as if refinement succeeded.

**Differentiated routing reference implementations:**
- `scripts/little_loops/loops/recursive-refine.yaml` — `run_refine` state: `on_success: check_passed`, `on_failure: detect_children`, `on_error: detect_children` — same `refine-to-ready-issue` sub-loop, already differentiated
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `refine_issue` state: `on_success: get_passed_issues`, `on_failure: skip_and_continue`, `on_error: skip_and_continue`; `skip_and_continue` appends to `.loops/tmp/auto-refine-and-implement-skipped.txt` then routes to `get_next_issue` — exact functional analogue for Option B

**Flag-write state reference (Option A pattern):**
- `scripts/little_loops/loops/autodev.yaml` — `mark_decide_ran` state: `action: printf '1' > .loops/tmp/autodev-decide-ran` — established in-loop sentinel-write pattern

**Tests to update/add (with specific anchors):**
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop.test_refine_current_has_success_and_failure_routes()` (~line 1375): currently checks presence; update to assert `on_failure != on_success`
- New: `TestAutodevLoop.test_refine_current_failure_routes_to_skip_not_copy_broke_down()` — assert `on_failure` routes to the new skip/error state
- New: `TestAutodevLoop.test_skip_inflight_state_exists()` — assert `skip_inflight` state is defined (Option B)
- Shell-action test using `_bash()` helper pattern from `scripts/tests/test_loops_recursive_refine.py` — set up `.loops/tmp/autodev-inflight` and `.loops/tmp/autodev-skipped.txt`, run `skip_inflight` action body, assert inflight cleared and skipped file updated

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — Section "autodev — Targeted Refine-and-Implement for Specific Issues" (lines 666-695): the FSM flow diagram shows `refine_current → copy_broke_down` as an unconditional single path; needs a fork showing the new failure path (Option B: `on_failure → skip_inflight → dequeue_next`; Option A: `on_failure → copy_broke_down → [refine-failed-hard check] → dequeue_next`). Prose note ("the broke-down handshake flag is copied after each sub-loop return") also needs qualification that this only happens on the success path after ENH-1679.

### Configuration
- Flag files: `.loops/tmp/recursive-refine-broke-down`, `.loops/tmp/autodev-broke-down`, `.loops/tmp/refine-failed-hard` (new, Option A), `.loops/tmp/autodev-skipped.txt` (new, Option B)

## Implementation Steps

1. Choose implementation approach: Option A (hard-failure flag in sub-loop) or Option B (differentiated routes in parent)
2. Implement chosen option in `loops/autodev.yaml` (`refine_current` and `copy_broke_down` states)
3. If Option A: add `write_diagnose_failed` state to `loops/refine-to-ready-issue.yaml` before the `failed` terminal
4. Add test covering `refine_current on_error → dequeue_next` routing path
5. Run `ll-loop validate loops/autodev.yaml` and `ll-loop validate loops/refine-to-ready-issue.yaml`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_builtin_loops.py` → `TestAutodevLoop.test_refine_current_has_on_no_route` (line 1381) — change assertion from `on_no == "copy_broke_down"` to the new failure-route target; also update `test_refine_current_has_success_and_failure_routes` (line 1375) to assert `on_failure != on_success`.
7. If Option A: update `TestRefineToReadyIssueLoop.test_diagnose_routes_to_failed` (~line 771) to assert `diagnose.next == "write_diagnose_failed"`.
8. Add `test_skip_inflight_writes_skipped_file_and_clears_inflight` shell-action test using `_bash()` helper from `scripts/tests/test_loops_recursive_refine.py` (line 14); model structure on `TestAutoRefineAndImplementLoop.test_skip_and_continue_*` (~line 1053).
9. Update `docs/guides/LOOPS_GUIDE.md` FSM flow diagram (lines 666-695) to show the new `refine_current` failure fork; update prose note about "copied after each sub-loop return" to scope it to the success path only.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete implementation references:_

- **Step 1**: `scripts/little_loops/loops/recursive-refine.yaml` `run_refine` state uses the exact differentiated routing pattern needed for the same sub-loop; `scripts/little_loops/loops/auto-refine-and-implement.yaml` `refine_issue` + `skip_and_continue` is the closest functional analogue for Option B
- **Step 2 (Option B)**: In `scripts/little_loops/loops/autodev.yaml`, change `refine_current.on_failure` from `copy_broke_down` to a new `skip_inflight` state; model `skip_inflight` on `skip_and_continue` in `auto-refine-and-implement.yaml` — write issue ID to `.loops/tmp/autodev-skipped.txt`, clear `.loops/tmp/autodev-inflight`, route to `dequeue_next`
- **Step 2 (Option A)**: In `scripts/little_loops/loops/autodev.yaml` `copy_broke_down`, add a branch that checks for `.loops/tmp/refine-failed-hard` and routes to `dequeue_next` instead of `check_broke_down`; reference `mark_decide_ran` state (same file) for the `printf '1' >` sentinel-write pattern
- **Step 3 (Option A)**: In `scripts/little_loops/loops/refine-to-ready-issue.yaml`, insert `write_diagnose_failed` between `diagnose` and `failed`; change `diagnose.next` from `failed` to `write_diagnose_failed`; model on `write_broke_down` state (same file) which does `printf '1' > .loops/tmp/recursive-refine-broke-down` before `done`
- **Step 4**: Update `scripts/tests/test_builtin_loops.py` `TestAutodevLoop.test_refine_current_has_success_and_failure_routes()` to assert `on_failure != on_success`; add `test_refine_current_failure_routes_to_skip_not_copy_broke_down()` asserting the new skip-state name; add shell-action test using `_bash()` helper from `scripts/tests/test_loops_recursive_refine.py`
- **Step 5**: `ll-loop validate scripts/little_loops/loops/autodev.yaml` and `ll-loop validate scripts/little_loops/loops/refine-to-ready-issue.yaml` (Option A only)

## Impact

- **Priority**: P3 — Edge-case correctness fix; observed during a real audit run but not blocking normal operation.
- **Effort**: Small — Limited to YAML state changes in 1-2 loop files; no Python code changes.
- **Risk**: Low — Changes isolated to FSM state routing; the `on_yes` (done terminal) path is explicitly preserved per Acceptance Criteria.
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `autodev`, `refine-to-ready-issue`, `verdict-laundering`

## Status

**Open** | Created: 2026-05-24 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-05-24T20:52:39 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:ready-issue` - 2026-05-24T20:49:31 - `e16c4fca-3245-4039-9073-2b4646700758.jsonl`
- `/ll:confidence-check` - 2026-05-24T21:00:00 - `2e418c46-c569-4a21-b915-a182722191d8.jsonl`
- `/ll:decide-issue` - 2026-05-24T20:44:09 - `ebfda8b1-7c6f-4402-a680-0e45fdae0827.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00 - `30e56638-d3ca-460d-97df-a2c95bf21e50.jsonl`
- `/ll:wire-issue` - 2026-05-24T20:35:48 - `6c49ced8-0239-42af-aa72-2f4ee1072abd.jsonl`
- `/ll:refine-issue` - 2026-05-24T20:29:43 - `054e1e86-e3ce-4820-80f3-5777ba9724b7.jsonl`
- `/ll:format-issue` - 2026-05-24T20:20:52 - `a3f52d53-d0d2-4bb3-977c-f1151d93ac50.jsonl`
