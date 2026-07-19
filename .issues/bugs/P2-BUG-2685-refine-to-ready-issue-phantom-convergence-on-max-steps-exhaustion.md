---
id: BUG-2685
type: BUG
priority: P2
status: done
captured_at: '2026-07-18T23:58:26Z'
completed_at: '2026-07-19T00:37:26Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
decision_needed: false
confidence_score: 95
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# BUG-2685: refine-to-ready-issue phantom-convergence on max_steps exhaustion

## Summary

`refine-to-ready-issue` (max_steps: 20) exhausted its full step budget on four
separate invocations during a single autodev run, each time reporting
`final_state: done` / `terminated_by: max_steps` — a phantom-convergence
pattern where the loop reports success without actually reaching its natural
terminal state. The same children were re-dispatched into the loop repeatedly
via `recheck_set`, multiplying the wasted budget.

## Current Behavior

Children of ENH-134 (ENH-135/136/137) and children of ENH-138 (ENH-138/139)
each drove `refine-to-ready-issue` to burn its full 20-step budget, at four
separate timestamps in one run (09:44:47, 10:34:16, 11:10:26, 11:54:45). The
loop's completion event reports `final_state: done`, which reads as a
successful convergence, but `terminated_by: max_steps` shows it was actually
cut off mid-refinement. Autodev's `recheck_set` mechanism re-enters the same
children into the loop on a later cycle without any awareness that a prior
cycle already exhausted the budget on them, so the cost compounds instead of
surfacing as a stall.

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `FSMExecutor.run()` step-cap guard (`if self.iteration >= self.fsm.max_steps:`, ~lines 423–464), `FSMExecutor._finish()` (~lines 2464–2525)
- **Cause**: The `max_steps` guard runs unconditionally at the *top* of every loop
  iteration, before the later terminal-state check block (`if
  state_config.terminal:`, ~line 533) that would set `terminated_by:
  "terminal"`. If the FSM routes into a state literally named `done` on its
  last permitted step, the *next* pass of `run()` sees `iteration >=
  max_steps` first and returns `_finish("max_steps")` without ever reaching
  the terminal-check block. `_finish()` builds `ExecutionResult.final_state`
  from `self.current_state` (whatever it happens to be parked on) and
  `terminated_by` from the caller-supplied string — the two fields are set
  independently with no cross-validation, so `final_state: "done"` /
  `terminated_by: "max_steps"` is a legitimate, unflagged combination.
  `refine-to-ready-issue.yaml` has no `on_max_steps:` hook and no
  `circuit.repeated_failure` block configured, so neither of the two
  existing mitigations (see Proposed Solution below) is active for this
  loop.
- **Note on sub-loop routing**: when `refine-to-ready-issue` is invoked as a
  sub-loop from `autodev.yaml`'s `refine_current` state,
  `FSMExecutor._execute_sub_loop()` (~lines 968–984) already routes
  `terminated_by == "max_steps"` through the generic failure branch
  (`on_failure`/`on_no`), regardless of `final_state` — so the phantom
  `done` label is misleading to a human/log reader (e.g. `ll-loop info`,
  `loop_complete` events) but does **not** cause autodev to misclassify the
  sub-loop call itself as a success. The actual harm BUG-2685 describes is
  wasted budget (4× full 20-step burns) plus `recheck_set`'s blindness to
  which children already exhausted budget — not a success/failure routing
  bug at the sub-loop-call boundary.

## Expected Behavior

Either:
1. `refine-to-ready-issue` detects when no new FSM state has been visited for
   N consecutive iterations and exits with a distinct "stalled" verdict
   (instead of the misleading `final_state: done` / `terminated_by: max_steps`
   combination), or
2. autodev's `recheck_set` does not re-dispatch a child into
   `refine-to-ready-issue` if a prior cycle already exhausted `max_steps` on
   it — avoiding repeated budget burn on issues that are known not to
   converge within budget.

Either fix (or both) should stop the loop from silently reporting phantom
success when it never reached its natural terminal state.

## Motivation

Four exhausted-budget invocations in one run is a significant, repeated
waste — each one silently burns the entire 20-step allowance without
producing the intended refinement outcome, and the `final_state: done`
label hides this from anyone scanning run summaries for failures.

## Proposed Solution

