---
id: BUG-2397
title: 'FSM runner emits `terminated_by: "max_iterations"` instead of `"interrupted"`
  when session is killed between state transitions'
type: BUG
status: done
priority: P3
captured_at: '2026-06-30T00:00:00Z'
completed_at: '2026-06-30T17:15:45Z'
discovered_date: '2026-06-30'
discovered_by: audit-loop-run
labels:
- fsm
- runner
- termination
- observability
confidence_score: 96
outcome_confidence: 82
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 20
decision_needed: false
---

# BUG-2397: FSM runner emits `terminated_by: "max_iterations"` on session kill instead of `"interrupted"`

## Summary

When a Claude session ends (SIGTERM, context limit, user interruption) while the
FSM runner is between state transitions — i.e., after a `route` event but before
the next `state_enter` — the runner's shutdown handler writes a `loop_complete`
event with `terminated_by: "max_iterations"` regardless of whether the iteration
budget was actually reached. This contradicts the `state.json` `status:
"interrupted"` field written by the same shutdown path, and misleads users and
audit tooling into diagnosing iteration budget exhaustion when the real cause is
external session death.

**Observed in run:** `.loops/.history/2026-06-14T024943-sprint-refine-and-implement/`

- `events.jsonl` → `loop_complete.terminated_by: "max_iterations"`, `iterations: 1`
- `state.json` → `status: "interrupted"`
- YAML had `max_iterations: 500` at commit `38a158b` — hitting the limit at
  iteration 1 is impossible through normal execution
- Total wall clock: 104ms; only `get_next_issue` ran (103ms); `refine_issue` was
  never entered

## Current Behavior

The FSM runner's shutdown handler always writes `terminated_by: "max_iterations"` in the `loop_complete` event, regardless of whether the iteration budget was actually exhausted. This occurs when a session ends (SIGTERM, context limit, user interruption) while the runner is between state transitions (after a `route` event but before the next `state_enter`).

As a result, `events.jsonl` and `state.json` contradict each other: `loop_complete.terminated_by` shows `"max_iterations"` while `state.json` shows `status: "interrupted"`.

## Expected Behavior

When a loop run is terminated by an external signal (SIGTERM, session kill):
- `events.jsonl` should emit `loop_complete` with `terminated_by: "interrupted"`
- `state.json` `status` should be `"interrupted"` (consistent with `terminated_by`)

When a loop run exhausts its iteration budget:
- `events.jsonl` should emit `loop_complete` with `terminated_by: "max_iterations"`
- `state.json` `status` should be `"max_steps_reached"`

The two fields must always agree.

## Steps to Reproduce

1. Start a loop with a large `max_iterations` budget (e.g., 500)
2. Send SIGTERM to the runner process (or let the host session end) while the runner is between state transitions — after a `route` event but before the next `state_enter`
3. Inspect `events.jsonl` in the run directory: `loop_complete.terminated_by` incorrectly shows `"max_iterations"` despite only 1 iteration completing
4. Inspect `state.json`: `status` shows `"interrupted"`, contradicting `events.jsonl`

## Root Cause

The FSMRunner shutdown / signal handler writes a `loop_complete` event before
exiting. The current implementation uses `"max_iterations"` as the `terminated_by`
label as a fallback whenever a `loop_complete` fires outside a natural terminal
state — without checking whether `self._iteration >= self.max_iterations`.

When a session is killed between a `route` event and the next `state_enter`:
1. The iteration counter has not yet incremented for the next state
2. The shutdown handler fires and emits `terminated_by: "max_iterations"`
3. `state.json` is updated with `status: "interrupted"` by the same path

The two fields end up contradicting each other.

**Likely location:** `scripts/little_loops/fsm/executor.py` — shutdown handler /
`loop_complete` emission path (`_finish("signal")` call sites at lines 316, 535).

## Impact

- **Priority**: P3 — Misleads users and audit tooling; retry/fleet tooling may misroute interrupted runs as budget-exhausted
- **Effort**: Small — Targeted change to the shutdown handler in `runner.py`; no new patterns required
- **Risk**: Low — Affects only the shutdown/interrupt path, not the normal execution hot path
- **Breaking Change**: No — corrects a misreported field value; downstream consumers keyed on `"interrupted"` will now receive accurate signals

**Downstream effects:**
- Users (and `/ll:audit-loop-run`) must cross-reference `state.json` against the
  `loop_complete` event to determine the real cause of a truncated run
