---
id: ENH-2689
title: "autodev: add reconcile step for stale issue-body sections after spike/refine plateau"
type: ENH
priority: P2
status: open
captured_at: '2026-07-19T04:38:59Z'
discovered_date: 2026-07-19
discovered_by: capture-issue
relates_to:
- FEAT-2672
labels:
- loops
- autodev
- refine-issue
---

# ENH-2689: autodev: add reconcile step for stale issue-body sections after spike/refine plateau

## Summary

`autodev.yaml`'s refine/spike/re-confidence-check cycle can plateau: `/ll:refine-issue`
only **appends** new "Codebase Research Findings" bullets when it discovers a
correction, but never rewrites the issue's own Implementation Steps /
Acceptance Criteria / Files to Modify sections to match. When those sections
contradict the accumulated findings, `/ll:confidence-check` re-flags the same
Concern every pass and the Readiness score never moves — the loop eventually
exhausts its remedies (`run_spike`, `run_wire`, `run_decide`) and defers the
issue via `low_readiness`, even though the underlying technical/architectural
blocker was already resolved.

## Motivation

Observed directly on `FEAT-2672` (`ll-loop run autodev FEAT-2672`, 2026-07-18):
six consecutive `/ll:confidence-check` passes reported the identical Concern —
"Implementation Steps 1-3 and AC bullet 2 still describe the superseded 'stub
emission + on-demand resolution' framing instead of the corrected mechanism
... Rewrite both sections before implementation" — while multiple
`/ll:refine-issue` passes (including a successful `/ll:spike` that proved the
corrected mechanism against the installed SDK) kept appending new research
findings that explained the correction without ever editing the stale
sections themselves. Readiness stayed pinned at 78/100 across the whole run;
the loop exhausted `run_spike` → `rerun_confidence_after_spike` →
`recheck_after_size_review` and deferred the issue as `low_readiness` after
25m49s / 35 iterations, even though the spike had already retired the
"novel mechanism" risk that was the issue's real architectural blocker.

This wastes an entire autodev run on an issue that a single targeted rewrite
of three sections would have unblocked, and produces a `deferred_reason:
low_readiness` state that mischaracterizes the issue as under-researched
when it was actually over-researched but never reconciled back into its own
body.

## Current Behavior

In `scripts/little_loops/loops/autodev.yaml`, after `run_spike` proves (or
attempts) an unproven mechanism, `rerun_confidence_after_spike` re-runs
`/ll:confidence-check` and routes straight to `enqueue_or_skip` →
`check_spike_needed_before_skip` → `recheck_after_size_review`, which does a
final `ll-issues check-readiness` and defers the issue on failure
(`P[...]:842-867`). There is no comparison between the pre-spike and
post-spike Concerns text/score, and no state that asks `/ll:refine-issue` (or
an equivalent) to reconcile the issue body's Implementation
Steps/AC/Files-to-Modify against the Codebase Research Findings that have
already been appended.

## Expected Behavior

When a confidence-check pass's Readiness score is unchanged (or its Concerns
text substantially repeats) from the immediately preceding pass in the same
run, the loop should recognize this as a "findings accumulated but body not
reconciled" plateau and route to a reconcile step that rewrites the stale
sections from the latest research findings — not append another finding —
before falling through to the existing spike/wire/size-review remedies or
`low_readiness` deferral.

## Implementation Steps

1. Add a `reconcile_current` state to `autodev.yaml` (or a `--reconcile`
   mode to `/ll:refine-issue`) that rewrites Implementation Steps,
   Acceptance Criteria, and Files to Modify in place from the issue's own
   accumulated "Codebase Research Findings" / "Wiring Phase" sections,
   rather than appending another finding bullet.
2. Detect the plateau condition: compare the Readiness score (and/or
   Concerns text) from the confidence-check pass before `run_spike` against
   the one from `rerun_confidence_after_spike`. If unchanged, route to
   `reconcile_current` instead of falling straight through to
   `enqueue_or_skip`.
3. After `reconcile_current`, re-run `/ll:confidence-check` once more before
   continuing to the existing `enqueue_or_skip` / `low_readiness` path, so a
   successful reconciliation gets one more chance to cross the readiness
   threshold.
4. Guard against infinite reconcile loops the same way `check_spike_needed`
   guards `run_spike` (a one-shot flag, e.g. `reconcile_attempted`, checked
   before routing).

## Acceptance Criteria

- [ ] An issue whose confidence-check Concerns repeat verbatim (or Readiness
      score is bit-identical) across the pre-spike and post-spike passes
      routes to a reconcile step instead of immediately falling to
      `low_readiness`.
- [ ] The reconcile step measurably rewrites (not just appends to) the
      stale Implementation Steps/AC/Files-to-Modify sections.
- [ ] Reconcile runs at most once per issue per autodev run (one-shot guard,
      mirroring `check_spike_needed`'s `spike_attempted` pattern).
- [ ] Existing `run_spike`/`run_wire`/`low_readiness` remedy paths are
      unaffected for issues that don't hit the plateau condition.

## Related Key Documentation

None linked — `documents.enabled` scan did not surface a match for this
loop-internals change; see `docs/generalized-fsm-loop.md` and
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` if wiring this by hand.

## Session Log
- `/ll:capture-issue` - 2026-07-19T04:38:59Z - captured from conversation diagnosing why `FEAT-2672` was deferred (`ll-loop run autodev FEAT-2672`, 2026-07-18)

## Status

**Open** | Created: 2026-07-19 | Priority: P2
