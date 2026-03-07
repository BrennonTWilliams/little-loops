---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 93
outcome_confidence: 95
---

# BUG-622: `output_numeric` silently defaults missing `target` to `0.0` when validation bypassed

## Summary

The `output_numeric` branch in `evaluate()` treats `config.target is None` as valid and substitutes `0.0`. While `validate_fsm()` lists `target` as a required field for `output_numeric`, paradigm compilers like `compile_paradigm()` build an `FSMLoop` directly without calling `validate_fsm()`. In that path, a missing `target` silently compares numeric output against 0 — producing wrong verdicts with no error or warning.

## Location

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Line(s)**: 559–576 (at HEAD; None-default at line 560–561)
- **Anchor**: `in function evaluate(), eval_type == "output_numeric" branch`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/evaluators.py#L559-L565)
- **Code**:
```python
elif eval_type == "output_numeric":
    if config.target is None:
        numeric_target = 0.0          # <-- silent default; bug here
    elif isinstance(config.target, str):
        try:
            resolved = interpolate(config.target, context) if context else config.target
            numeric_target = float(resolved)
        except (InterpolationError, ValueError) as e:
            raise ValueError(
                f"output_numeric target must be numeric, got: {config.target!r}"
            ) from e
    else:
        numeric_target = float(config.target)
```

## Current Behavior

When `config.target` is `None` and the loop was built via a paradigm compiler (bypassing `validate_fsm`), the evaluator silently uses `0.0` as the comparison target. The loop runs, produces verdicts, and routes states — all compared against 0 rather than the intended value. No warning is emitted.

## Expected Behavior

When `target` is `None`, the evaluator should raise a clear `EvaluationError` rather than substituting a default that changes evaluation semantics silently.

## Steps to Reproduce

1. Use `compile_paradigm()` directly (not via YAML file load) to build an `FSMLoop` with an `output_numeric` evaluator that has no `target` field.
2. Run the resulting FSM.
3. Observe: evaluator runs with `target=0.0` silently.

## Root Cause

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Anchor**: `in function evaluate(), output_numeric branch`
- **Cause**: The `else 0.0` fallback was added for defensive coding but bypasses the validation layer that enforces `target` is required.

## Proposed Solution

Replace the silent default with an explicit error (`EvaluationError` does not exist in the codebase; use `ValueError` consistent with the existing error-raise pattern at line 567):

```python
elif eval_type == "output_numeric":
    if config.target is None:
        raise ValueError("output_numeric evaluator requires 'target' to be set")
    elif isinstance(config.target, str):
        ...
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate()` function, `output_numeric` branch (line ~561)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._evaluate()` calls `evaluate()` (dispatches to this branch)
- `scripts/little_loops/fsm/__init__.py` — exports `evaluate_output_numeric`; no change needed

### Similar Patterns
- `scripts/little_loops/fsm/evaluators.py` line ~613 — `convergence` evaluator has the identical `if config.target is not None else 0.0` fallback; consider fixing for consistency

### Tests
- `scripts/tests/test_fsm_evaluators.py` — add test verifying `EvaluationError` is raised when `target=None` in `evaluate()` dispatch (not just `evaluate_output_numeric` directly)

### Documentation
- N/A — no docs reference `output_numeric` target behavior

### Configuration
- N/A

## Implementation Steps

1. Replace `else 0.0` fallback with an `EvaluationError` raise in the `output_numeric` branch

## Impact

- **Priority**: P4 — Unlikely to affect users in practice (validation catches it at YAML load), but the silent default is a correctness hazard
- **Effort**: Small — One-line change
- **Risk**: Low — Turns a silent wrong behavior into a loud error; behavior only changes for configs that bypass validation
- **Breaking Change**: No (technically breaks the `target=None` fallback path, but that path is wrong behavior)

## Labels

`bug`, `fsm`, `evaluator`, `captured`

## Verification Notes

**Verdict**: NEEDS_UPDATE — Verified 2026-03-07

- Commit `4b0de89` restructured the `output_numeric` branch in `evaluators.py` (added a non-numeric string guard with interpolation), but the `config.target is None → 0.0` silent default **still persists** at `evaluators.py:555–576`. Core bug is still valid.
- Issue code snippet no longer matches current code structure (it shows a single ternary; current code is a multi-branch `if/elif/else`). The proposed fix (raise `EvaluationError` when `target is None`) remains correct and is the same change needed.
- No other changes to impact or scope required.

## Resolution

**Status**: COMPLETED — 2026-03-07

### Changes Made

- `scripts/little_loops/fsm/evaluators.py`: Replaced silent `0.0` default with `ValueError` in `output_numeric` branch (line ~561). Also fixed identical pattern in `convergence` branch (line ~623).
- `scripts/tests/test_fsm_evaluators.py`: Added `test_dispatch_output_numeric_none_target_raises` and `test_dispatch_convergence_none_target_raises` to cover the new error paths.

### Verification

- All 104 evaluator tests pass.

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8a0f657-a512-4e80-9946-68695952f105.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d11c154b-ec01-40ba-bc51-c1eb3dd6ae2f.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7f1264d4-d8b5-4093-9023-f666be376885.jsonl`
- `/ll:manage-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`

---

**Completed** | Created: 2026-03-07 | Priority: P4