- Budget-utilization analysis (`STEPS_CONSUMED / MAX_STEPS < 0.3`) correctly
  rejects budget-exhaustion as root cause, but only if the auditor knows to apply
  it; the `terminated_by` label alone is misleading
- Downstream tooling that branches on `terminated_by` (e.g., retry logic, fleet
  dashboards) may misclassify interrupted runs as budget-exhausted ones

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Actual attribute names (differ from the pseudo-code above):**
- Shutdown flag: `self._shutdown_requested` (not `self._interrupted`)
- Per-state step counter: `self.iteration` (incremented just before `state_enter`)
- Maintain-mode full-pass counter: `self._iteration_count`
- Step cap: `self.fsm.max_steps`; full-pass cap: `self.fsm.max_iterations`
- Current signal call: `return self._finish("signal")` in `executor.py`

**Current `terminated_by` vocabulary in `_finish()` call sites** (`executor.py`):
- `"signal"` — `_shutdown_requested` was True, or runner exit_code == -9
- `"max_steps"` — `self.iteration >= self.fsm.max_steps`
- `"max_iterations_reached"` — `self._iteration_count >= self.fsm.max_iterations` (maintain-mode only)
- `"terminal"`, `"timeout"`, `"error"`, `"handoff"`, `"cycle_detected"`, `"stall_detected"`

Note: The string `"max_iterations"` (bare, without `_reached`) does **not** appear at any `_finish()` call site in the current codebase. The observed value in the original run directory may reflect an older code version or a since-renamed path.

**Actual vocabulary mismatch** (the real bug): `events.jsonl` emits `terminated_by: "signal"` while `state.json` writes `status: "interrupted"`. The `PersistentExecutor.run()` status-mapping block in `persistence.py` (lines 783–806) explicitly translates `"signal"` → `"interrupted"` — so the two fields always disagree by design.

---

Two implementation options exist; a decision is required before starting:

### Option A — Rename `"signal"` → `"interrupted"` in `events.jsonl`

> **Selected:** Option A — Rename `"signal"` → `"interrupted"` — aligns with the established `"interrupted"` vocabulary in `state.json` and `RESUMABLE_STATUSES`, follows the prior `max_iterations` → `max_steps` rename precedent (score: 7/12)

Change all `_finish("signal")` call sites in `executor.py` to `_finish("interrupted")`. Update:
- `PersistentExecutor.run()` status-map in `persistence.py`: replace `"signal"` with `"interrupted"` in the lookup set
- `cli/loop/_helpers.py` exit-code map (lines 29–45): replace `"signal"` with `"interrupted"`
- `cli/logs.py::_derive_loop_outcome()` (lines 1756–1761): replace `"signal"` with `"interrupted"`
- All tests asserting `terminated_by == "signal"` → assert `== "interrupted"` (including `test_signal_emits_events_before_termination` at line 2114 in `test_fsm_persistence.py` and `test_shutdown_emits_loop_complete_event` in `test_fsm_executor.py`)

**Pro:** `events.jsonl` and `state.json` use the same vocabulary; downstream consumers key on one string.
**Con:** Wider change surface; breaks any external tooling that currently reads `"signal"` from `events.jsonl`.

### Option B — Keep `"signal"`, align `state.json` and audit tooling

Keep `_finish("signal")` as the canonical `terminated_by` for SIGTERM. Update `state.json`'s final-status mapping to write `status: "signal"` (not `"interrupted"`) so both files agree. Update the `RESUMABLE_STATUSES` frozenset in `persistence.py` (line 46) to include `"signal"` in place of (or alongside) `"interrupted"`. Update `audit-loop-run` to treat `terminated_by == "signal"` as `honest-failure` with root cause "session interrupted".

**Pro:** Smaller change; no test renaming; `"signal"` is a richer diagnostic value than `"interrupted"`.
**Con:** Requires updating `RESUMABLE_STATUSES` and any tooling that checks `state.status == "interrupted"` for resumability.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-30.

**Selected**: Option A — Rename `"signal"` → `"interrupted"` in `events.jsonl`

