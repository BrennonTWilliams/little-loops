---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
---

# BUG-530: `--no-llm` Flag Sets `llm.enabled=False` But Executor Never Reads the Field

## Summary

The `ll-loop run --no-llm` flag sets `fsm.llm.enabled = False` on the loaded `FSMLoop` object, but neither `FSMExecutor` nor any evaluator ever reads `llm.enabled`. LLM evaluation calls in `evaluate_llm_structured` proceed unconditionally. The `--no-llm` flag silently has no effect.

## Location

- **File**: `scripts/little_loops/cli/loop/run.py`
- **Line(s)**: 84–85 (at scan commit: 47c81c8)
- **Anchor**: `in function cmd_run()`, `--no-llm` branch
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/cli/loop/run.py#L84-L85)
- **Code**:
```python
if args.no_llm:
    fsm.llm.enabled = False   # sets field...

# executor.py _evaluate() — never reads llm.enabled:
result = evaluate_llm_structured(
    action_result.output,
    model=self.fsm.llm.model,
    ...
)
```

## Current Behavior

Running `ll-loop run my-loop --no-llm` sets `fsm.llm.enabled = False` in memory but the FSM executor proceeds to call `evaluate_llm_structured` normally. LLM API calls are made, tokens are consumed, and latency is incurred — the same as if `--no-llm` was not passed.

## Expected Behavior

`--no-llm` prevents any LLM evaluation calls. Evaluators that use LLM should fall back to a default verdict (e.g., `"unknown"` or `"error"`) or raise a clear error when `llm.enabled = False`.

## Motivation

`--no-llm` is presumably intended for dry-run, testing, or cost-control scenarios. If it doesn't work, users who rely on it to avoid API costs or test without credentials will be silently making LLM calls. The flag's existence creates a false sense of safety.

## Steps to Reproduce

1. Create a loop using `evaluate: llm_structured`
2. Run: `ll-loop run my-loop --no-llm`
3. Observe: LLM API call is made (network traffic, API key required, tokens consumed)

## Actual Behavior

`evaluate_llm_structured` is called regardless of `llm.enabled`.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/run.py` (sets field) and `scripts/little_loops/fsm/executor.py` (ignores it)
- **Anchor**: `in method FSMExecutor._evaluate()`, `in function cmd_run()`
- **Cause**: `llm.enabled` was defined as a schema field but `_evaluate()` in `executor.py` was never updated to check it before dispatching to `evaluate_llm_structured`

## Proposed Solution

In `FSMExecutor._evaluate()`, check `self.fsm.llm.enabled` before calling LLM evaluation:

```python
# In FSMExecutor._evaluate():
if eval_config.type == "llm_structured":
    if not self.fsm.llm.enabled:
        return EvaluationResult(
            verdict="error",
            details={"error": "LLM evaluation disabled via --no-llm"},
        )
    return evaluate_llm_structured(...)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._evaluate()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py` — uses `FSMExecutor` internally; inherits fix
- `scripts/little_loops/cli/loop/run.py` — sets `llm.enabled`; no change needed

### Similar Patterns
- `scripts/little_loops/fsm/schema.py:308` — `LLMConfig.enabled` field definition

### Tests
- `scripts/tests/test_ll_loop_execution.py:746` (`TestLLMFlags` class) — add test: `llm.enabled=False` → `_evaluate()` returns error verdict without calling `evaluate_llm_structured`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `if not self.fsm.llm.enabled: return error verdict` guard in `FSMExecutor._evaluate()` for `llm_structured` type
2. Add test verifying that `--no-llm` prevents LLM evaluator from being called
3. Optionally: surface a clear warning to the user when `--no-llm` skips an LLM evaluation

## Impact

- **Priority**: P3 — Silent misbehavior; flag that does nothing is a UX and cost-control bug
- **Effort**: Small — Guard clause addition in `_evaluate()`
- **Risk**: Low — Only affects `llm_structured` evaluator path; no other evaluators impacted
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | Evaluator types — LLM evaluator (line 545), CLI run flags (line 1381) |
| `docs/guides/LOOPS_GUIDE.md` | LLM evaluator documentation (line 295) |

## Labels

`bug`, `ll-loop`, `llm`, `scan-codebase`

## Resolution

**Status**: Fixed
**Date**: 2026-03-04
**Commit**: (see git log)

Added `llm.enabled` guard in `FSMExecutor._evaluate()` for both evaluation paths:
1. **Default path** (prompt/slash command with no explicit evaluate config): checks `self.fsm.llm.enabled` before calling `evaluate_llm_structured`; returns `verdict="error"` with `"LLM evaluation disabled via --no-llm"` if disabled
2. **Explicit path** (`state.evaluate.type == "llm_structured"`): same guard before dispatching to `evaluate_llm_structured`

Added two unit tests to `TestLLMFlags`:
- `test_no_llm_prevents_explicit_llm_structured_evaluation` — verifies explicit `llm_structured` config with `llm.enabled=False` returns error without calling `evaluate_llm_structured`
- `test_no_llm_prevents_default_prompt_evaluation` — verifies default prompt evaluation with `llm.enabled=False` returns error without calling `evaluate_llm_structured`

All 42 tests pass.

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; updated test ref to `test_ll_loop_execution.py:746` (TestLLMFlags)
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:ready-issue` — 2026-03-04T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/483ea015-0ad0-4661-a36d-84e6187e35e9.jsonl`
- `/ll:manage-issue` — 2026-03-04T00:00:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/` — Fixed: added llm.enabled guard in FSMExecutor._evaluate(); added 2 tests

## Blocks

- ENH-563
- ENH-542

---

**Completed** | Created: 2026-03-03 | Priority: P3
