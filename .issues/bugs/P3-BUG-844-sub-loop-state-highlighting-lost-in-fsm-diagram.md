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
- `scripts/little_loops/fsm/executor.py:592–599` — `_sub_event_callback` closure stamps child events with `"depth": depth`; read-only context, no changes needed

### Similar Patterns
- `current_iteration = [0]` at line 307 — same mutable-list closure pattern to use
- `loop_start_time` at line 308 — plain float closed over alongside `current_iteration` (read-only, no list needed)
- `layout.py:1427–1432` — `_render_fsm_diagram(fsm, verbose, highlight_state, highlight_color, edge_label_colors)` signature

### Tests
- `scripts/tests/test_ll_loop_display.py` — add test using `MockExecutor` that emits depth-0 then depth-1 `state_enter` events and asserts `_render_fsm_diagram` is called with the depth-0 state as `highlight_state` for all events

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact spy pattern to use for the new test** (follow `test_ll_loop_display.py:1603–1627`):

```python
from little_loops.cli.loop import layout as layout_mod

events = [
    {"event": "state_enter", "state": "run_sub_loop", "iteration": 1},          # depth=0
    {"event": "state_enter", "state": "child_state_1", "iteration": 1, "depth": 1},  # depth=1
    {"event": "state_enter", "state": "child_state_2", "iteration": 2, "depth": 1},  # depth=1
]
executor = MockExecutor(events)
with patch.object(
    layout_mod, "_render_fsm_diagram", wraps=layout_mod._render_fsm_diagram
) as mock_render:
    run_foreground(executor, self._make_fsm(), self._make_args(show_diagrams=True))
    # All three calls should highlight "run_sub_loop" (the depth-0 state)
    for call_args in mock_render.call_args_list:
        assert call_args.kwargs["highlight_state"] == "run_sub_loop"
```

Note: use `layout_mod` (not `info_mod`) because `_helpers.py`'s `show_diagrams` branch does `from little_loops.cli.loop.layout import _render_fsm_diagram` at runtime. The existing spy tests at lines 1603–1627 and 1659–1686 confirm this import path.

**Depth event structure** (from `executor.py:592–599`): child events arrive as `{"event": "state_enter", "state": "<child-state>", "iteration": N, "depth": 1}`. The `"depth"` key is added by `_sub_event_callback` wrapping the child executor's callback. The parent's own `state_enter` for the sub-loop state has no `"depth"` key (defaults to 0 in the handler).

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

## Related Issues

- **ENH-846** (`.issues/enhancements/P3-ENH-846-show-sub-loop-fsm-diagram-alongside-parent.md`) — complementary enhancement to show the child FSM diagram alongside the parent; may share the depth-tracking variable introduced here
- **BUG-759** (`.issues/bugs/P3-BUG-759-fsm-diagram-shifts-horizontally-when-state-highlighted.md`) — open bug: diagram shifts horizontally during highlighting; may interact with this fix
- **ENH-839** (`.issues/enhancements/P3-ENH-839-split-layout-py-diagram-rendering-into-focused-modules.md`) — planned restructuring of `layout.py`; no conflict, but worth noting if ENH-839 lands first

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `fsm-diagram`, `sub-loop`, `show-diagrams`, `captured`

---

## Resolution

**Fixed** in `scripts/little_loops/cli/loop/_helpers.py`:

1. Added `last_parent_state: list[str | None] = [None]` alongside `current_iteration` in `run_foreground()` to track the last depth=0 state.
2. In the `state_enter` handler, update `last_parent_state[0] = state` when `depth == 0`.
3. Derive `highlight = state if depth == 0 else last_parent_state[0]` and pass that to `_render_fsm_diagram` instead of always using `state`.
4. Added regression test `test_sub_loop_diagram_keeps_parent_state_highlighted` in `test_ll_loop_display.py`.

---

## Status

**Completed** | Created: 2026-03-20 | Resolved: 2026-03-20 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:ready-issue` - 2026-03-20T21:21:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c36d8d5-c74f-40f7-ba5e-174db436832e.jsonl`
- `/ll:refine-issue` - 2026-03-20T21:16:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3303c29-3790-45d8-bfd8-d2eed0c1be4f.jsonl`
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1bf4f47d-175f-43a1-a162-27f1c4d41801.jsonl`
