---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# ENH-536: `EvaluateConfig.source` Field Parsed and Serialized But Never Consumed During Evaluation

## Summary

`EvaluateConfig.source` is documented as "Override default source (current action output)", present in the Python dataclass, `to_dict()`/`from_dict()`, and the JSON schema. However, `evaluate()` in `evaluators.py` receives only the raw `output: str` string and never checks `config.source`. The field cannot redirect evaluation to a different captured variable — it silently has no effect.

## Location

- **File**: `scripts/little_loops/fsm/schema.py`
- **Line(s)**: 49, 72 (at scan commit: 47c81c8)
- **Anchor**: `in class EvaluateConfig`, `source` field
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/schema.py#L49)

And in `scripts/little_loops/fsm/evaluators.py` — `evaluate()` function does not reference `config.source`.

- **Code**:
```python
# schema.py:72
source: str | None = None
# "Override default source (current action output)"

# evaluators.py:502 — evaluate() signature:
def evaluate(config: EvaluateConfig, output: str, ...) -> EvaluationResult:
    # config.source never read; 'output' always used directly
```

## Current Behavior

Setting `evaluate: { type: exit_code, source: "${captured.previous_run.output}" }` in a loop YAML has no effect. The evaluator always uses the current state's action output, regardless of `source`.

## Expected Behavior

When `source` is set, the evaluator uses the resolved `source` value as its input instead of the current action output. This allows evaluating a captured variable from a previous state rather than the immediately preceding action's stdout.

## Motivation

The `source` override enables powerful patterns: evaluate the output of an action from 3 states ago, evaluate a stored file path's content, or re-evaluate a previous result with a different evaluator. Without it, loops must use complex action gymnastics to get the right value into `${prev.output}`.

## Proposed Solution

In `FSMExecutor._evaluate()` (where `evaluate()` is called), resolve `config.source` if set and use it as the evaluation input:

```python
# In FSMExecutor._evaluate():
if config.source:
    try:
        eval_input = interpolate(config.source, ctx)
    except InterpolationError:
        eval_input = output   # fallback to current output
else:
    eval_input = output

return evaluate(config, eval_input, ...)
```

This keeps evaluators themselves source-agnostic; only the executor resolves the source expression.

## Scope Boundaries

- Only changes which string is passed to evaluators; does not change evaluator logic
- `source` is optional; no-`source` behavior is identical to current
- Does not add new evaluator types

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._evaluate()`, resolve `config.source` before calling `evaluate()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py` — wraps `FSMExecutor`; inherits fix
- `scripts/little_loops/fsm/evaluators.py` — `evaluate()` signature unchanged; no changes needed
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig.source` field already exists; no changes

### Similar Patterns
- `interpolate()` usage in `_build_context()` and `_execute_state()` for reference

### Tests
- `scripts/tests/test_ll_loop_execution.py` — add: `evaluate.source = "${captured.prev.output}"` → evaluates captured value not current action output

### Documentation
- N/A — field already documented in schema

### Configuration
- N/A

## Implementation Steps

1. In `FSMExecutor._evaluate()`, check `config.source` and interpolate if set
2. Pass resolved input to `evaluate()` instead of raw `output`
3. Add test: source field redirects evaluation to a captured variable
4. Add test: invalid source expression falls back to `output`

## Impact

- **Priority**: P3 — Documented feature that doesn't work; blocks users from using `source` override pattern
- **Effort**: Small — ~10 lines in `_evaluate()`
- **Risk**: Low — Only affects evaluations where `source` is explicitly set (currently 0 — feature is broken)
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ll-loop`, `evaluators`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P3
