---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 86
---

# ENH-627: `is_prompt`/`is_slash_command` re-derived independently in `_run_action` and `_evaluate` with subtle divergence

## Summary

`FSMExecutor._run_action()` and `_evaluate()` each independently compute whether the current state's action is a slash command or prompt. The two computations use slightly different inputs: `_run_action` uses the post-interpolation `action` string, while `_evaluate` uses the raw `state.action` template. If the template and the interpolated result differ in their leading character, the two checks disagree about whether the action is a prompt. Additionally, computing the same thing twice adds coupling.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 557–560 and 627–630 (at scan commit: 12a6af0; updated to HEAD)
- **Anchor**: `in class FSMExecutor, methods _run_action() and _evaluate()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/executor.py#L541-L544)
- **Code**:
```python
# In _run_action (lines 541-544) — uses interpolated action string:
if state.action_type is not None:
    is_slash_command = state.action_type in ("prompt", "slash_command")
else:
    is_slash_command = action.startswith("/")

# In _evaluate (lines 611-614) — uses raw state.action template:
if state.action_type is not None:
    is_prompt = state.action_type in ("prompt", "slash_command")
else:
    is_prompt = state.action is not None and state.action.startswith("/")
```

## Current Behavior

The two checks agree for all current use cases (since action templates typically start with `/` if they're slash commands). However the subtle divergence — interpolated string vs raw template — is a latent bug waiting to be triggered if a context variable could change the leading character of an action.

## Expected Behavior

The `is_prompt` determination should be computed once (ideally from `state.action_type` or the raw template before interpolation) and passed to both `_run_action` and `_evaluate`, or extracted into a helper like `_is_prompt_action(state)`.

## Motivation

Removing duplication here eliminates the latent inconsistency and reduces the cognitive load of understanding the execution path. A helper function is easy to test in isolation.

## Success Metrics

- Duplicate `is_prompt`/`is_slash_command` inline blocks: 2 → 0
- All existing `FSMExecutor` tests pass with no behavior change (`TestActionType` + `test_ll_loop_execution.py` direct `_evaluate` calls)
- `_run_action` heuristic fallback uses `state.action` (raw template) instead of post-interpolation string, matching `_evaluate`

## Proposed Solution

```python
def _is_prompt_action(self, state: StateConfig) -> bool:
    """Return True if state's action is a slash-command/prompt type."""
    if state.action_type is not None:
        return state.action_type in ("prompt", "slash_command")
    return state.action is not None and state.action.startswith("/")

# Both _run_action and _evaluate call self._is_prompt_action(state)
```

## API/Interface

New private method on `FSMExecutor`:

```python
def _is_prompt_action(self, state: StateConfig) -> bool:
    """Return True if state's action is a slash-command/prompt type."""
```

No public API changes.

## Scope Boundaries

- Only refactors the detection; no behavior change for current inputs
- `_run_action` should switch to using the raw template (matching `_evaluate`) for consistency

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — extract `_is_prompt_action()` helper; update `_run_action()` and `_evaluate()`

### Reference Files (read-only)
- `scripts/little_loops/fsm/schema.py:192` — `StateConfig.action_type: Literal["prompt", "slash_command", "shell"] | None = None`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:506` — `_execute_state()` calls `_run_action()` (unconditional-transition branch; skips `_evaluate`)
- `scripts/little_loops/fsm/executor.py:517` — `_execute_state()` calls `_run_action()` (normal evaluation branch)
- `scripts/little_loops/fsm/executor.py:520` — `_execute_state()` calls `_evaluate()` with result from line 517
- `scripts/tests/test_ll_loop_execution.py:1138,1177,1225,1269,1310` — calls `executor._evaluate(state, action_result, ctx)` directly (5 call sites); these tests must continue to pass

### Tests
- `scripts/tests/test_fsm_executor.py` — existing `TestActionType` class covers the detection behavior end-to-end via `mock_runner.calls`
- `scripts/tests/test_ll_loop_execution.py` — integration tests that call `_evaluate` directly; must be verified after refactor

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Downstream usage of `is_slash_command` in `_run_action` (lines 554–578):**
- Line 559: emitted in `action_start` event payload under key `"is_prompt"`
- Line 567: passed as `is_slash_command=` kwarg to `action_runner.run()` — **load-bearing**: determines whether `DefaultActionRunner` spawns `["claude", ..., "-p", action]` vs `["bash", "-c", action]`
- Line 578: emitted in `action_complete` event payload under key `"is_prompt"`

**Downstream usage of `is_prompt` in `_evaluate` (lines 624–629):**
- Line 629: gates evaluator selection — `True` → `evaluate_llm_structured(...)`, `False` → `evaluate_exit_code(action_result.exit_code)`
- Only reached when `state.evaluate is None` and `action_result is not None` (lines 620–622)

## Implementation Steps

1. Add `_is_prompt_action(self, state: StateConfig) -> bool` to `FSMExecutor` in `executor.py` (insert near other helpers; see existing pattern from `_build_context()` at line ~750). Can also be `@staticmethod` since it needs no instance state — see `git_lock.py:183` for that convention.
2. In `_run_action()` at lines 557–560: replace the `is_slash_command` inline block with `is_slash_command = self._is_prompt_action(state)`. Note: the heuristic fallback currently uses the post-interpolation `action` string; switch to using `state.action` (raw template) to match `_evaluate` and eliminate the divergence.
3. In `_evaluate()` at lines 627–630: replace the `is_prompt` inline block with `is_prompt = self._is_prompt_action(state)`.
4. Run `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_ll_loop_execution.py -v` to verify no behavioral regressions.

### Test Approach

_Added by `/ll:refine-issue` — based on codebase analysis:_

The existing `TestActionType` class in `test_fsm_executor.py:233–348` tests detection behavior end-to-end via `executor.run()` and `mock_runner.calls` — **private methods are never called directly in this codebase**. Do not add a direct unit test for `_is_prompt_action`; instead, verify that the existing `TestActionType` tests still pass after extraction. If the `@staticmethod` form is chosen, add one additional test case in `TestActionType` for an action that uses an interpolation variable (e.g., `action: "${cmd}"`) to confirm the raw-template heuristic is used consistently.

## Impact

- **Priority**: P4 — Code quality improvement; eliminates a latent divergence
- **Effort**: Small — Small refactor, no behavior change
- **Risk**: Low — Pure extraction; both existing paths are preserved
- **Breaking Change**: No

## Labels

`enhancement`, `fsm`, `executor`, `refactor`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T22:10:34Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:refine-issue` - 2026-03-07T22:30:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/92d72a99-e16b-4c87-9ec6-73861d732416.jsonl`
- `/ll:confidence-check` - 2026-03-07T23:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4838eb0-1445-40b3-888f-e1478bd2dbcf.jsonl`
- `/ll:ready-issue` - 2026-03-07T23:30:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b465cdda-4652-4db9-85ba-9f6d533dcac8.jsonl`

## Resolution

- **Status**: Completed
- **Resolved**: 2026-03-07
- **Solution**: Extracted `_is_prompt_action(self, state: StateConfig) -> bool` helper on `FSMExecutor`. Both `_run_action` and `_evaluate` now call this method. The heuristic fallback uses `state.action` (raw template) consistently, eliminating the divergence with the post-interpolation string.
- **Files Changed**: `scripts/little_loops/fsm/executor.py`
- **Tests**: 140 passed (0 failures)

## Session Log
- `/ll:manage-issue` - 2026-03-07T23:45:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

**Completed** | Created: 2026-03-07 | Priority: P4
