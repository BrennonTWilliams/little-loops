---
id: BUG-2066
title: vega-viz terminates on first ALL_PASS while judge documents blocking defects (phantom convergence)
type: BUG
priority: P2
status: done
captured_at: '2026-06-09T22:30:00Z'
discovered_date: 2026-06-09
discovered_by: user-session
labels:
- loops
- fsm
- harness
- visualization
- vega
- phantom-convergence
relates_to:
- ENH-2010
- ENH-2045
size: Small
completed_at: '2026-06-09T22:30:00Z'
---

# BUG-2066: vega-viz terminates on first ALL_PASS while judge documents blocking defects (phantom convergence)

## Summary

The built-in `vega-viz` loop (`scripts/little_loops/loops/vega-viz.yaml`) shipped
a visualization with five concrete, evaluator-documented visual defects because
its scoring gate let the LLM judge self-report `VERDICT: ALL_PASS` while
simultaneously listing actionable defects in its own "Issues to Address"
section. The loop exited to `done` on the **first** scoring pass and never
iterated. This is the classic phantom-convergence pattern: the judge narrates
failure and stamps success in the same breath, and the per-criterion numeric
thresholds mask the contradiction.

Surfaced by a full audit of run `2026-06-10T002506` (a force-directed
microservice call-graph), captured in `audit-vega-viz-2026-06-10.md`.

## Root Cause

The `score` state's prompt computed `VERDICT` purely from per-criterion numeric
thresholds (`faithfulness`/`honesty >= hard_gate`, `effectiveness`/`craft >=
pass_threshold`). Nothing linked the judge's "Issues to Address" list to the
verdict, so a critique could read `ALL_PASS` with five defects (overlapping
labels, empty legend entries, a formula/visual-radius mismatch, a near-invisible
reference mark, an off-center layout) and remain internally consistent by its
own rubric. The deterministic `record` state then routed `EVAL_PASS → done` on
the first pass.

Per the repo's meta-loop rule MR-1, an LLM self-grade on harness output must be
paired with a non-LLM evaluator; here the deterministic `record` router trusted
the judge's self-consistency instead of independently enforcing the contract.

## The Fix

Two coupled changes to `scripts/little_loops/loops/vega-viz.yaml`, severity-aware
to avoid the over-blunt "any issue forces ITERATE" failure mode (a skeptical
reviewer always finds *something*, which would grind the loop to
`max_iterations: 20` over nitpicks):

1. **`score` prompt** — every "Issues to Address" item must be tagged with its
   severity as the first token: `[BLOCKING]` (a defect that makes the chart
   wrong, misleading, or visibly broken) or `[MINOR]` (an optional refinement).
   The VERDICT rule now requires `ALL_PASS` to satisfy **both** the four numeric
   thresholds **and** zero `[BLOCKING]` items. `[MINOR]` items do not block.

2. **`record` shell (deterministic gate)** — counts `[BLOCKING]` lines in
   `critique.md` and overrides a self-reported `VERDICT: ALL_PASS` back to
   `ITERATE` when any are present, emitting a `BLOCKING_OVERRIDE:` log line. The
   non-LLM router now enforces the convergence contract rather than trusting the
   judge (MR-1 compliance).

This is independent of and narrower than the deferred `ENH-2045` (which ports
four `rlhf-animated-svg` robustness patterns into vega-viz); none of ENH-2045's
items address this empty-/blocking-issues gate, which is the actual root cause
of this run's phantom convergence.

## Files Changed

- `scripts/little_loops/loops/vega-viz.yaml`
  - `score` state prompt: `[BLOCKING]`/`[MINOR]` severity tagging + the
    "zero blocking items" requirement on `ALL_PASS`.
  - `record` state shell: `[BLOCKING]` count + `BLOCKING_OVERRIDE` of a claimed
    pass (with a `grep -c` empty-output guard so a missing/zero-match critique
    can't break the numeric test).
- `scripts/tests/test_builtin_loops.py`
  - New `TestVegaVizScoringGate` class (9 tests): 5 structural assertions on the
    YAML wiring + 4 behavioral tests that execute the real `record` shell action
    against representative critiques.

## Verification

- `ll-loop validate vega-viz` → valid, no new MR violations.
- `python -m pytest scripts/tests/test_builtin_loops.py -k TestVegaVizScoringGate`
  → 9 passed. Behavioral cases assert on the **last** emitted token (what
  `record`'s `output_contains: EVAL_PASS` evaluator routes on), so a regression
  where the override prints but `EVAL_PASS` still leaks through is caught.
  - `ALL_PASS` + `[BLOCKING]` → `BLOCKING_OVERRIDE`, final token `ITERATE`
  - `ALL_PASS` + `[MINOR]`-only → `EVAL_PASS`
  - `ALL_PASS` + clean → `EVAL_PASS`
  - genuine `ITERATE` → `ITERATE` with no spurious override message

## Acceptance Criteria

- [x] `score` prompt requires `[BLOCKING]`/`[MINOR]` severity tags on every
      Issues-to-Address item
- [x] `score` prompt ties `ALL_PASS` to zero `[BLOCKING]` items; `[MINOR]` items
      do not block
- [x] `record` deterministically overrides a claimed `ALL_PASS` to `ITERATE`
      when any `[BLOCKING]` item is present
- [x] `record.on_yes → done` / `record.on_no → generate` routing unchanged
- [x] `ll-loop validate vega-viz` passes with no new MR violations
- [x] `TestVegaVizScoringGate` exists and passes

## Out of Scope / Follow-ups

- The audit's other proposals (P3 pass-streak, P4 evaluator model pin, P5
  programmatic visual-defect detection in `capture`) were intentionally not
  taken: P5 is fragile bounding-box heuristics the audit itself rates
  low-confidence, P4 is a host/runtime concern (the YAML pins no models), and the
  iteration-robustness patterns partially overlap the deferred `ENH-2045`.
- Empirical confirmation: re-running the original force-directed-graph input
  should now produce 2+ scoring iterations before termination.

## Related Documentation

| Document | Relevance |
|---|---|
| `audit-vega-viz-2026-06-10.md` | Source audit; full defect list and proposal ranking |
| `scripts/little_loops/loops/vega-viz.yaml` | Fixed loop |
| `.claude/CLAUDE.md` § Loop Authoring (MR-1) | Non-LLM-evaluator pairing rule the fix satisfies |
| `.issues/enhancements/P3-ENH-2045-port-rlhf-harness-patterns-to-vega-viz.md` | Adjacent (deferred) robustness work; does not cover this gate |

## Session Log
- `hook:posttooluse-status-done` - 2026-06-10T03:39:36 - `8013c50d-ebdc-4af3-a57e-9b84d0db1f66.jsonl`
- user-session - 2026-06-09 - reviewed `audit-vega-viz-2026-06-10.md`, implemented the blocking-issue convergence gate in `vega-viz.yaml`, and added `TestVegaVizScoringGate`
