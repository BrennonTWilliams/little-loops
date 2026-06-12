---
id: ENH-2099
title: Add diff_stall guards to iterative generator loops to halt no-progress refinement
type: ENH
priority: P3
status: open
captured_at: '2026-06-12T14:10:00Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
parent: EPIC-1811
---

# ENH-2099: Add diff_stall guards to iterative generator loops

## Summary

The iterative generator family (`svg-image-generator`, `p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`, `canvas-sketch-generator`, `html-website-generator`, `vega-viz`) runs evaluate→refine cycles bounded only by `max_iterations` (20–30). When refinement stops changing the artifact (model plateaus, prompt saturated), the loop burns the remaining iteration budget producing identical output. The `diff_stall` evaluator (compare git diff across iterations; fail after `max_stall` consecutive no-change iterations) exists but is unused in this family — the 2026-06-12 audit found only one `convergence` use corpus-wide outside fragments.

## Expected Behavior

Each generator loop's refine cycle includes a `diff_stall` guard (e.g. `max_stall: 3`, scoped to the artifact path) routing to a graceful terminal (accept best-so-far) instead of continuing to burn iterations.

## Implementation notes

- Several of these loops are thin wrappers over `oracles/generator-evaluator.yaml` — adding the guard to the oracle once may cover most wrappers (same leverage as ENH-1957's snapshot state). Verify which wrappers delegate vs. own their cycle.
- `diff_stall` fields: `scope` (paths to limit), `max_stall` (consecutive no-change threshold). See `scripts/little_loops/fsm/evaluators.py` and `lib/common.yaml`'s `diff_stall_gate` fragment.
- Route stall to the loop's existing done/accept state, not failed — a plateaued artifact is a result, not an error.

## Acceptance Criteria

- [ ] Refine cycles in the family guard against no-progress iterations (directly or via the shared oracle)
- [ ] `ll-loop validate` clean for all touched loops
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes
