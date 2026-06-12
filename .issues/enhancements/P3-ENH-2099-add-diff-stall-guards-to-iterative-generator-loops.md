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

## Motivation

This enhancement would:
- Eliminate wasted iteration budget: generator loops currently consume up to 20–30 iterations producing identical output once the model plateaus
- Wire an existing capability: the `diff_stall` evaluator already exists in `scripts/little_loops/fsm/evaluators.py` and the `diff_stall_gate` fragment in `loops/lib/common.yaml` — this issue adds the missing wiring to 7 generator loops
- The 2026-06-12 audit found only one `convergence` use corpus-wide outside fragments, confirming the gap is systematic across the family

## Expected Behavior

Each generator loop's refine cycle includes a `diff_stall` guard (e.g. `max_stall: 3`, scoped to the artifact path) routing to a graceful terminal (accept best-so-far) instead of continuing to burn iterations.

## Success Metrics

- Generator loops detect plateau and exit the refine cycle within `max_stall` (≤ 3) consecutive no-change iterations
- Token waste on plateaued artifacts drops to `max_stall` iterations or fewer (down from up to `max_iterations`)
- `ll-loop validate` clean for all 7 generator loops after changes

## Scope Boundaries

- **In scope**: `svg-image-generator`, `p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`, `canvas-sketch-generator`, `html-website-generator`, `vega-viz` refine cycles; `loops/oracles/generator-evaluator.yaml` if wrappers delegate their cycle there
- **Out of scope**: Non-generator loops; other oracle consumers outside the generator family

## Implementation Steps

- Several of these loops are thin wrappers over `oracles/generator-evaluator.yaml` — adding the guard to the oracle once may cover most wrappers (same leverage as ENH-1957's snapshot state). Verify which wrappers delegate vs. own their cycle.
- `diff_stall` fields: `scope` (paths to limit), `max_stall` (consecutive no-change threshold). See `scripts/little_loops/fsm/evaluators.py` and `lib/common.yaml`'s `diff_stall_gate` fragment.
- Route stall to the loop's existing done/accept state, not failed — a plateaued artifact is a result, not an error.

## Acceptance Criteria

- [ ] Refine cycles in the family guard against no-progress iterations (directly or via the shared oracle)
- [ ] `ll-loop validate` clean for all touched loops
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes

## Integration Map

### Files to Modify
- `loops/svg-image-generator.yaml`
- `loops/p5js-sketch-generator.yaml`
- `loops/pixi-generative-art.yaml`
- `loops/pixi-data-viz.yaml`
- `loops/canvas-sketch-generator.yaml`
- `loops/html-website-generator.yaml`
- `loops/vega-viz.yaml`
- `loops/oracles/generator-evaluator.yaml` (if wrappers delegate cycle there — verify first)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/evaluators.py` — `diff_stall` evaluator implementation
- `loops/lib/common.yaml` — `diff_stall_gate` fragment (canonical pattern to follow)

### Similar Patterns
- `loops/lib/common.yaml` `diff_stall_gate` fragment — reference implementation for `diff_stall` wiring

### Tests
- `scripts/tests/test_builtin_loops.py` — must pass after changes

### Documentation
- N/A

### Configuration
- N/A


## Session Log
- `/ll:format-issue` - 2026-06-12T20:24:10 - `a1ec72f5-b2fb-4515-a490-94794292cae6.jsonl`
