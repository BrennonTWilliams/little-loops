---
id: 2986
title: autodev loop does not clear `autodev-inflight` sentinel on NOT_READY path
type: BUG
priority: P2
status: open
discovered_date: 2026-08-01
labels:
- little-loops
- autodev
- loop-mechanics
- sentinel
- finalize
- bug104-followup
---

# BUG-2986: autodev loop does not clear `autodev-inflight` sentinel on NOT_READY path

## Summary

The autodev loop's `implement_current.on_no` chain
(`check_learning_gate` → `check_impl_auth` → `dequeue_next`) sets the
`autodev-inflight` sentinel at `dequeue_next:99` but does not clear it
on the failure paths. As a result, a NOT_READY verdict (e.g., from
`ready-issue` not producing a clean implementation) is misclassified
by `finalize_done` as `inflight_at_finalize` — a sentinel-still-set
abandon rather than a clean "issue did not close" outcome. This is
the exact mechanism that produced the BUG-104 anomaly run on
2026-08-01 (the autodev run's exit reason was
`Unverified (2): BUG-104,BUG-104  inflight_at_finalize`).

## Current Behavior

In `scripts/little_loops/loops/autodev.yaml`:

1. `dequeue_next:99` writes the `autodev-inflight` sentinel when a
   new issue is dequeued for implementation.
2. `finalize_done` classifies the run exit as `inflight_at_finalize`
   when the sentinel is still set at the end of the run.
3. The `implement_current.on_no` chain
   (`check_learning_gate` → `check_impl_auth` → `dequeue_next`) clears
   the sentinel only on the success / skip / decomposition /
   gate-block paths. The NOT_READY path (the failure path that
   occurs when `ready-issue` does not produce a closeable outcome)
   does not clear the sentinel before reaching `dequeue_next`.
4. Result: a NOT_READY verdict is recorded as `inflight_at_finalize`
   on the next run's `finalize_done`, double-classifying the issue
   (once as the actual not-closed outcome, then as
   `inflight_at_finalize`).

This is the same `rm -f autodev-inflight` idiom the skip states
already use, just applied to the implementation-failure path.

## Expected Behavior

The autodev loop's `implement_current.on_no` chain should clear the
`autodev-inflight` sentinel before reaching `dequeue_next` on the
NOT_READY path, so a NOT_READY verdict is recorded as a clean
non-pass rather than as `inflight_at_finalize`. The skip-state
siblings (`scripts/little_loops/loops/autodev.yaml:392-443`) already
implement this pattern with `rm -f ${context.run_dir}/autodev-inflight`
in their action.

## Reproduction

1. Run `ll-loop run autodev <issue-id>` against a hub that triggers
   the NOT_READY path (e.g., a hub with a `ready-issue`-not-ready
   verdict).
2. Inspect the run's exit reason — it will end with
   `inflight_at_finalize` rather than a clean NOT_READY.
3. Cross-reference `scripts/little_loops/loops/autodev.yaml:99` and
   the `finalize_done` chain — the sentinel is still set at the end
   of the run because the NOT_READY path does not clear it.

## Patch Sketch (R3 from the BUG-104 analysis)

```yaml
# scripts/little_loops/loops/autodev.yaml
check_impl_auth:
  # ... existing on_yes/on_no/on_error unchanged ...
  on_no: clear_inflight_and_drain
  on_error: dequeue_next          # was: dequeue_next

clear_inflight_and_drain:
  # R3: a non-learning-gate, non-auth failure (e.g. ready-issue NOT_READY)
  # is a clean "issue did not close" outcome, not an in-flight abandon.
  # Clear the sentinel so finalize_done does not misclassify as
  # inflight_at_finalize.
  action: |
    rm -f ${context.run_dir}/autodev-inflight
  action_type: shell
  next: dequeue_next
  on_error: dequeue_next
```

This is the same `rm -f autodev-inflight` idiom the skip states
already use, just applied to the implementation-failure path.

## Acceptance Criteria

- `scripts/little_loops/loops/autodev.yaml` includes a new
  `clear_inflight_and_drain` state that removes the
  `autodev-inflight` sentinel from `${context.run_dir}`.
- `check_impl_auth.on_no` routes through `clear_inflight_and_drain`
  before `dequeue_next`.
- A test in `tests/test_autodev_loop.py` (or equivalent) executes a
  synthetic NOT_READY path and asserts the exit reason is
  NOT_READY (not `inflight_at_finalize`).
- The autodev run on 2026-08-01's `inflight_at_finalize` exit reason
  no longer reproduces on a re-run of the same input.

## Source Doc

- `~/AIProjects/brenentech/little-loops/postmortems/autodev-bug104-failure-analysis-2026-08-01.md` R3 section — the full R3 patch sketch and rationale.
- `scripts/little_loops/loops/autodev.yaml:99` — the inflight write site.
- `scripts/little_loops/loops/autodev.yaml:392-443` — the skip-state
  siblings that already implement the `rm -f autodev-inflight` idiom.
- `scripts/little_loops/loops/autodev.yaml:883` — the `check_impl_auth.on_no` → `dequeue_next` edge that needs to route through `clear_inflight_and_drain` first.

## Status

**Open** | Created: 2026-08-02
