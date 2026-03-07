---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# BUG-622: `output_numeric` silently defaults missing `target` to `0.0` when validation bypassed

## Summary

The `output_numeric` branch in `evaluate()` treats `config.target is None` as valid and substitutes `0.0`. While `validate_fsm()` lists `target` as a required field for `output_numeric`, paradigm compilers like `compile_paradigm()` build an `FSMLoop` directly without calling `validate_fsm()`. In that path, a missing `target` silently compares numeric output against 0 — producing wrong verdicts with no error or warning.

## Location

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Line(s)**: 559–565 (at scan commit: 12a6af0)
- **Anchor**: `in function evaluate(), eval_type == "output_numeric" branch`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/evaluators.py#L559-L565)
- **Code**:
```python
numeric_target = float(config.target) if config.target is not None else 0.0
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

Replace the silent default with an explicit error:

```python
if config.target is None:
    raise EvaluationError("output_numeric evaluator requires 'target' to be set")
numeric_target = float(config.target)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate()` function, `output_numeric` branch

### Tests
- `scripts/tests/test_fsm_evaluators.py` — add test verifying error is raised when `target=None`

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

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P4
