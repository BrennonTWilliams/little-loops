---
id: BUG-844
type: BUG
priority: P3
title: Sub-loop state highlighting lost in FSM diagram
discovered_date: 2026-03-20
discovered_by: capture-issue
---

# BUG-844: Sub-loop state highlighting lost in FSM diagram

## Summary

When `ll-loop run` executes a state that runs a sub-loop (`loop: child-loop-name`), the `--show-diagrams` display loses the highlight on the parent's sub-loop state after the child's first state begins. The parent FSM diagram goes unhighlighted for the entire duration of child loop execution.

## Current Behavior

1. Parent enters sub-loop state "run_sub_loop" → `state_enter` (depth=0) → diagram highlights "run_sub_loop" ✓
2. Child starts, enters "child_state_1" → `state_enter` (depth=1, state="child_state_1") → rendered against parent FSM → no match → **no highlight** ✗
3. Child enters "child_state_2" → same → no highlight ✗

## Expected Behavior

While the child sub-loop is executing, the parent FSM diagram should keep the sub-loop state (depth=0 state that triggered the child) highlighted throughout all child `state_enter` events.

## Motivation

Visual coherence during sub-loop execution — the user should always know where in the parent loop execution stands. Without this fix, the diagram goes dark during potentially long child loop runs, defeating the purpose of `--show-diagrams`.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `in display_progress()` closure, `state_enter` handler (~lines 318–344)
- **Cause**: `display_progress()` handles all `state_enter` events uniformly regardless of depth. When a child sub-loop emits `state_enter` with `depth=1`, the handler extracts the child state name and passes it as `highlight_state` to `_render_fsm_diagram(fsm, ...)`. The child state doesn't exist in the parent FSM, so nothing gets highlighted.

## Steps to Reproduce

1. Create a loop YAML with a state that has `loop: child-loop-name`
2. Run `ll-loop run <loop> --show-diagrams`
3. Observe the parent FSM diagram — the sub-loop state box becomes unhighlighted as soon as the child loop starts executing

## Proposed Solution

Track the last known depth-0 state in a mutable closure variable. When rendering the diagram for child events (depth > 0), use the tracked parent state as `highlight_state` instead of the child state.

In `run_foreground()`, add alongside `current_iteration`:
```python
last_parent_state: list[str | None] = [None]
```

In the `state_enter` handler:
```python
if depth == 0:
    last_parent_state[0] = state
highlight = state if depth == 0 else last_parent_state[0]
diagram = _render_fsm_diagram(
    fsm,
    highlight_state=highlight,   # was: state
    highlight_color=highlight_color,
    edge_label_colors=edge_label_colors,
)
```

The `state` variable is still used unchanged for the text output line (showing child progress text is correct behavior).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — the only file to change
  - `run_foreground()` starting at line 282
  - `display_progress()` closure starting at line 310
  - `current_iteration = [0]` at line 307 — follow this pattern for the new variable
  - `state_enter` handler at lines 318–344 — where the fix goes

### Dependent Files (Callers/Importers)
- `scripts/tests/test_ll_loop_display.py` — add regression test

### Similar Patterns
- `current_iteration = [0]` at line 307 — same mutable-list closure pattern to use

### Tests
- `scripts/tests/test_ll_loop_display.py` — add test using `MockExecutor` that emits depth-0 then depth-1 `state_enter` events and asserts `_render_fsm_diagram` is called with the depth-0 state as `highlight_state` for all events

## Implementation Steps

1. Add `last_parent_state: list[str | None] = [None]` alongside `current_iteration` in `run_foreground()`
2. In the `state_enter` branch, update `last_parent_state[0] = state` when `depth == 0`
3. Derive `highlight = state if depth == 0 else last_parent_state[0]`
4. Change `_render_fsm_diagram` call to pass `highlight_state=highlight` instead of `highlight_state=state`
5. Add regression test in `test_ll_loop_display.py`

## Impact

- **Priority**: P3 - Display bug during sub-loop execution; no functional impact
- **Effort**: Small - Single file change (~5 lines), well-scoped
- **Risk**: Low - Only affects `--show-diagrams` rendering path
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `fsm-diagram`, `sub-loop`, `show-diagrams`, `captured`

---

## Status

**Open** | Created: 2026-03-20 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1bf4f47d-175f-43a1-a162-27f1c4d41801.jsonl`
