---
id: BUG-1674
type: BUG
priority: P2
status: open
discovered_date: 2026-05-24
discovered_by: downstream-report
relates_to: [FEAT-1637]
confidence_score: 90
outcome_confidence: 80
---

# BUG-1674: StallDetector is blind to progress made by states with unconditional `next:` transitions

## Summary

`StallDetector` only records `(state, exit_code, verdict)` triples for states whose `_execute_state` reaches line 815 of `scripts/little_loops/fsm/executor.py`. States with an unconditional `next:` and no `evaluate:` take the early return at `executor.py:777` and never call `_stall_detector.record(...)`. Consequence: the detector cannot distinguish a *real* stall (same eval verdict, no work between cycles) from *slow but real* progress (same eval verdict, but an intermediate non-eval state made file-level changes between cycles). With `window: 3`, three visits to any eval-bearing state with identical verdict will fire the stall — even if the loop is iterating productively.

## Steps to Reproduce

Downstream report: `ll-marketing/.issues/bugs/P2-BUG-004-general-task-stalled-on-check-done.md`.

1. Use an FSM loop with a `check↔work` ping-pong where the work state uses `next:` (no `evaluate:`) — e.g. `general-task.yaml`'s `continue_work` state.
2. Run the loop against a task with many DoD criteria (~15+ unchecked).
3. Observe eval-bearing state (`check_done`) visited at iterations 4, 6, 8 — each returning `(check_done, 0, "no")` because the DoD still has ~16 unchecked criteria.
4. Between those visits, `continue_work` (iterations 5, 7) completes plan steps and flips DoD criteria from `[ ]` to `[x]` — real, file-level progress.
5. Observe: stall detector fires on the third identical `check_done` verdict and routes to `diagnose → failed`, killing the loop despite incremental progress.

## Root Cause

`scripts/little_loops/fsm/executor.py:751-777` — the `if state.next:` early-return path executes the action and routes via `state.next` without ever reaching the stall-detector record block at `executor.py:815-817`. So in any loop with a check↔work ping-pong where the work state uses `next:` (no `evaluate:`), the detector's deque fills with consecutive identical triples from the eval-bearing state regardless of intermediate productive work.

`general-task.yaml`'s `continue_work` matches this exactly: `action_type: prompt`, `next: check_done`, no `evaluate:`.

The detector is doing what it's documented to do (`stall_detector.py:1-11`), but the documented contract — "the same state produces the same exit code and verdict across consecutive iterations" — is itself the bug. "Consecutive in eval-bearing terms" is not the same as "consecutive without productive intermediate work," and the detector treats them identically.

## Current Behavior

`StallDetector` records `(state, exit_code, verdict)` triples only for states that reach `_stall_detector.record()` in `_execute_state`. States with an unconditional `next:` transition take the early-return path at `executor.py:777` and never call `record()`. With `window: 3`, three consecutive visits to any eval-bearing state with identical verdicts triggers the stall signal — even when intermediate non-eval states have made real file-level changes between cycles. The detector treats "same eval verdict" as equivalent to "no progress."

## Expected Behavior

The stall detector should not fire when intermediate state activity has measurably advanced the loop's working state since the previous record. Concretely: if observable artifacts the loop writes to (e.g. files under the loop's tmp dir, or a configured fingerprint set) changed between two `record()` calls for the same eval-bearing state, the deque should be reset.

The detector should still fire promptly for genuine no-progress loops: same verdict, zero file changes between cycles.

## Proposed Solution

Make the detector progress-aware. Two implementation sketches:

**Option A — Fingerprint-based reset, opt-in per loop:**
- Extend `RepeatedFailureConfig` (`fsm/schema.py:774-806`) with an optional `progress_paths: list[str]` (or `progress_glob`) field. When set, the executor hashes those paths' (mtime, size) — or a content hash for small files — before calling `record(...)` and passes the fingerprint in. `StallDetector.record(state, exit_code, verdict, fingerprint)` resets the deque if the fingerprint differs from the previous record for that state.
- Default behavior (no `progress_paths`) preserves current semantics — no regression for existing loops that rely on the detector.

**Option B — Generic intermediate-state-activity tracker:**
- Executor tracks a monotonic "productive activity counter" that increments whenever any non-eval-bearing state's action exits 0 (or writes a tracked artifact). The detector resets if the counter advanced between two records of the same triple.
- Less configuration, but harder to define "productive" generically — risks false negatives (a tracked state that does nothing useful still counts).

