---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 98
outcome_confidence: 90
---

# BUG-620: `output_numeric` evaluator raises unguarded `ValueError` for string targets

## Summary

The `output_numeric` evaluator branch in `evaluate()` calls `float(config.target)` without catching `ValueError`. If `config.target` is a non-numeric string (such as an interpolation template like `"${context.threshold}"`), `float()` raises `ValueError`. The exception propagates out of `_evaluate()` into the executor's outer `except Exception` handler, which terminates the loop with `terminated_by="error"` — providing no diagnostic information about which evaluator field caused the failure.

## Location

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Line(s)**: 559–565 (at scan commit: 12a6af0)
- **Anchor**: `in function evaluate(), eval_type == "output_numeric" branch`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/evaluators.py#L559-L565)
- **Code**:
```python
elif eval_type == "output_numeric":
    # Target must be numeric
    numeric_target = float(config.target) if config.target is not None else 0.0
    return evaluate_output_numeric(
        output=output,
        operator=config.operator or "eq",
        target=numeric_target,
    )
```

Compare with the `convergence` evaluator at evaluators.py which explicitly handles string targets via `interpolate()` before conversion.

## Current Behavior

If `evaluate.target` is set to a string (e.g., an interpolation placeholder `"${context.threshold}"` meant to be resolved before evaluation), `float("${context.threshold}")` raises `ValueError` with no diagnostic message. The outer exception handler in `FSMExecutor._run_state()` catches it and terminates the loop with a generic error.

## Expected Behavior

The `output_numeric` evaluator should either:
1. Attempt interpolation of `config.target` if it is a string (matching the `convergence` evaluator's behavior), or
2. Raise a clear `EvaluationError` with a message like `"output_numeric target must be numeric, got: '${context.threshold}'"`.

## Motivation

Users who configure `output_numeric` evaluators with context-variable targets (e.g., `target: "${context.threshold}"`) — a natural expectation given that the `convergence` evaluator already supports interpolation — receive a completely opaque failure: the loop terminates with `terminated_by="error"` and a raw `ValueError` traceback. There is no indication which evaluator field is misconfigured or why. This discoverability gap slows debugging and undermines trust in the FSM executor's error reporting.

## Steps to Reproduce

1. Create a loop YAML with an `output_numeric` evaluator and set `target` to a string value.
2. Run the loop with `ll-loop run`.
3. Observe: loop terminates with `terminated_by="error"` and a raw `ValueError` traceback rather than a clear diagnostic.

## Root Cause

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Anchor**: `in function evaluate(), output_numeric branch`
- **Cause**: The `output_numeric` branch calls `float(config.target)` unconditionally without a `try/except ValueError` or interpolation step, unlike the `convergence` evaluator which calls `interpolate()` and handles conversion errors explicitly.

## Proposed Solution

```python
elif eval_type == "output_numeric":
    if config.target is None:
        numeric_target = 0.0
    elif isinstance(config.target, str):
        # Attempt interpolation for template strings
        resolved = interpolate(str(config.target), context) if context else config.target
        try:
            numeric_target = float(resolved)
        except ValueError:
            raise ValueError(
                f"output_numeric target must be numeric, got: {resolved!r}"
            )
    else:
        numeric_target = float(config.target)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate()` function, `output_numeric` branch

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — calls `evaluate()` in `_run_state()`; wraps exceptions in generic handler
- `scripts/little_loops/cli/loop/testing.py` — calls `evaluate()` for test-mode state evaluation
- `scripts/little_loops/fsm/__init__.py` — re-exports evaluators module

### Similar Patterns
- `scripts/little_loops/fsm/evaluators.py` — `convergence` branch already handles string targets with interpolation; use the same pattern

### Tests
- `scripts/tests/test_fsm_evaluators.py` — add test for `output_numeric` with string target (interpolation template and non-numeric string)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `try/except ValueError` guard (and optional interpolation step) in the `output_numeric` branch of `evaluate()`
2. Add unit tests covering: numeric string, non-numeric string, interpolation template

## Impact

- **Priority**: P3 — Affects users who attempt to use context variable interpolation in `output_numeric` targets; produces confusing errors
- **Effort**: Small — Small change to `evaluate()` following the existing `convergence` pattern
- **Risk**: Low — Change is local to the `output_numeric` branch; no interface changes
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `evaluator`, `captured`

## Verification Notes

**Verdict**: NEEDS_UPDATE — Bug confirmed valid; proposed solution corrected.

- **Bug confirmed**: `float(config.target)` at `evaluators.py:561` is unguarded — matches issue exactly.
- **Proposed solution fix 1**: `EvaluationError` does not exist in the codebase. Corrected to `ValueError` (consistent with existing `raise ValueError(f"Unknown evaluator type: {eval_type}")` pattern in the same file).
- **Proposed solution fix 2**: The proposed code used `ctx` but the actual parameter in `evaluate()` is `context`. Corrected.
- **Convergence reference confirmed**: `interpolate()` is already imported from `little_loops.fsm.interpolation` and used at lines 588, 606, 620 — the proposed pattern is valid.
- **Test file confirmed**: `scripts/tests/test_fsm_evaluators.py` exists.

## Resolution

**Status**: Fixed
**Resolved**: 2026-03-07
**Commit**: (see git log)

### Changes Made

- `scripts/little_loops/fsm/evaluators.py`: Updated `output_numeric` branch in `evaluate()` to attempt interpolation on string targets (matching `convergence` behavior), and raise a clear `ValueError` with diagnostic message if resolution or float conversion fails.
- `scripts/tests/test_fsm_evaluators.py`: Added 3 new tests in `TestEvaluateDispatcher`: numeric string target, interpolated template target, and non-numeric string target raising `ValueError`.

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dfbe60d2-18e9-4a8b-a421-41de3f2906c2.jsonl`
- `/ll:manage-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

## Status

**Completed** | Created: 2026-03-07 | Priority: P3
