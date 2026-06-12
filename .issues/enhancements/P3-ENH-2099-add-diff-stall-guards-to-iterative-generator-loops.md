---
id: ENH-2099
title: Add diff_stall guards to iterative generator loops to halt no-progress refinement
type: ENH
priority: P3
status: done
captured_at: '2026-06-12T14:10:00Z'
completed_at: '2026-06-12T22:00:01Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
parent: EPIC-1811
confidence_score: 92
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 18
---

# ENH-2099: Add diff_stall guards to iterative generator loops

## Summary

The iterative generator family (`svg-image-generator`, `p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`, `canvas-sketch-generator`, `html-website-generator`, `vega-viz`) runs evaluate→refine cycles bounded only by `max_iterations` (20–30). When refinement stops changing the artifact (model plateaus, prompt saturated), the loop burns the remaining iteration budget producing identical output. The `diff_stall` evaluator (compare git diff across iterations; fail after `max_stall` consecutive no-change iterations) exists but is unused in this family — the 2026-06-12 audit found only one `convergence` use corpus-wide outside fragments.

## Motivation

This enhancement would:
- Eliminate wasted iteration budget: generator loops currently consume up to 20–30 iterations producing identical output once the model plateaus
- Wire an existing capability: the `diff_stall` evaluator already exists in `scripts/little_loops/fsm/evaluators.py` and the `diff_stall_gate` fragment in `scripts/little_loops/loops/lib/common.yaml` — this issue adds the missing wiring to 7 generator loops
- The 2026-06-12 audit found only one `convergence` use corpus-wide outside fragments, confirming the gap is systematic across the family

## Current Behavior

Generator loops in the family (`svg-image-generator`, `p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`, `canvas-sketch-generator`, `html-website-generator`, `vega-viz`) run evaluate→refine cycles bounded only by `max_iterations` (20–30). When the model plateaus and refinement produces no change to the artifact, the loop continues consuming the full remaining iteration budget — generating identical output until `max_iterations` is exhausted. The `diff_stall` evaluator exists in `scripts/little_loops/fsm/evaluators.py` and the `diff_stall_gate` fragment in `scripts/little_loops/loops/lib/common.yaml` but is unused in this family.

## Expected Behavior

Each generator loop's refine cycle includes a `diff_stall` guard (e.g. `max_stall: 3`, scoped to the artifact path) routing to a graceful terminal (accept best-so-far) instead of continuing to burn iterations.

## Success Metrics

- Generator loops detect plateau and exit the refine cycle within `max_stall` (≤ 3) consecutive no-change iterations
- Token waste on plateaued artifacts drops to `max_stall` iterations or fewer (down from up to `max_iterations`)
- `ll-loop validate` clean for all 7 generator loops after changes

## Scope Boundaries

- **In scope**: `svg-image-generator`, `p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`, `canvas-sketch-generator`, `html-website-generator`, `vega-viz` refine cycles; `scripts/little_loops/loops/oracles/generator-evaluator.yaml` if wrappers delegate their cycle there
- **Out of scope**: Non-generator loops; other oracle consumers outside the generator family

## Implementation Steps

- Several of these loops are thin wrappers over `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — adding the guard to the oracle once may cover most wrappers (same leverage as ENH-1957's snapshot state). Verify which wrappers delegate vs. own their cycle.
- `diff_stall` fields: `scope` (paths to limit), `max_stall` (consecutive no-change threshold). See `scripts/little_loops/fsm/evaluators.py` and `scripts/little_loops/loops/lib/common.yaml`'s `diff_stall_gate` fragment.
- Route stall to the loop's existing done/accept state, not failed — a plateaued artifact is a result, not an error.

## Acceptance Criteria

- [ ] Refine cycles in the family guard against no-progress iterations (directly or via the shared oracle)
- [ ] `ll-loop validate` clean for all touched loops
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes

## Impact

- **Priority**: P3 — Efficiency improvement; loops still function correctly but waste tokens on plateaued artifacts
- **Effort**: Small — Wiring an existing evaluator to 7 loop files (or 1 shared oracle)
- **Risk**: Low — Additive change; existing behavior preserved when stall guard is not triggered
- **Breaking Change**: No

## Labels

`loop-quality`, `efficiency`, `evaluators`, `generator-loops`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/svg-image-generator.yaml`
- `scripts/little_loops/loops/p5js-sketch-generator.yaml`
- `scripts/little_loops/loops/pixi-generative-art.yaml`
- `scripts/little_loops/loops/pixi-data-viz.yaml`
- `scripts/little_loops/loops/canvas-sketch-generator.yaml`
- `scripts/little_loops/loops/html-website-generator.yaml`
- `scripts/little_loops/loops/vega-viz.yaml`
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` (if wrappers delegate cycle there — verify first)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/evaluators.py` — `diff_stall` evaluator implementation
- `scripts/little_loops/loops/lib/common.yaml` — `diff_stall_gate` fragment (canonical pattern to follow)

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml` `diff_stall_gate` fragment — reference implementation for `diff_stall` wiring

### Tests
- `scripts/tests/test_builtin_loops.py` — must pass after changes

### Documentation
- N/A

### Configuration
- N/A


## Status

**Open** | Created: 2026-06-12 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-12T21:47:32 - `8a3a96e3-47db-43cc-af43-8757bfe51799.jsonl`
- `/ll:format-issue` - 2026-06-12T20:24:10 - `a1ec72f5-b2fb-4515-a490-94794292cae6.jsonl`
- `/ll:confidence-check` - 2026-06-12T20:45:00Z - `a75b6271-be48-44c0-98be-3e6c0b2e4371.jsonl`
