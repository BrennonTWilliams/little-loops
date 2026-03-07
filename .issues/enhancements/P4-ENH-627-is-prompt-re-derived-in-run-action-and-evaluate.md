---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# ENH-627: `is_prompt`/`is_slash_command` re-derived independently in `_run_action` and `_evaluate` with subtle divergence

## Summary

`FSMExecutor._run_action()` and `_evaluate()` each independently compute whether the current state's action is a slash command or prompt. The two computations use slightly different inputs: `_run_action` uses the post-interpolation `action` string, while `_evaluate` uses the raw `state.action` template. If the template and the interpolated result differ in their leading character, the two checks disagree about whether the action is a prompt. Additionally, computing the same thing twice adds coupling.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 541–544 and 611–614 (at scan commit: 12a6af0)
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
- All existing `FSMExecutor` tests pass with no behavior change
- New `_is_prompt_action` helper has direct unit test coverage

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

### Tests
- `scripts/tests/test_fsm_executor.py` — existing tests cover behavior; add test for `_is_prompt_action` helper directly

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Extract `_is_prompt_action(state: StateConfig) -> bool` method on `FSMExecutor`
2. Replace both inline checks in `_run_action()` and `_evaluate()` with `self._is_prompt_action(state)`

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

---

**Open** | Created: 2026-03-07 | Priority: P4
