---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# BUG-531: `evaluate_convergence` Unconditionally Returns "progress" on First Iteration

## Summary

When `previous is None` (first iteration), `evaluate_convergence` returns `"progress"` without inspecting the current value. The `previous` value is `None` because interpolating `${prev.output}` raises `InterpolationError` on the first iteration (no previous result exists), which is caught in the caller and sets `previous = None`. The evaluator cannot distinguish "genuinely first iteration" from "interpolation failed for another reason", and always routes to the `"apply"` (fix) state — even if the current value is already at the target.

## Location

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Line(s)**: 350–361 (at scan commit: 47c81c8)
- **Anchor**: `in function evaluate_convergence()`, first-iteration branch
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/evaluators.py#L350-L361)
- **Code**:
```python
if previous is None:
    return EvaluationResult(
        verdict="progress",       # always "progress" — never checks current vs target
        details={"current": current, "previous": None, "target": target, "delta": None},
    )
```

And in the caller at `evaluators.py:557`:
```python
except (InterpolationError, ValueError):
    previous = None    # masks root cause
```

## Current Behavior

On iteration 1, `${prev.output}` raises `InterpolationError` → `previous = None` → `evaluate_convergence` returns `"progress"` → loop applies a fix action unconditionally, even if the current metric is already at the target.

## Expected Behavior

On the first iteration, `evaluate_convergence` should check whether `current` is already within tolerance of `target`. If so, return `"converged"` (no fix needed). If not, return `"progress"` (apply fix). The first-iteration path should behave identically to subsequent iterations, just without a delta direction check.

## Motivation

A convergence loop that checks "is metric X at target Y?" will apply an unnecessary fix on iteration 1 even when X == Y. This wastes an API call or shell action and can cause incorrect state transitions.

## Steps to Reproduce

1. Create a `convergence` paradigm loop where the initial system state already matches the target
2. Run it: `ll-loop run already-converged-loop`
3. Observe: loop enters `apply` state on iteration 1 and applies a fix to an already-correct system

## Actual Behavior

Loop applies a fix unconditionally on iteration 1.

## Root Cause

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Anchor**: `in function evaluate_convergence()` and the `except (InterpolationError, ValueError)` block that sets `previous = None`
- **Cause**: Two separate issues: (1) first-iteration `None` check skips `current vs target` comparison; (2) the caller masks `InterpolationError` as `None`, preventing `evaluate_convergence` from knowing the true cause

## Proposed Solution

In the `previous is None` branch, still compare `current` to `target`:

```python
if previous is None:
    # First iteration: check convergence but skip delta direction
    within_tolerance = abs(current - target) <= (tolerance or 0)
    verdict = "converged" if within_tolerance else "progress"
    return EvaluationResult(
        verdict=verdict,
        details={"current": current, "previous": None, "target": target, "delta": None},
    )
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_convergence()` first-iteration branch

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — calls `evaluate_convergence` via `_evaluate()`
- `scripts/little_loops/fsm/compilers.py` — `compile_convergence` sets up routing from `"converged"` / `"progress"`

### Similar Patterns
- Other evaluators' first-iteration handling for reference

### Tests
- `scripts/tests/test_ll_loop_execution.py` — add test: already-converged state on iteration 1 returns `"converged"`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Update `evaluate_convergence` first-iteration branch to compare `current` vs `target` with tolerance
2. Add unit test in evaluator tests: `previous=None, current=target → "converged"`; `previous=None, current≠target → "progress"`

## Impact

- **Priority**: P4 — Correctness issue but limited to convergence paradigm; workaround is `max_iterations=1` on initial pass
- **Effort**: Small — 3-line change in one function
- **Risk**: Low — Behavioral change only for convergence loops where current == target on iteration 1
- **Breaking Change**: No (changes behavior from "always apply fix" to "check first" — the correct behavior)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-loop`, `evaluators`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P4
