---
id: ENH-846
type: ENH
priority: P3
title: Show sub-loop FSM diagram alongside parent during sub-loop execution
discovered_date: 2026-03-20
discovered_by: capture-issue
---

# ENH-846: Show sub-loop FSM diagram alongside parent during sub-loop execution

## Summary

When `ll-loop run` executes a sub-loop state and `--show-diagrams` is passed, only the parent FSM diagram is displayed. The child loop's FSM is never rendered, so the user has no visibility into where execution stands *within* the child. This enhancement renders the child FSM diagram below the parent diagram throughout sub-loop execution, with the active child state highlighted, then removes it when the sub-loop exits.

## Motivation

`--show-diagrams` exists to give users real-time orientation during loop execution. When a sub-loop state runs a child loop, that child loop may execute many states over a long period, yet the display shows only "sub-loop state is running" in the parent diagram. The user is left blind to child progress. Rendering both diagrams — parent (showing which sub-loop state is active) and child (showing the current child state) — completes the promise of `--show-diagrams` for nested loops and mirrors the call-stack mental model users already have.

## Expected Behavior

1. Parent enters sub-loop state → parent FSM diagram renders (sub-loop state highlighted)
2. Child starts, enters "child_state_1" → parent FSM renders (sub-loop state still highlighted, per BUG-844) + separator header + child FSM renders ("child_state_1" highlighted)
3. Child enters "child_state_2" → same layout, child FSM updates to highlight "child_state_2"
4. Child loop completes → parent returns to depth-0 execution → child diagram disappears, only parent renders

Display shape per `state_enter` event during sub-loop execution:
```
[parent FSM diagram — sub-loop state highlighted]
── sub-loop: child-loop-name ──
[child FSM diagram — current child state highlighted]
```

## Current Behavior

Only the parent FSM diagram is rendered for all `state_enter` events. Child `state_enter` events (depth > 0) render the parent diagram with the child state name passed as `highlight_state`, which matches nothing in the parent FSM (the issue tracked by BUG-844). The child FSM is never rendered.

## Proposed Solution

In `run_foreground()`, track the active child FSM in a mutable closure variable alongside `current_iteration` and `last_parent_state` (from BUG-844):

```python
current_child_fsm: list[FSMLoop | None] = [None]
```

In the `state_enter` handler:
- When `depth == 0`: look up the FSM state by name; if `fsm_state.loop` is set, load the child FSM via `load_loop()` and store it in `current_child_fsm[0]`; if not set (sub-loop just exited), clear `current_child_fsm[0] = None`
- When rendering, if `current_child_fsm[0]` is not None, print parent diagram, then a separator line (`── sub-loop: <child_name> ──`), then the child diagram with `highlight_state=state` (the child state)
- The child state name is used as-is for the child FSM highlight; the parent uses `last_parent_state[0]` (per BUG-844)

Loading the child FSM requires `loops_dir`, which is available via `args` in `run_foreground()`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py`
  - `run_foreground()` starting at line 282 — add `current_child_fsm: list[FSMLoop | None] = [None]`
  - `display_progress()` closure `state_enter` handler (lines 318–344) — detect sub-loop entry/exit, conditionally render child diagram
  - Import `load_loop` from the same module (already defined at line 114)

### Dependent Files (Callers/Importers)
- `scripts/tests/test_ll_loop_display.py` — add regression test

### Similar Patterns
- `current_iteration = [0]` at line 307 — same mutable-list closure pattern
- `last_parent_state: list[str | None] = [None]` from BUG-844 — parallel pattern for the new variable

### Tests
- `scripts/tests/test_ll_loop_display.py` — add test using `MockExecutor` that emits depth-0 sub-loop `state_enter` then depth-1 `state_enter` events and asserts `_render_fsm_diagram` is called twice per child event (once for parent, once for child FSM), with correct `highlight_state` for each

### Configuration
- No new config flags; this activates automatically under `--show-diagrams` when a sub-loop state is executing

## Scope Boundaries

- Out of scope: depth > 1 nesting (child-of-child loops) — only one level of child diagram is shown; deeper nesting would require a stack, which is a separate enhancement
- Out of scope: new CLI flags or config options
- Out of scope: any changes to `layout.py` rendering functions

## Implementation Steps

1. Add `current_child_fsm: list[FSMLoop | None] = [None]` alongside `current_iteration` in `run_foreground()`
2. In the `state_enter` branch, when `depth == 0`:
   a. Look up `fsm.states.get(state)` to get the `FSMState`
   b. If `fsm_state.loop` is set, call `load_loop(fsm_state.loop, loops_dir, logger)` and store result in `current_child_fsm[0]`
   c. If not set, clear `current_child_fsm[0] = None`
3. After rendering the parent diagram (or instead of single render), check `current_child_fsm[0]`:
   - If set: print parent diagram + separator + child diagram with `highlight_state=state` (child state name)
   - If not set: print parent diagram only (existing behavior)
4. Ensure BUG-844 fix (`last_parent_state`) is applied first — this enhancement depends on it for correct parent highlighting
5. Add regression test in `test_ll_loop_display.py`

## Impact

- **Priority**: P3 — Display enhancement during sub-loop execution; no functional impact
- **Effort**: Small-Medium — ~20–30 lines; requires loading child FSM on state entry, which is I/O but negligible for display path
- **Risk**: Low — Only affects `--show-diagrams` rendering path; `load_loop()` already handles missing/invalid paths gracefully
- **Breaking Change**: No
- **Prerequisite**: BUG-844 (parent highlight tracking) should be applied first; this enhancement builds on that fix

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `fsm-diagram`, `sub-loop`, `show-diagrams`, `captured`

---

## Status

**Open** | Created: 2026-03-20 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae4f7fa9-4038-444b-b34c-8c4cea5178e2.jsonl`