TBD - requires investigation. Two candidate approaches (see Expected
Behavior): a stalled-state detector inside `refine-to-ready-issue.yaml`
(compare visited-state history across iterations), or a check in
`autodev.yaml`'s `recheck_set` dispatch path that skips/flags children whose
last `refine-to-ready-issue` run already terminated via `max_steps`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Two existing mechanisms in the FSM engine are direct precedents for each
candidate approach and are not currently wired into `refine-to-ready-issue.yaml`:

**Option A**: Enable stalled-state detection inside `refine-to-ready-issue.yaml`
via the existing `circuit.repeated_failure` block
(`scripts/little_loops/fsm/stall_detector.py::StallDetector`, config
dataclass `RepeatedFailureConfig` in `scripts/little_loops/fsm/schema.py`
lines 980–1036), already used by `scripts/little_loops/loops/general-task.yaml`
lines 24–30:
```yaml
circuit:
  repeated_failure:
    window: 3
    on_repeated_failure: abort
```
`StallDetector` tracks a rolling window of `(state, exit_code, verdict)`
triples and fires a **distinct** `terminated_by: "stall_detected"` (via
`executor.py` ~lines 638–652) when the window is identical — separate from
`"max_steps"`, so downstream consumers (and humans reading `ll-loop info`)
would no longer see a bare `done`/`max_steps` combo for a stalled run.
Complementary: the `on_max_steps` summary-hook (`scripts/little_loops/fsm/executor.py`
~lines 423–464, precedent in `general-task.yaml` line 9 `on_max_steps:
summarize_partial`, from ENH-1631/BUG-2204) does not change `terminated_by`
but gives a place to write a distinct marker file when the cap fires,
addressed further in Option B.

> **Selected:** Option A — `circuit.repeated_failure`/`StallDetector` is a
> fully implemented, executor-wired, test-covered mechanism (config-only
> addition to `refine-to-ready-issue.yaml`); Option B requires net-new
> executor plumbing (`terminated_by` is currently never surfaced to
> `captured`), an argparse enum extension, and a from-scratch read-side
> dispatch guard with no existing precedent to reuse.

**Option B**: Add a dispatch-guard using the existing `deferred_by:
automation` / `deferred_reason` discriminator pattern (ENH-2664), already
used three times for exactly this "skip re-dispatch of an already-known-bad
child" shape:
- `scripts/little_loops/loops/rn-implement.yaml` state `mark_deferred`
  (lines 1330–1366) — reason codes `blocked_by_unmet` / `remediation_stalled`
- `scripts/little_loops/loops/autodev.yaml` state `mark_gate_blocked`
  (~line 504) — gate-blocked children
- `scripts/little_loops/loops/autodev.yaml` state `record_decision_unresolved`
  (~line 372) — decision-needed children

Each writes `ll-issues set-status <ID> deferred --by automation --reason
<CODE>` plus a sidecar `deferred_reason_<ID>.txt` under `${context.run_dir}`,
consumed by `autodev.yaml`'s `report` state (lines 1591–1609) to build a
`deferred_automation` breakdown. A new reason code (e.g.
`refine_max_steps_exhausted`) written at `autodev.yaml`'s `refine_current`
`on_failure: skip_inflight` when `child_result.terminated_by == "max_steps"`
would let `dequeue_next`/`recheck_set` skip re-entry the same way the other
three not-ready exits already do. Note: `auto-refine-and-implement.yaml`'s
`recheck_set` state (lines 283–338) currently dedupes purely by ID
membership in `dispatched.txt`, with no read of any prior run's
`terminated_by`/`final_state` — a guard added only inside `autodev.yaml`
would not by itself prevent `auto-refine-and-implement.yaml`'s
`recheck_set` from re-including a max-steps-exhausted child in a later
sweep unless the same marker is consulted there too (or the child is also
transitioned to `deferred`, which would make it fall out of the active
sprint set `recheck_set` re-resolves against).

The closest existing "check history before dispatch" precedent already
lives inside `refine-to-ready-issue.yaml` itself: state
`check_lifetime_limit` (lines 55–96) queries `ll-issues refine-status <ID>
--json` → `refine_count` before allowing another refine pass — the same
persistent-per-issue-counter shape either option would need, except no
field currently persists "prior run hit max_steps" anywhere issue-keyed
(only to `.loops/.history/` and the `loop_runs` SQLite table, which is
indexed on `terminated_by` but has no `issue_id` column —
`scripts/little_loops/session_store.py` lines 786–807,
`record_loop_run_summary()` lines 1605–1676).

