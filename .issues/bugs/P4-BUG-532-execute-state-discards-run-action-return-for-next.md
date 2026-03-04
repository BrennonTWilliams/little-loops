---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# BUG-532: `_execute_state` Discards `_run_action` Return Value for `state.next`-Routed States

## Summary

When a state has an unconditional `next` transition, `_execute_state` calls `_run_action` but discards the returned `ActionResult`. This means `self.prev_result` is NOT updated after the action runs. Subsequent states referencing `${prev.output}` or `${prev.exit_code}` receive stale values from the last non-`next` state, not from the `next`-routed state's action.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 447–451 (at scan commit: 47c81c8)
- **Anchor**: `in method FSMExecutor._execute_state()`, unconditional-transition branch
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/executor.py#L447-L451)
- **Code**:
```python
if state.next:
    if state.action:
        self._run_action(state.action, state, ctx)   # return value discarded
    return interpolate(state.next, ctx)
```

Compare with the conditional-transition branch which correctly updates `prev_result`:
```python
result = self._run_action(state.action, state, ctx)
self.prev_result = result   # stored
```

## Current Behavior

In loops using the `goal` or `imperative` paradigm (compiled by `compile_goal` and `compile_imperative`), `fix` and `step_N` states use `next` routing. If these states have actions, the action output is silently discarded. `${prev.output}` in the next state reflects the *evaluate/check* state's output, not the fix/step output.

## Expected Behavior

`_run_action` return value is always stored in `self.prev_result`, regardless of whether the state uses `next` or conditional routing.

## Motivation

Any `goal` or `imperative` loop that references `${prev.output}` in a state following a `next`-routed fix/step gets silently wrong data. The bug is hidden because the common pattern puts evaluation logic in states with conditional routing — but any loop that references `prev` in the state immediately after a `next`-routing state is affected.

## Steps to Reproduce

1. Create a loop with two states: `fix` (with action, `next: evaluate`) and `evaluate` (references `${prev.output}`)
2. Run the loop
3. Observe: `${prev.output}` in `evaluate` contains the output from the *previous evaluate call*, not from `fix`

## Actual Behavior

`${prev.output}` is stale (from the last state with conditional routing) in any state that follows a `next`-routed state.

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py`
- **Anchor**: `in method FSMExecutor._execute_state()`, `if state.next:` branch
- **Cause**: `_run_action` return value not captured and assigned to `self.prev_result`

## Proposed Solution

```python
if state.next:
    if state.action:
        result = self._run_action(state.action, state, ctx)
        self.prev_result = result    # add this line
    return interpolate(state.next, ctx)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._execute_state()`, `if state.next:` branch

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py` — wraps `FSMExecutor`; inherits fix
- `scripts/little_loops/fsm/compilers.py` — `compile_goal` and `compile_imperative` produce `next`-routed states

### Similar Patterns
- The else branch in `_execute_state` correctly assigns `self.prev_result = result`

### Tests
- `scripts/tests/test_ll_loop_execution.py` — add: `next`-routed state action output captured in `prev_result`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `self.prev_result = result` after `self._run_action(...)` in the `if state.next:` branch
2. Add test confirming `${prev.output}` in post-`next` state contains correct value

## Impact

- **Priority**: P4 — Affects only loops that reference `${prev}` after a `next`-routed state; silent wrong data rather than crash
- **Effort**: Small — 1-line fix
- **Risk**: Low — Purely additive; no existing behavior removed
- **Breaking Change**: No (corrects silently wrong behavior)

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | Execution engine — action execution and state transitions (line 1425), variable interpolation namespaces (line 855) |
| `docs/guides/LOOPS_GUIDE.md` | `${prev.output}` interpolation variable (line 295) |

## Labels

`bug`, `ll-loop`, `executor`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; noted `test_fsm_executor.py:23` (MockActionRunner) for test pattern
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P4