Recommend **Option A**: explicit, easy to reason about, no behavior change for loops that don't opt in. `general-task.yaml` would declare:
```yaml
circuit:
  repeated_failure:
    window: 3
    on_repeated_failure: diagnose
    progress_paths:
      - "${env.PWD}/.loops/tmp/general-task-plan.md"
      - "${env.PWD}/.loops/tmp/general-task-dod.md"
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/stall_detector.py` — extend `record()` to accept optional fingerprint; reset deque on fingerprint change
- `scripts/little_loops/fsm/executor.py` — compute path fingerprint before calling `record()` in `_execute_state`
- `scripts/little_loops/fsm/schema.py` — extend `RepeatedFailureConfig` with optional `progress_paths: list[str]`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/general-task.yaml` — add `progress_paths` under `circuit.repeated_failure`
- Any loop YAML using `circuit.repeated_failure` with `next:`-only work states (search: `repeated_failure` in `loops/`)

### Similar Patterns
- `scripts/little_loops/fsm/circuit_breaker.py` — compare fingerprint-reset pattern if one exists
- Other loop YAMLs with `check↔work` patterns: audit after fix

### Tests
- `scripts/tests/fsm/test_stall_detector.py` — add tests for progress-aware reset; confirm existing no-progress behavior unchanged
- Integration test: `general-task` loop with ~15 DoD criteria iterates ≥10 `check_done` cycles without stalling

### Documentation
- `docs/reference/API.md` — document new `progress_paths` field on `RepeatedFailureConfig`
- Loop authoring guide (if exists) — describe when to use `progress_paths`

### Configuration
- `scripts/little_loops/loops/general-task.yaml` — add `progress_paths` entries for plan and DoD files

## Implementation Steps

1. Extend `RepeatedFailureConfig` in `fsm/schema.py` with `progress_paths: list[str] = field(default_factory=list)`
2. In `_execute_state` (`fsm/executor.py`), compute `(mtime, size)` fingerprint for each path in `repeated_failure.progress_paths` before calling `_stall_detector.record()`
3. Update `StallDetector.record()` to accept optional `fingerprint` arg; reset `deque` if fingerprint differs from previous call for that state
4. Update `general-task.yaml` to declare `progress_paths` pointing to `.loops/tmp/general-task-plan.md` and `.loops/tmp/general-task-dod.md`
5. Add tests: progress-aware reset (fingerprint changes → deque resets), no-progress still fires (same fingerprint → deque fills), backward compat (no `progress_paths` → current semantics)

## Workaround (already applied)

`scripts/little_loops/loops/general-task.yaml` `circuit.repeated_failure.window` widened from 3 to 7 (this commit). Buys runway for slow-progress cycles but doesn't fix the underlying class of bug — any loop with a long check↔work tail that uses `next:` for the work state is still vulnerable, and the threshold is necessarily a guess.

## Acceptance Criteria

- [ ] Stall detector does not fire when a state with unconditional `next:` made observable file-level changes between two consecutive identical verdicts of an eval-bearing state.
- [ ] A `general-task` run with ~15 unchecked DoD criteria iterates at least 10 `check_done` cycles without stalling, provided `continue_work` writes to the plan or DoD file each cycle.
- [ ] Stall detector still fires within `window` cycles for a genuine no-progress loop (same verdict, zero file changes between cycles).
- [ ] Existing loops that don't opt into progress tracking retain current detector semantics (no regression in `tests/fsm/test_stall_detector.py`).

## Impact

- **Priority**: P2 — False-positive stall fires kill productive loops prematurely; directly observed in `general-task`; affects any loop with `next:`-only work states
- **Effort**: Medium — Well-defined Option A; touches 3 files (schema, executor, stall_detector) plus loop YAML and tests; no novel patterns required
- **Risk**: Medium — Changes FSM executor and stall detector core; Option A is opt-in so existing loops without `progress_paths` are unaffected; regression risk bounded to `test_stall_detector.py`
- **Breaking Change**: No (opt-in `progress_paths` field; default behavior preserved)

## Labels

`stall-detector`, `fsm`, `executor`, `false-positive`

## Notes

- Related: BUG-1657 (general-task evaluate prompt simplification) — different bug, same loop.
- Related: FEAT-1637 (original stall detector).
- The downstream issue's "raise stall threshold" proposal is the workaround, not the fix. The "task should be scoped narrowly enough that DoD gap closes within ~3 cycles" proposal is unworkable for general-purpose loops that take arbitrary task input.

---

**Open** | Created: 2026-05-24 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-05-24T07:24:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4bd7f585-d3e7-44e3-81e4-3bd5de0cef5d.jsonl`
