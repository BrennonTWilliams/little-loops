---
id: ENH-846
type: ENH
priority: P3
title: Show sub-loop FSM diagram alongside parent during sub-loop execution
discovered_date: 2026-03-20
discovered_by: capture-issue
confidence_score: 88
outcome_confidence: 97
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

Loading the child FSM requires `loops_dir`, which is accessible via `executor.loops_dir` (stored on `PersistentExecutor`, `persistence.py:323`) — **not** via `args`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`loops_dir` correction**: The parameter is **not** on `args` inside `run_foreground()`. It lives on `executor.loops_dir` (`PersistentExecutor.loops_dir`, `persistence.py:323`). The `display_progress` closure already captures `executor`, so use `executor.loops_dir` directly.

**`logger` gap**: `load_loop(name_or_path, loops_dir, logger)` requires a logger, but `run_foreground()` signature (`_helpers.py:282`) has no logger parameter. Options: (a) use `logging.getLogger(__name__)` inline in the handler, or (b) call `resolve_loop_path()` + `load_and_validate()` directly with a bare `try/except` and silent failure (child diagram simply not rendered if load fails).

**`depth` injection**: The `depth` key is not emitted by `FSMExecutor._emit()` — it is injected by `_sub_event_callback` at `executor.py:594–599`. Top-level events have no `depth` key (`event.get("depth", 0) == 0`); first-level child events get `depth=1`.

**`StateConfig.loop` type**: `fsm.states.get(state)` returns `StateConfig | None` (`schema.py:230`), not `FSMState`. The `loop` field is `str | None` — the sub-loop name/path string.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py`
  - `run_foreground()` at line 282 — add `current_child_fsm: list[FSMLoop | None] = [None]` near `current_iteration = [0]` (line 307)
  - `display_progress()` closure `state_enter` handler (lines 318–344) — detect sub-loop entry/exit, conditionally render child diagram
  - `load_loop` already defined at line 114 in this module; no new import needed

### Dependent Files (Callers/Importers)
- `scripts/tests/test_ll_loop_display.py` — add regression test
- `scripts/little_loops/fsm/executor.py:571` — `_execute_sub_loop()` already loads the child FSM at line 586, but never surfaces it to the event callback; this enhancement re-loads it in the display layer

### Similar Patterns
- `current_iteration = [0]` at `_helpers.py:307` — same mutable-list closure pattern (comment: `# Use list to allow mutation in closure`)
- `last_parent_state: list[str | None] = [None]` from BUG-844 — parallel pattern for the new variable
- Separator lines using `\u2500` (`─`): `info.py:596–605` — `"─" * max(0, tw - len(left) - len(right))` fill pattern

### Tests
- `scripts/tests/test_ll_loop_display.py` — add test using `MockExecutor` that emits a depth-0 sub-loop `state_enter` then a depth-1 `state_enter`, asserting `_render_fsm_diagram` is called twice for the child event

### Codebase Research Findings — Test Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Mock target is `layout_mod._render_fsm_diagram`** (not `info._render_fsm_diagram`), because `run_foreground` imports it from `little_loops.cli.loop.layout`:
```python
from little_loops.cli.loop import layout as layout_mod
with patch.object(layout_mod, "_render_fsm_diagram", wraps=layout_mod._render_fsm_diagram) as mock_render:
    run_foreground(executor, parent_fsm, args)
    assert mock_render.call_count == 2  # once for parent, once for child
    calls = mock_render.call_args_list
    assert calls[0] == call(parent_fsm, highlight_state="sub_loop_state", ...)
    assert calls[1] == call(child_fsm, highlight_state="child_state_1", ...)
```

**`MockExecutor` sub-loop event sequence** (`test_ll_loop_display.py:34-51` shows the class):
```python
events = [
    {"event": "state_enter", "state": "sub_loop_state", "iteration": 1},          # depth=0
    {"event": "state_enter", "state": "child_state_1", "iteration": 1, "depth": 1},  # depth=1
]
```

**FSM fixture**: The new test needs a `FSMLoop` with one state having `loop="child-loop-name"` set on its `StateConfig`, plus a child `FSMLoop` to be returned by the mocked `load_loop`. Existing `_make_fsm()` helpers in the test file create simple FSMs without sub-loop states — create a new fixture or extend `_make_fsm()` with an optional `sub_loop_state` parameter.

