---
id: ENH-2251
priority: P3
type: ENH
status: done
discovered_date: 2026-06-20
discovered_by: review-loop
confidence_score: 95
outcome_confidence: 90
completed_at: 2026-06-20T22:55:00Z
---

# ENH-2251: Harden brainstorm loop resilience and handoff behavior

## Summary

Reviewed the `brainstorm` built-in loop via `/ll:review-loop` and applied three
resilience/correctness fixes: added missing `on_error` routes to four states and
switched `on_handoff` from the implicit `pause` default to `spawn` to match the
codebase convention for autonomous loops.

## Motivation

`brainstorm` is a well-architected double-diamond ideation loop (composite quality
score 27/30 pre-fix), but its one weak dimension was Resilience. Several states
lacked `on_error` routing, so an LLM or evaluator error would halt the FSM with no
recovery path. Behavioral simulation (`ll-loop simulate brainstorm`) confirmed this:
the run terminated by `error` at `saturation_gate` because its `output_numeric`
evaluator errored and there was no `on_error` route to fall through.

Separately, `brainstorm` set no `on_handoff` and therefore defaulted to `pause`,
making it the outlier among built-in loops — 64 of 65 loops that set `on_handoff`
use `spawn`, including every sibling planning-category loop (`rn-refine`,
`rn-implement`, `rn-decompose`, `rn-remediate`). Because `brainstorm` has no
human-in-the-loop states (every state is shell or an agent-executed prompt), a
manual resume contributes nothing on a context handoff — `spawn` (auto-continue in
a detached session) is the correct behavior.

## Changes Applied

File: `scripts/little_loops/loops/brainstorm.yaml`

1. **`on_handoff: spawn`** added at the top level — autonomous loop auto-continues on
   a context handoff instead of pausing for manual resume.
2. **`saturation_gate` → `on_error: cluster`** — an evaluator error now stops
   divergence and proceeds to convergence instead of halting the loop (the gap that
   surfaced in simulation).
3. **`frame`, `diverge`, `converge` → `on_error: failed`** — prompt states that
   previously had only `next:` now route LLM errors to the `failed` terminal,
   consistent with the existing policy on `cluster` and `rank`.

## Deliberately Skipped

Defensive `on_error` routes on `pop_lens`, `route_sink`, and `sink_file` were
considered but skipped — these already degrade gracefully via their `on_no` /
`route._` catch-alls, so explicit error routes would add noise without changing
behavior.

## Verification

- `ll-loop validate brainstorm` → valid (exit 0).
- `ll-loop show brainstorm` → confirms `handoff: spawn`.
- Post-fix re-check: no new findings (no RT-1 regressions); all edits are pure
  additions targeting existing states (`cluster`, `failed`) plus one top-level field.
- Quality scorecard: composite **27 → 28/30** (Resilience 3 → 4).

## Artifacts

- Review record: `.loops/reviews/brainstorm-20260620-175000.md`

## Follow-up (not in scope)

The `/ll:review-loop` QC-6 check only flags "set `on_handoff` explicitly" — it does
not recommend `spawn` specifically, so it cannot catch a pause/spawn mismatch like
this one. Worth teaching QC-6 to recommend `spawn` unless the loop has
human-in-the-loop states.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-20T22:55:27 - `a2318783-4747-4466-abaf-2845dd563a2c.jsonl`
