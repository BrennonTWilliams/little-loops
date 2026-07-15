---
id: BUG-2654
type: BUG
priority: P3
status: open
captured_at: '2026-07-15T21:40:10Z'
discovered_date: 2026-07-15
discovered_by: capture-issue
labels:
- fsm
- loops
- autodev
- confidence
- spike
relates_to:
- ENH-2640
- BUG-2650
- ENH-2568
parent: EPIC-2570
---

# BUG-2654: autodev spike remedy bypassed for spike_needed issues on the decide path

## Summary

The `check_spike_needed` → `run_spike` remediation branch that ENH-2640 added to
`autodev.yaml` is only reachable from `triage_outcome_failure` (the
`check_passed.on_no` path). An issue that is **both** `decision_needed: true`
**and** `spike_needed: true` is routed down the **decide path**
(`check_decision_* → run_decide → … → recheck_after_decide → snap_and_size_review
→ run_size_review → enqueue_or_skip → recheck_after_size_review`), which never
visits `check_spike_needed`. The spike remedy is structurally bypassed and the
issue is skipped as `low_readiness` even though an applicable remedy exists.

## Root Cause

`scripts/little_loops/loops/autodev.yaml` — the spike gate is wired onto a single
edge. ENH-2640 retargeted only `triage_outcome_failure.on_no`
(`check_missing_artifacts` → `check_spike_needed`). The decide path resolves the
decision, re-scores, and when outcome confidence is still below threshold it
routes `recheck_after_decide.on_no → snap_and_size_review → run_size_review`
(autodev.yaml:355, 386-404). From there `enqueue_or_skip.on_no →
recheck_after_size_review` (autodev.yaml:807) skips the issue with
`low_readiness` (autodev.yaml:823) without ever checking `spike_needed`.

`triage_outcome_failure` (autodev.yaml:665) — the only state that reaches the
spike gate — sits on the `check_passed.on_no` edge (autodev.yaml:205), which is
mutually exclusive with the decide path in a given iteration.

## Current Behavior

Observed on the `ll-loop run autodev BUG-2650` run
(`.loops/runs/autodev-20260715T161809/`, 2026-07-15). BUG-2650 carried both an
Option A/B decision block (`decision_needed: true`) and `spike_needed: true`
(unproven root-cause mechanism). The loop:

1. refined it, ran `/ll:decide-issue` (resolved Option A),
2. re-ran `/ll:confidence-check` → outcome_confidence 68 (< 75 threshold),
3. `recheck_after_decide` failed → `snap_and_size_review` → `run_size_review`,
4. size-review declined to decompose (no children),
5. `recheck_after_size_review` failed again → wrote `BUG-2650  low_readiness` to
   `autodev-skipped.txt` and dequeued.

`/ll:spike` — the remedy that could have lifted the outcome score — was never
invoked, despite `spike_needed: true` being set.

## Expected Behavior

A `spike_needed: true` (and not-yet-`spike_attempted`) issue reaches
`check_spike_needed → run_spike → rerun_confidence_after_spike` regardless of
whether it also carried a `decision_needed` flag — i.e. the decide path checks
for a pending spike after the decision is resolved and re-scored, before falling
through to size-review-then-skip. The `spike_attempted` one-shot guard still
prevents a completed-or-attempted spike from re-running.

## Steps to Reproduce

1. Have an issue with `decision_needed: true`, `spike_needed: true`,
   `spike_attempted` unset, confidence_score ≥ readiness_threshold, and
   outcome_confidence below `outcome_threshold` (75) — e.g. BUG-2650 before any
   spike.
2. `ll-loop run autodev <ID>`.
3. Observe the run dumps `<ID>  low_readiness` to
   `${run_dir}/autodev-skipped.txt`; `usage.jsonl` shows `run_decide`,
   `rerun_confidence_after_decide`, `run_size_review` but **no** `run_spike`
   state.

## Proposed Solution

Insert a `check_spike_needed` gate on the decide path so a pending spike is
attempted before the issue is skipped. Candidate insertion point:
`recheck_after_size_review` (the decide/size-review terminal skip at
autodev.yaml:810-830) — before writing `low_readiness`, route a
`spike_needed AND NOT spike_attempted` issue to `run_spike` rather than skipping.
Alternatively, retarget `recheck_after_decide.on_no` (or
`snap_and_size_review`) through `check_spike_needed` first.

Decide the exact edge at implementation time, but the invariant is: **every path
that ends in a `low_readiness` skip must first give a not-yet-attempted
`spike_needed` issue its one shot at `run_spike`.** Reuse the existing
`check_spike_needed` / `run_spike` / `rerun_confidence_after_spike` states
(autodev.yaml:683-731) — this is a routing/edge change plus (possibly) a small
re-entry guard, not new states. Mind the `spike_attempted` one-shot guard so the
decide-path and triage-path spike checks don't double-fire in one iteration.

## Files to Modify

- `scripts/little_loops/loops/autodev.yaml` — add a spike check on the decide /
  size-review skip path (candidate: `recheck_after_size_review`, autodev.yaml:810,
  and/or `recheck_after_decide.on_no`, autodev.yaml:355).

## Tests

- `scripts/tests/test_builtin_loops.py` — add a routing test asserting the
  decide-path skip edge reaches `check_spike_needed` (or `run_spike`) for a
  `spike_needed` issue; regression that a non-spike issue still skips via
  `low_readiness`. Clone the ENH-2640 spike-triad routing test cluster.
- `scripts/tests/test_autodev_decision_gate.py` — whole-file
  `test_autodev_yaml_loads_and_validates` stays zero-`ERROR` (MR-1..MR-11) after
  the edge change; add a structural/routing assertion for the new decide-path
  spike edge.

## Acceptance Criteria

1. An issue with `decision_needed: true` + `spike_needed: true` +
   `spike_attempted` unset that fails outcome after decide+size-review reaches
   `run_spike` (invokes `/ll:spike --auto`) before any `low_readiness` skip.
2. The `spike_attempted` one-shot guard prevents the spike from running twice in
   one iteration across the triage and decide paths.
3. A non-`spike_needed` issue still skips via `recheck_after_size_review`'s
   `low_readiness` path unchanged (regression).
4. `python -m pytest scripts/tests/test_builtin_loops.py
   scripts/tests/test_autodev_decision_gate.py` passes; `autodev.yaml` loads with
   zero `ValidationSeverity.ERROR`.

## Related Issues

- **ENH-2640** — added the `check_spike_needed`/`run_spike`/`rerun_confidence_after_spike`
  states, but only wired the gate onto `triage_outcome_failure.on_no` (the
  no-decision path). This bug is the uncovered decide path.
- **BUG-2650** — the concrete instance skipped as `low_readiness` because its
  spike remedy was bypassed on the decide path.
- **ENH-2568** — parent theme (autodev spike triage routing).
- **EPIC-2570** — spike workflow / confidence-flag / autodev-routing epic.

## Status

- **Current Status**: open
- **Blockers**: None — self-contained routing/edge change reusing existing states.

## Session Log
- `/ll:capture-issue` - 2026-07-15T21:40:10Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2a4fbb3-4941-4589-a115-5db99a56d98b.jsonl`
</content>
</invoke>