**Reasoning**: `"interrupted"` is already the canonical vocabulary for `state.json`, `RESUMABLE_STATUSES`, and `parallel/types.py`. The prior `max_iterations` → `max_steps` rename establishes the exact same sweep pattern (executor call sites + downstream consumers + tests), and the existing `_derive_loop_outcome()` already maps `"signal"` → `"interrupted"` at the display layer, confirming `"interrupted"` is the intended user-facing concept. Option B would introduce `"signal"` as a new `state.json` status value with no precedent in the status vocabulary, breaking the display layer, `_reconcile_stale_runs()`, and 4 existing tests.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Rename `"signal"` → `"interrupted"` | 2/3 | 1/3 | 3/3 | 1/3 | 7/12 |
| Option B — Keep `"signal"`, align `state.json` | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Option A: `"interrupted"` is established across `state.json`, `RESUMABLE_STATUSES`, and `parallel/types.py`; `_derive_loop_outcome()` already maps `"signal"` → `"interrupted"`; prior `max_iterations` → `max_steps` rename is a direct precedent; reuse score 2/3
- Option B: Introducing `"signal"` as a `state.json` status value has no precedent in the status vocabulary; would break `info.py` display layer, `_reconcile_stale_runs()`, and 4 test assertions; reuse score 1/3

## Integration Map

### Files to Modify

**Option A (rename `"signal"` → `"interrupted"`):**
- `scripts/little_loops/fsm/executor.py` — all `_finish("signal")` call sites (lines ~315, ~534); no change to `_finish()` body itself
- `scripts/little_loops/fsm/persistence.py::PersistentExecutor.run()` (lines 783–806) — replace `"signal"` with `"interrupted"` in the status-mapping `if` condition
- `scripts/little_loops/cli/loop/_helpers.py` (lines 29–45) — exit-code map references `"signal"`
- `scripts/little_loops/cli/logs.py::_derive_loop_outcome()` (lines 1756–1761) — `"signal"` in outcome category map