### Configuration
- No new config flags; this activates automatically under `--show-diagrams` when a sub-loop state is executing

## Scope Boundaries

- Out of scope: depth > 1 nesting (child-of-child loops) — only one level of child diagram is shown; deeper nesting would require a stack, which is a separate enhancement
- Out of scope: new CLI flags or config options
- Out of scope: any changes to `layout.py` rendering functions

## Implementation Steps

1. Add `current_child_fsm: list[FSMLoop | None] = [None]` at `_helpers.py:309` (directly after `last_parent_state` at line 308)
2. In the `state_enter` branch at `_helpers.py:319`, when `depth == 0`:
   a. Look up `fsm_state = fsm.states.get(state)` — returns `StateConfig | None` (`schema.py:230`), not `FSMState`
   b. If `fsm_state is not None and fsm_state.loop is not None`, load the child FSM: `current_child_fsm[0] = load_loop(fsm_state.loop, executor.loops_dir, logging.getLogger(__name__))` — note: `executor.loops_dir`, **not** `args.loops_dir` or `getattr(args, "loops_dir", ...)`; wrap in `try/except (FileNotFoundError, ValueError)` to leave `current_child_fsm[0]` unchanged on failure
   c. If `fsm_state is None or fsm_state.loop is None`, clear `current_child_fsm[0] = None`
3. In the diagram rendering block at `_helpers.py:332–342`, check `current_child_fsm[0]`:
   - If set: render parent diagram, print separator `── sub-loop: <fsm_state.loop> ──` using `\u2500` fill (pattern: `info.py:596–605`), render child diagram with `highlight_state=state`
   - If not set: render parent diagram only (existing behavior, unchanged)
4. Ensure BUG-844 fix (`last_parent_state`) is applied first — this enhancement depends on it for correct parent highlighting; `last_parent_state[0]` provides the parent state name when depth > 0
5. Add `import logging` at the top of `_helpers.py` if not already present
6. Add regression test in `test_ll_loop_display.py` — mock `load_loop` to return a child `FSMLoop`, mock `layout_mod._render_fsm_diagram`, emit depth-0 + depth-1 events, assert double call with correct args

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-03-20_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 97/100 → HIGH CONFIDENCE

### Concerns
- ~~**BUG-844 is an unresolved prerequisite**~~: BUG-844 is now completed. `last_parent_state` tracking is already in `_helpers.py:308`. This concern is resolved.

## Resolution

**Completed** on 2026-03-20

### Changes Made

- `scripts/little_loops/cli/loop/_helpers.py`:
  - Added `import logging`
  - Added `current_child_fsm: list[FSMLoop | None] = [None]` closure variable alongside `last_parent_state`
  - On `depth == 0` `state_enter` events: looks up `fsm.states.get(state)`; if `fsm_state.loop` is set, loads child FSM via `load_loop(fsm_state.loop, executor.loops_dir, ...)` with `try/except`; otherwise clears `current_child_fsm[0]`
  - On `show_diagrams` rendering: after printing parent diagram, if `depth > 0` and `current_child_fsm[0]` is set, prints separator (`── sub-loop: <name> ──`) and child FSM diagram with `highlight_state=state`

- `scripts/tests/test_ll_loop_display.py`:
  - Added `loops_dir: Path = Path(".")` to `MockExecutor.__init__`
  - Added `test_sub_loop_child_diagram_rendered_during_sub_loop_execution` regression test

### Verification

All 121 tests pass (`python -m pytest scripts/tests/test_ll_loop_display.py`).

## Status

**Completed** | Created: 2026-03-20 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-03-20T21:39:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/51a33daf-4007-40cc-a0a0-fa27ffa9df00.jsonl`
- `/ll:refine-issue` - 2026-03-20T21:02:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/66287049-8150-4128-9cfd-31f459fc62db.jsonl`
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae4f7fa9-4038-444b-b34c-8c4cea5178e2.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a252f10d-b254-4738-9e2f-e6571da6b831.jsonl`
