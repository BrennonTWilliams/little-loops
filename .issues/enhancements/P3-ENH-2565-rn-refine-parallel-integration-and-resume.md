---
id: ENH-2565
type: ENH
priority: P3
status: open
discovered_date: 2026-07-09
discovered_by: manual
---

# ENH-2565: rn-refine — parallelize bottom-up integration and support resume from interrupted integration

## Summary

A `rn-refine` run against a 24-node, 3-deep tree timed out (4h wall-clock cap)
during the final root-node integration step. All 23 non-root nodes had already
produced a `final.md`; the timeout hit while `synth_pop` was serially
integrating internal nodes bottom-up, one node at a time. The refinement work
was fully intact but unreachable without hand-executing the remaining
integration steps. See `rn-refine-timeout-finalize-2026-07-09.md` (root of
repo, from `/ll:debug-loop-run rn-refine`) for the full incident writeup.

Immediate mitigations (timeout bump to 21600s, a `RECOVERY_NEEDED` marker when
`assemble` falls back to an un-integrated root, and per-node `final.md`
snapshots to `.loops/diagnostics/`) have already landed in `rn-refine.yaml`.
This issue tracks the two structural fixes that need real design work.

## Current Behavior

`synth_pop`/`integrate_node` (`rn-refine.yaml` ~line 264-315) dequeue and
integrate exactly one internal node per cycle, serially, even when multiple
internal nodes at the same depth have no dependency on each other. There is
also no resume path: any interruption after refinement completes but before
integration finishes forces a full re-run from `init`.

## Expected Behavior

Internal nodes whose children are all already integrated should integrate
concurrently. A run interrupted mid-integration should be resumable straight
into `synth_pop` without redoing the (potentially hours-long) refinement
phase.

## Impact

On a 24-node, 3-deep tree, serial integration (n10→n12→n1→n3, ~1,222s
cumulative) combined with a lack of resume turned a single dropped timeout
into a total loss of the integration phase's progress — the operator had to
re-run the entire loop, discarding a completed refinement tree, just to get
the last bottom-up rollup step. Any `rn-refine` run whose integration phase
alone approaches the timeout has the same failure mode.

## Scope Boundaries

In scope: `rn-refine.yaml`'s `synth_pop`/`integrate_node` states and queue
bookkeeping. Out of scope: changes to the per-node refinement phase
(`oracles/plan-node-refine`), to `ll-parallel` (issue-worktree parallelism,
not sub-loop parallelism), or to other loops.

## Problem

`scripts/little_loops/loops/rn-refine.yaml`'s `synth_pop` → `integrate_node`
flow dequeues and integrates exactly one internal node at a time
(`synth_pop`/`integrate_node` states, ~line 264-315). Internal nodes at the
same depth have disjoint children by construction, so they're independent and
safe to integrate concurrently — but the current FSM has no concurrency
primitive to express that (`ll-parallel` is the repo's only parallel
substrate today, and it's issue-worktree-shaped, not sub-loop-shaped).

Separately, there is no way to resume a run that died mid-integration. A
timeout (or any interruption) after refinement completes but before
integration finishes forces a full re-run from `init`, discarding a queue
whose refinement phase can take hours.

## Proposed Direction

1. **Parallel integration**: fan out `integrate_node` across all
   currently-poppable internal nodes (those whose children are all already
   integrated) instead of one per `synth_pop` cycle — either a worker-pool
   dispatch over `synth_queue.txt`, or multiple sub-loop workers coordinating
   through the same queue file with locking. Depth-first ordering must still
   guarantee a child is integrated before its parent is dequeued.
2. **Resume from interrupted integration**: detect (or accept a `--resume`
   flag) that `nodes/*/final.md` already exist for a completed refinement
   phase, rebuild `synth_queue.txt` from whichever internal nodes still lack a
   `final.md`, and jump straight to `synth_pop` — skipping `dequeue_next`/
   `refine_node` entirely.

Both should go through `ll:loop-specialist` for FSM design (this is a
meta-loop change to `rn-refine.yaml`) rather than being hand-patched, per the
project's meta-loop authoring rules (diagnosis-first scaffolding, non-LLM
evaluator, per-run artifact isolation).

## Acceptance Criteria

- [ ] `ll-loop validate rn-refine` passes with the new states/routing.
- [ ] A synthetic tree with ≥2 same-depth internal nodes integrates them
      concurrently (verified via timing or explicit concurrent-execution
      markers, not just an LLM self-report).
- [ ] A run resumed after an integration-phase interruption reuses existing
      `nodes/*/final.md` and does not re-run refinement for already-refined
      nodes.

## Status

**Open** | Created: 2026-07-09 | Priority: P3