**Option B (keep `"signal"`, align `state.json`):**
- `scripts/little_loops/fsm/persistence.py::PersistentExecutor.run()` (lines 783–806) — change `final_status = "interrupted"` to `final_status = "signal"` (or rename `"interrupted"` → `"signal"` in `RESUMABLE_STATUSES`)
- `scripts/little_loops/fsm/persistence.py` (line 46) — `RESUMABLE_STATUSES` frozenset update
- `skills/audit-loop-run/SKILL.md` — Step 5 Phase 1 fault detection logic for `"signal"` root cause

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/_helpers.py:29–45` — exit-code logic branches on `terminated_by` value; affected by Option A rename
- `scripts/little_loops/cli/logs.py:1756–1761` — `_derive_loop_outcome()` maps `"signal"` to outcome category; affected by Option A rename
- `scripts/little_loops/transport.py:408–409,462–471` — OpenTelemetry transport handles `loop_complete` event; reads `terminated_by` from event dict
- `scripts/little_loops/session_store.py:115` — ingests `loop_complete` events; field stored as-is

### Tests

- `scripts/tests/test_fsm_persistence.py::TestSignalHandlingPersistence.test_signal_termination_saves_state_as_interrupted` (line 1945) — asserts `result.terminated_by == "signal"` and `state.status == "interrupted"`
- `scripts/tests/test_fsm_persistence.py::TestSignalHandlingPersistence.test_signal_emits_events_before_termination` (line 2114) — asserts `loop_complete["terminated_by"] == "signal"` from `events.jsonl` ← **this is the test that needs updating under Option A, or that validates Option B coverage is already present**
- `scripts/tests/test_fsm_executor.py::TestErrorHandling.test_shutdown_emits_loop_complete_event` (line ~2886) — asserts `loop_complete_events[0]["terminated_by"] == "signal"`
- `scripts/tests/test_fsm_persistence.py::TestPersistentExecutor.test_final_status_interrupted_on_max_steps` (line 979) — pattern to follow for the analogous `"signal"` path test

**New test needed (regardless of option chosen):**
- Test that simulates mid-run shutdown (between `route` and `state_enter`) using Approach B (runner calls `request_shutdown()` after first action) — verify the between-state race window produces the correct `terminated_by` in `events.jsonl`. Existing `test_signal_emits_events_before_termination` only covers the pre-run shutdown case.

### Similar Patterns

- `scripts/tests/test_fsm_persistence.py::TestPersistentExecutor.test_final_status_interrupted_on_max_steps` (line 979) — follow this structure for adding between-state-race test
- `scripts/tests/test_fsm_executor.py::TestErrorHandling.test_shutdown_emits_loop_complete_event` (line ~2886) — pattern for asserting `loop_complete.terminated_by` from FSMExecutor directly

## Acceptance Criteria

- [ ] Killing a loop mid-run with SIGTERM emits a consistent `terminated_by` value in `events.jsonl` (see vocabulary decision — Option A: `"interrupted"`; Option B: `"signal"`)
- [ ] `state.json` `status` and `events.jsonl` `terminated_by` agree semantically after any shutdown path (either both signal-vocabulary or both interrupted-vocabulary)
- [ ] A loop that genuinely exhausts `max_steps` still emits `terminated_by: "max_steps"` (unchanged); a maintain-mode loop exhausting `max_iterations` still emits `terminated_by: "max_iterations_reached"` (unchanged)
- [ ] Mid-run shutdown (signal received **between** `route` and `state_enter`) produces the same correct `terminated_by` as pre-run shutdown — verified by a new test using `ShutdownAfterFirstRunner` pattern (see `test_signal_interrupted_loop_can_be_resumed` at line 2038 in `test_fsm_persistence.py` for the fixture pattern)
- [ ] `/ll:audit-loop-run` on a SIGTERM-interrupted run reports `honest-failure` with root cause "session interrupted" rather than prompting budget-exhaustion analysis

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-30_

**Readiness Score**: 76/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 72/100 → MODERATE RISK

### Concerns
- The proposed fix code block (`self._iteration >= self.max_iterations`, `self._interrupted`) references attributes that do not exist in the current `FSMExecutor`. Current code uses `self._shutdown_requested` and calls `_finish("signal")`. The implementer must adapt to current patterns.
- The issue names `runner.py` as the file to modify; the actual paths are `executor.py::_finish()` (line 2046) and `persistence.py::PersistentExecutor.run()` (lines 783–788).

### Gaps to Address
- Decide whether `loop_complete` should emit `terminated_by: "interrupted"` (matching state.json) or keep `"signal"` and update state.json vocabulary accordingly.
- Extend `test_signal_termination_saves_state_as_interrupted` (or add a new test) to assert `loop_complete.terminated_by == "interrupted"` in `events.jsonl`, not only `state.status`.

### Outcome Risk Factors
- **Test coverage gap on the exact field**: existing tests verify `state.status` consistency but skip the `loop_complete.terminated_by` value in `events.jsonl`. Implement tests first so the fix is verified at the correct layer.
- **Open decision on string vocabulary**: `"signal"` vs `"interrupted"` as the canonical `terminated_by` label for session kills. Downstream consumers of `"signal"` (audit-loop-run, retry logic) may need updating — resolve before starting.

## Resolution

Implemented Option A: renamed `terminated_by: "signal"` → `"interrupted"` across the FSM runner.

**Changes:**
- `fsm/executor.py`: both `_finish("signal")` call sites → `_finish("interrupted")`
- `fsm/persistence.py`: status-map condition updated to match `"interrupted"`
- `cli/loop/_helpers.py`: `EXIT_CODES` key and `_is_success` check updated
- `cli/logs.py`: `_derive_loop_outcome()` tuple updated
- `fsm/types.py`: docstring vocabulary updated
- Tests: 18+ assertions in `test_fsm_executor.py` + 6 in `test_fsm_persistence.py` updated to expect `"interrupted"`; new test `test_mid_run_shutdown_emits_interrupted_in_events_jsonl` added to cover the between-state race window

## Status

**Done** | Created: 2026-06-30 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-30T17:03:16 - `b8654ad8-857c-4060-9dae-d6d23ec37f24.jsonl`
- `/ll:confidence-check` - 2026-06-30T17:30:00Z - `aa2acd27-7309-4093-9b7b-f3b346b3f2e7.jsonl`
- `/ll:decide-issue` - 2026-06-30T16:55:57 - `8e9755e7-7d29-464a-bd7a-9e1b831a62db.jsonl`
- `/ll:refine-issue` - 2026-06-30T16:48:58 - `f0b87735-4bf8-4166-a015-f579bb5467a7.jsonl`
- `/ll:format-issue` - 2026-06-30T16:34:06 - `833dc57f-03e9-4170-bd03-9f2f1952ca00.jsonl`
- `/ll:confidence-check` - 2026-06-30T00:00:00Z - `8a1adc05-14e5-4b8e-bd82-6f1d6ea6c6da.jsonl`