**Recommended**: Both — start with Option B (reuse the ENH-2664
`deferred_by`/`deferred_reason` idiom; low risk, matches an established
pattern, directly fixes the repeated-dispatch waste) and layer Option A on
top for `refine-to-ready-issue.yaml` itself so a stalled run gets a distinct
`terminated_by: "stall_detected"` before it burns the full 20-step budget,
rather than after.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-18.

**Selected**: Option A — Enable stalled-state detection inside
`refine-to-ready-issue.yaml` via the existing `circuit.repeated_failure`
block.

**Reasoning**: Option A is a config-only addition — `StallDetector`,
`RepeatedFailureConfig`, and the distinct `terminated_by: "stall_detected"`
termination path are already implemented and wired in
`scripts/little_loops/fsm/executor.py`, with extensive existing test
coverage (`TestStallDetector` in `test_fsm_executor.py`,
`test_stall_detector.py`). Option B's write-side (`set-status ... deferred
--reason`) reuses an established idiom, but its read/guard side has **no
existing precedent**: none of `mark_gate_blocked`, `record_decision_unresolved`,
or `recheck_after_size_review` actually consult `deferred_reason` before
re-dispatch — they are write-only, single-pass-queue states — and the FSM
executor currently discards `child_result.terminated_by`/`final_state` for
delegate calls (only `.error` reaches `captured`), so distinguishing
`max_steps` at `refine_current`/`recheck_set` call sites requires new
executor-level plumbing, not just a new shell guard. Option A carries a
tuning risk (window sizing / `progress_paths` config against the loop's
existing `check_lifetime_limit`/`check_refine_limit` bounded-retry guard)
but that risk is contained to one loop file, versus Option B's cross-file,
cross-schema surface. Option B remains a reasonable follow-on (tracked by
the closely related `ENH-2686`) once `terminated_by` is exposed to
`captured`, but is not the lower-risk starting point this bug needs.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (StallDetector) | 2/3 | 2/3 | 3/3 | 1/3 | 8/12 |
| Option B (deferred dispatch guard) | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Option A: One live precedent (`general-task.yaml`), full executor wiring,
  9+ existing regression tests; but `refine-to-ready-issue.yaml` has no
  `progress_paths` precedent to configure against its own legitimate
  1-retry refine cycle (`check_refine_limit`).
- Option B: Write-side idiom (`ll-issues set-status --by automation
  --reason`) is a 3–4x repeated pattern, but the guard/read side and
  `terminated_by` exposure to `captured` are net-new engine plumbing with
  zero in-repo precedent.

## Impact

- **Priority**: P2 — recurring, budget-multiplying waste confirmed across
  four invocations in a single run; not data-destructive but materially
  inflates automation cost and obscures failures behind a `done` label.
- **Effort**: Medium — likely needs either a small stalled-detection addition
  to `refine-to-ready-issue.yaml`'s routing, or a dispatch-guard in
  `autodev.yaml`'s `recheck_set` handling; scope needs confirming against the
  FSM's existing state-visit tracking before implementation.
- **Risk**: Low-medium — changes touch a widely-used built-in loop
  (`refine-to-ready-issue.yaml`) and the autodev dispatch path, so a bad
  guard could cause the opposite failure mode (real work incorrectly skipped
  as "already stalled").

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — add
  `circuit.repeated_failure` (Option A) and/or an `on_max_steps` hook
- `scripts/little_loops/loops/autodev.yaml` — `refine_current` state
  (~line 126, `on_failure: skip_inflight`) — write a
  `deferred_reason_<ID>.txt` marker when `terminated_by == "max_steps"`
  (Option B)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `recheck_set`
  state (lines 283–338) — consult the same marker (or issue `deferred`
  status) before re-adding a child to the dispatch diff

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._execute_sub_loop()`
  (~lines 968–984) routes `terminated_by` for any sub-loop caller of
  `refine-to-ready-issue`, including `autodev.yaml:refine_current`
- `scripts/little_loops/cli/logs.py::_derive_loop_outcome()` (~lines
  1751–1770) already buckets `terminated_by in ("max_steps",
  "max_iterations_reached")` as `"max-steps"` distinct from `"converged"` —
  precedent for reading `terminated_by` over `final_state`
