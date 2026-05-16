---
discovered_date: 2026-02-19
discovered_by: user-report
follows: ENH-444
confidence_score: 100
---

# BUG-445: FSM diagram renders non-main-path edges as plain text instead of 2D routed lines

## Summary

The 2D ASCII box renderer introduced in ENH-444 only draws proper box-drawing characters for the main flow (top row). All other edges — branches and back-edges — are rendered as flat text annotations below the diagram with no spatial connection to the boxes above. This defeats the purpose of a 2D renderer.

## Steps to Reproduce

1. Define or use any loop with branches or back-edges (e.g., `codebase-scan`, `tests-until-passing`)
2. Run `ll-loop show <loop-name>`
3. Observe: Non-main-path edges are rendered as plain text annotations below the diagram instead of 2D routed lines

## Actual Behavior

Non-main-path edges (branches and back-edges) are rendered as flat text strings like `src ──(label)──▶ dst` with no graphical connection to the box diagram above. Only the main flow (top row) uses proper 2D box-drawing characters. See Current Behavior for specific examples.

## Current Behavior

`ll-loop show codebase-scan` produces:

```
  ┌────────┐          ┌────────┐          ┌────────┐          ┌────────────┐             ┌──────┐
  │ step_0 │───next──▶│ step_1 │───next──▶│ step_2 │───next──▶│ check_done │───success──▶│ done │
  └────────┘          └────────┘          └────────┘          └────────────┘             └──────┘
       check_done ──(fail)──▶ step_0
```

The `check_done → step_0` back-edge is a text string with no graphical connection to either box.

Similarly, `ll-loop show tests-until-passing`:

```
  ┌──────────┐             ┌──────┐
  │ evaluate │───success──▶│ done │
  └──────────┘             └──────┘
       evaluate ──(fail)──▶ fix
       evaluate ──(error)──▶ fix
       fix ──(next)──▶ evaluate
```

Only the top row is a proper 2D diagram. The `evaluate → fix`, `fix → evaluate` edges are unconnected text.

## Expected Behavior

Non-main-path edges should be rendered as actual 2D routed lines using box-drawing characters, with visual connections to the source and target boxes. For example, `codebase-scan` should look something like:

```
  ┌────────┐          ┌────────┐          ┌────────┐          ┌────────────┐             ┌──────┐
  │ step_0 │───next──▶│ step_1 │───next──▶│ step_2 │───next──▶│ check_done │───success──▶│ done │
  └────────┘          └────────┘          └────────┘          └────────────┘             └──────┘
       ▲                                                             │
       └─────────────────────────── fail ────────────────────────────┘
```

And `tests-until-passing` should render the `evaluate ↔ fix` cycle as connected boxes below, not text:

```
  ┌──────────┐             ┌──────┐
  │ evaluate │───success──▶│ done │
  └──────────┘             └──────┘
       │  ▲
  fail │  │ next
       ▼  │
     ┌─────┐
     │ fix │
     └─────┘
```

The key requirements are:
- Back-edges drawn with vertical drops from source, horizontal runs, and arrows into target
- Off-path states (like `fix`) rendered as boxes, not just names in text
- Edge labels placed along the routed lines
- Visual connection to the actual box columns (using `col_start`/`col_center` positions)

## Root Cause

In `_render_2d_diagram()` at `scripts/little_loops/cli/loop/info.py:298-306`:

```python
    # --- Branch and back-edge routing below the main flow ---
    non_self_branches = [(s, d, lbl) for s, d, lbl in branches if s != d]
    non_self_back = [(s, d, lbl) for s, d, lbl in back_edges if s != d]
    all_extra = non_self_branches + non_self_back

    for src, dst, label in all_extra:
        # Use text annotation: src ──(label)──▶ dst
        lines.append(f"       {src} ──({label})──▶ {dst}")
```

This loop simply appends plain text strings for every non-main-path edge. The `col_start` and `col_center` position data computed earlier in the function is never used to place these edges spatially. The original ENH-444 issue's expected behavior diagram showed proper 2D routing, but the implementation used text annotations as a shortcut.

## Proposed Solution

Replace the text annotation block (lines 298-306) with actual 2D edge routing:

1. **Back-edges** (target is earlier in BFS order than source): Draw a vertical line down from the source box's center column, a horizontal line running left to the target box's center column, and an upward arrow into the target box. Place the edge label along the horizontal segment.

2. **Forward branches** (target is later but not on main path): Draw a vertical line down from the source box, horizontal to the target position, and render the off-path target as a box.

3. **Off-path state boxes**: States not on the main path (currently tracked in `off_path` list, lines 185-190) should be rendered as Unicode boxes below the main flow, positioned using their `col_start` values.

The function already computes `col_start`, `col_center`, `off_path`, and `total_width` — all the positional data needed. The fix is to use these positions to build additional character grid rows instead of appending text strings.

### Edge routing strategy

For each non-main-path edge `(src, dst, label)`:
- Compute `src_col = col_center[src]` and `dst_col = col_center[dst]` (or `col_start[dst]` for off-path targets)
- Add rows below the main flow: a connector row (vertical drop `│` from source), a horizontal routing row (`└───label───┘` or `└───label───▶`), and optionally a connector row into the target (`│` rising into target box)
- Use `├`, `┤`, `┘`, `└`, `┐`, `┌` corner characters at turns
- Multiple back-edges should stack vertically with increasing offset to avoid overlap

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — rewrite lines 298-306 of `_render_2d_diagram()`

### Tests
- `scripts/tests/test_ll_loop_display.py` — update assertions in `TestRenderFsmDiagram` for proper 2D routing (tests like `test_cyclic_fsm_shows_back_edges_section`, `test_branching_fsm_shows_branches_section`)

## Impact

- **Priority**: P3 — Visual quality issue in the primary loop inspection command
- **Effort**: Medium — Requires careful 2D grid math for edge routing with corner characters and label placement
- **Risk**: Low — Purely visual output, no behavioral impact
- **Breaking Change**: No — only changes `ll-loop show` text output format

## Labels

`bug`, `cli`, `ll-loop`

---

## Resolution

**Fixed** in `_render_2d_diagram()` by replacing text annotations with 2D routed lines:
- Main-to-main back-edges rendered as U-shaped routes with `▲`, `└───label───┘` box-drawing characters
- Off-path states rendered as proper Unicode boxes with vertical connectors (`│`, `▼`, `▲`) and labels
- Outgoing edges from off-path boxes drawn as labeled arrows on the box middle row
- Off-path box positioning changed from left-aligned to center-aligned under anchor state

Files modified:
- `scripts/little_loops/cli/loop/info.py` — rewrote edge routing in `_render_2d_diagram()`
- `scripts/tests/test_ll_loop_display.py` — strengthened assertions for 2D box rendering

## Status

**Resolved** | Created: 2026-02-19 | Resolved: 2026-02-19 | Priority: P3
