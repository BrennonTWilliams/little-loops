---
captured_at: '2026-05-28T17:31:20Z'
discovered_date: 2026-05-28
discovered_by: capture-issue
status: open
labels:
- bug
- captured
- fsm
- stall-detector
- loops
relates_to: [BUG-1674, BUG-1766]
---

# BUG-1767: StallDetector `progress_paths` fingerprint is defeated by loops that mutate their own progress-path files

## Summary

`BUG-1674` (done) made `StallDetector` progress-aware by fingerprinting a configured set
of `progress_paths` and resetting the stall deque whenever those files change between
records. But when a loop's `progress_paths` point at files the loop **mutates every
iteration as part of its own bookkeeping**, the fingerprint always changes, the deque
always resets, and the detector **never fires** — even during a genuine no-real-progress
spin.

`general-task.yaml` is the live example: its `progress_paths` are the plan/DoD tracking
files (`general-task-plan.md`, `general-task-dod.md`, lines 18–20), and its `continue_work`
state appends to `plan.md` on every cycle. In audit run `2026-05-28T145405`, the loop spun
for ~40 iterations re-executing finished work (see [[BUG-1766]]) and the audit recorded
**"no fault signals"** — because each `continue_work` append registered as "progress" and
reset the stall window. The detector is counting "the loop wrote to its own scratchpad" as
real progress.

## Current Behavior

- `StallDetector` records `(state, exit_code, verdict)` and, per BUG-1674, a fingerprint
  of `progress_paths` (mtime/size or content hash).
- On each record, if the fingerprint differs from the prior record for that state, the
  deque resets.
- In `general-task`, `continue_work` appends a remediation step to `plan.md` every cycle,
  so the fingerprint of `plan.md` changes every cycle → deque resets every cycle → the
  stall signal can never accumulate to its `window`.
- Net effect: the BUG-1674 hardening is **disabled in practice** for any loop whose
  `progress_paths` overlap its own write targets.

## Expected Behavior

The detector should distinguish **real working-state progress** from **the loop touching
its own bookkeeping files**. Options to evaluate during refinement:

- **Separate the signals**: a loop should be able to declare progress paths that are
  *distinct* from its internal tracking artifacts (the work surface vs. the scratchpad),
  so appending to its own plan/DoD does not count as progress.
- **Content-semantic fingerprint**: instead of mtime/size, hash only the *meaningful*
  content (e.g. count of checked criteria) so that appending a duplicate/no-op step does
  not reset the deque.
- **Per-loop guidance/lint**: at minimum, warn (via `ll-loop validate`) when a loop's
  `progress_paths` intersect files written by its own prompt/shell actions, since that
  configuration silently neuters the stall guard.

The detector must still fire promptly for genuine no-progress loops.

## Steps to Reproduce

1. Configure a loop with `circuit.repeated_failure.progress_paths` pointing at a file the
   loop appends to every iteration (e.g. `general-task`'s `plan.md`).
2. Drive it into a state cycle that makes no real progress but keeps appending to that file
   (e.g. the BUG-1766 `continue_work → select_step → … → count_done → continue_work` spin).
3. Observe: the stall detector never fires despite many no-progress cycles; the loop runs
   to convergence or `max_iterations` with no fault signal emitted.

## Root Cause

- **File**: `scripts/little_loops/fsm/stall_detector.py` — fingerprint-reset logic added by
  BUG-1674; resets the deque on any `progress_paths` change.
- **File**: `scripts/little_loops/fsm/executor.py` — computes the fingerprint passed into
  `record(...)`.
- **Config surface**: `scripts/little_loops/loops/general-task.yaml` lines 18–20 —
  `progress_paths` set to files the loop itself mutates.
- **Cause**: the fingerprint treats *any* change to a progress path as evidence of forward
  progress. It cannot tell a real artifact change from the loop's own bookkeeping append,
  so a self-appending loop can never trip the stall window.

## Proposed Solution

Refine the BUG-1674 mechanism so self-mutated bookkeeping files don't mask stalls. Likely
the cleanest: distinguish "progress paths" (external work surface) from the loop's internal
tracking files, and/or fingerprint semantic content rather than mtime/size. Add an
`ll-loop validate` warning when `progress_paths` overlap the loop's own write targets.
Decide the concrete approach during `/ll:refine-issue` — both the detector semantics and
the general-task config need to land together.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/stall_detector.py` — fingerprint/reset semantics.
- `scripts/little_loops/fsm/executor.py` — fingerprint computation passed to `record(...)`.
- `scripts/little_loops/loops/general-task.yaml` — `progress_paths` config (and any other
  loop with the same overlap).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/schema.py` — `RepeatedFailureConfig.progress_paths` (validation
  / possible new field for semantic vs. mtime fingerprinting).

### Tests
- `scripts/tests/` FSM/stall-detector tests — add a regression that a loop appending to a
  `progress_paths` file every cycle still trips the stall window when no semantic progress
  occurs.

### Similar Patterns
- Audit other loops with `circuit.repeated_failure.progress_paths` for the same overlap
  between progress paths and self-write targets.

### Documentation
- `docs/guides/LOOPS_GUIDE.md` / stall-detector reference — document that `progress_paths`
  must point at the external work surface, not the loop's own tracking files.

### Configuration
- Possible new schema field to opt into semantic-content fingerprinting.

## Implementation Steps

1. Decide detector approach (separate progress paths from tracking files vs. semantic
   fingerprint) during refinement.
2. Implement the chosen detector change in `stall_detector.py` / `executor.py`.
3. Fix `general-task.yaml` `progress_paths` to match the new contract.
4. Add an `ll-loop validate` warning for `progress_paths` ∩ self-write targets.
5. Add regression tests; sweep other loops for the same misconfiguration.

## Impact

- **Priority**: P3 — Reliability gap in a safety mechanism, not an outage. It silently
  disables the BUG-1674 stall guard for self-appending loops, allowing wasted iterations
  (see BUG-1766) to go undetected. Bounded by `max_iterations`.
- **Effort**: Medium — touches detector semantics plus config and validation; needs a
  decision on approach.
- **Risk**: Medium — changing stall semantics affects every loop using `progress_paths`;
  must avoid regressing real-progress detection (the original BUG-1674 goal).
- **Breaking Change**: Possibly — if a new `progress_paths` contract requires existing
  loops to reconfigure.

## Related Key Documentation

- [[BUG-1674]] — introduced the `progress_paths` fingerprint reset this issue refines.
- [[BUG-1766]] — the general-task spin that this detector gap failed to catch.

## Labels

`bug`, `captured`, `fsm`, `stall-detector`, `loops`

## Session Log
- `/ll:capture-issue` - 2026-05-28T17:31:20Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d72d4842-d084-41b6-af0f-1adf964926ab.jsonl`

---

**Open** | Created: 2026-05-28 | Priority: P3