- `scripts/little_loops/session_store.py::record_loop_run_summary()`
  (lines 1605–1676) writes every `_finish()` result to the `loop_runs`
  table (indexed on `terminated_by`, no `issue_id` column)

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml` lines 9, 24–30 — both
  `on_max_steps: summarize_partial` and `circuit.repeated_failure` wired
  together on one loop
- `scripts/little_loops/loops/rn-implement.yaml` state `mark_deferred`
  (lines 1330–1366) — the `deferred_by`/`deferred_reason` idiom to extend
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` state
  `check_lifetime_limit` (lines 55–96) — existing persistent-counter
  dispatch-guard shape in this same loop

### Tests
- `scripts/tests/test_fsm_executor.py::TestMaxStepsSummaryHook` (~line
  8509) and `test_max_steps_respected` (~lines 408–430) — assert on
  `result.terminated_by`, model for a new `stall_detected`-vs-`max_steps`
  regression test
- `scripts/tests/test_builtin_loops.py` — already contains
  phantom-convergence test cases per locator research; extend for this loop
- `scripts/tests/test_stall_detector.py` — unit coverage for
  `StallDetector` if Option A is implemented

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — meta-loop rules (MR-1..MR-11)
- `docs/reference/EVENT-SCHEMA.md` — `terminated_by` field documentation

## Related Key Documentation

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (`max_steps: 20`,
  confirmed still current)
- `scripts/little_loops/loops/autodev.yaml` (`recheck_set` dispatch)
- `.issues/enhancements/P3-ENH-2686-recheck-set-retry-abandoned-autodev-queue.md`
  — related but distinct: covers `recheck_set`'s blindness to a child
  abandoned in autodev's own residual queue, not this issue's
  `final_state`/`terminated_by` mislabeling
- `.issues/enhancements/P2-ENH-2664-tag-automation-deferral-with-reason-discriminator.md`
  — origin of the `deferred_by`/`deferred_reason` pattern Option B extends
- `.issues/features/P3-FEAT-1637-fsm-stall-detector-for-repeated-state-failures.md`
  — origin of `StallDetector` (Option A)
- `.issues/enhancements/P3-ENH-1631-fsm-runtime-on-max-iterations-summary-hook.md`
  and `.issues/bugs/P2-BUG-2204-fsm-max-iterations-core-dual-counter-implementation.md`
  — origin of the `on_max_steps` summary-hook mechanism

## Resolution

Enabled `circuit.repeated_failure` (Option A, per Decision Rationale above) in
`scripts/little_loops/loops/refine-to-ready-issue.yaml`: `window: 3`,
`on_repeated_failure: diagnose`. A phantom-convergence stall (e.g. a sub-loop
state like `confidence_check` retrying with no observable state-level
progress for 3 consecutive iterations) now fires a distinct
`terminated_by: "stall_detected"` and routes to the loop's existing
`diagnose` → `failed` terminal path, instead of silently burning the full
20-step `max_steps` budget behind a misleading
`final_state: "done"` / `terminated_by: "max_steps"` combination. `window: 3`
sits safely above this loop's one legitimate retry cycle
(`check_refine_limit` caps `check_readiness` retries at 1, so its triple
repeats at most twice consecutively in normal operation), so real in-progress
refinement is not misclassified as a stall.

Added `TestRefineToReadyIssueSubLoop.test_circuit_repeated_failure_configured`
(`scripts/tests/test_builtin_loops.py`) asserting the config is wired.

Option B (autodev `recheck_set` dispatch guard) remains tracked separately
via `ENH-2686`.

## Status

- [x] Root cause confirmed
- [x] Fix implemented
- [x] Tests added
- [x] Verified

## Session Log
- `/ll:manage-issue` - 2026-07-19T00:37:01Z - `96b02463-6fc1-4613-a7c9-353bcebf076d.jsonl`
- `/ll:ready-issue` - 2026-07-19T00:30:25 - `7aed402c-e95a-44ce-941f-1178265e1d35.jsonl`
- `/ll:confidence-check` - 2026-07-19T00:30:00 - `ca7cebf2-8a6a-4b8f-a10a-fe1f0cc08bde.jsonl`
- `/ll:decide-issue` - 2026-07-19T00:26:45 - `019afb61-8250-4a1c-a403-f85442f517db.jsonl`
- `/ll:refine-issue` - 2026-07-19T00:21:37 - `5dbfc23f-76d5-472b-b62d-3800f546ca8c.jsonl`
- `/ll:capture-issue` - 2026-07-18T23:58:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e0375ff-a00e-4840-8f31-93fc423e7780.jsonl`
