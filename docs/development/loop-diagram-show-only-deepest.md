# Plan: Show Only Deepest Active Loop in Pinned Pane

## Context

`--show-diagrams summary` was falling back to the neighborhood layout because both the parent FSM diagram and the sub-loop FSM diagram were stacked in the pinned pane, consuming too much vertical space for the `layered` topology to fit before `_choose_pinned_layout` degraded it. The fix is to show only the currently-executing (deepest active) loop, replacing the stacked view, and inject the parent context into the header line so the user still knows where they are in the overall run.

## Approach

Determine the deepest active depth by walking `child_fsm_stack` + `last_state_at_depth`, then render only that FSM's diagram. When a sub-loop is active, the header gains a breadcrumb showing immediate parent loop name and current parent state.

**Header formats:**
- Parent only: `== loop: autodev =====================`
- Sub-loop active: `== loop: refine-to-ready-issue (autodev › refine_current) ===`
- Deeper nesting: show immediate parent only — `== loop: grandchild (child-loop › wire_issue) ===`

## File to Modify

`scripts/little_loops/cli/loop/_helpers.py` — two sites:

### Site 1: `_build_pinned_pane` (lines ~314–332)

Replace the current block that renders the parent diagram and then iterates `child_fsm_stack` to render each sub-loop with a separator:

```python
# --- REMOVE THIS ---
lines.append(header_text + "=" * ...)
parent_diagram = _render_one(fsm, parent_highlight, prev_highlight)
...
for d, child_fsm_at_d in sorted(child_fsm_stack.items()):
    ...sep + child diagram...
```

With:

```python
# Find deepest active loop
active_fsm = fsm
active_state = parent_highlight
active_prev = prev_highlight
active_depth = 0
for d in sorted(child_fsm_stack.keys()):
    child = child_fsm_stack[d]
    if child is not None and (d + 1) in last_state_at_depth:
        active_fsm = child
        active_state = last_state_at_depth.get(d + 1)
        active_prev = prev_map.get(d + 1)
        active_depth = d + 1

# Header: inject immediate parent context when in a sub-loop
if active_depth > 0:
    parent_fsm_name = child_fsm_stack.get(active_depth - 2, {})  # see note below
    # immediate parent name + state
    imm_parent_name = fsm.name if active_depth == 1 else (child_fsm_stack.get(active_depth - 2) or fsm).name
    imm_parent_state = last_state_at_depth.get(active_depth - 1, "")
    header_text = f"== loop: {active_fsm.name} ({imm_parent_name} › {imm_parent_state}) "
else:
    header_text = f"== loop: {fsm.name} "

lines.append(header_text + "=" * max(0, cols - len(header_text)))
diagram = _render_one(active_fsm, active_state, active_prev)
if diagram:
    lines.extend(diagram.split("\n"))
```

Note: for depth > 1 the immediate parent FSM object is `child_fsm_stack[active_depth - 2]` (the child loaded at depth `active_depth-2` runs at depth `active_depth-1`). For depth 1 it is just `fsm`.

### Site 2: Non-pinned `show_diagrams` path in `display_progress` (lines ~770–839)

Same logic applied inline:
- Walk `child_fsm_stack` + `last_state_at_depth` to find deepest active FSM, state, scope
- Build header with breadcrumb
- Render single diagram for the active FSM
- Remove the `for d, child_fsm_at_d in sorted(child_fsm_stack.items())` loop that renders sub-loops separately

The scope fallback logic (checking if `parent_highlight` is reachable in `main` scope) should apply to whichever FSM is being shown.

## Verification

1. Run a loop that uses a sub-loop (e.g., `autodev`) with `--show-diagrams summary` and observe that:
   - While the sub-loop is executing, only the sub-loop diagram is shown
   - The header reads `== loop: refine-to-ready-issue (autodev › refine_current) ===`
   - When the sub-loop finishes and the parent resumes, the parent diagram is shown again with the normal header
2. Run with a narrower terminal — verify the layered view no longer degrades to neighborhood for the common case (sub-loop is small enough to fit alone)
3. Run with `--show-diagrams detailed` and `--show-diagrams=layered` to confirm topology-pinned mode still works unchanged
4. Run existing tests: `python -m pytest scripts/tests/test_ll_loop_display.py scripts/tests/test_cli_loop_lifecycle.py -v`
