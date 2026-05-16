---
id: BUG-1498
type: BUG
priority: P3
status: open
captured_at: "2026-05-16T14:12:59Z"
discovered_date: "2026-05-16"
discovered_by: capture-issue
---

# BUG-1498: FSM diagram same-layer right-to-left edge draws wrong arrowhead

## Summary

In `_render_layered_diagram` (`scripts/little_loops/cli/loop/layout.py`), same-layer edges where the destination sits left of the source are rendered with a `▶` arrowhead pointing at the *source* instead of `◀` pointing at the destination. Observed in the `eval-specfile-gold` loop diagram on the `failed.on_yes → loop_complete_final` edge.

## Current Behavior

Line 37 of the rendered diagram shows:

```
│ loop_complete_final ◉ │◀──yes──▶│ failed │
```

The edge `failed.on_yes → loop_complete_final` runs right-to-left, but the rendered `▶` glyph points back at `failed` (the source). A stray `◀` also appears next to `loop_complete_final`, likely from connector overdraw on the same row.

## Expected Behavior

Right-to-left same-layer edges should render as `dst ◀──label── src` (the form already documented in the docstring comment at `layout.py:1199`). No spurious arrow glyphs should appear at the destination box boundary.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: `_render_layered_diagram` — same-layer edge branch around `layout.py:1198-1219` (the `elif dst_right <= src_left:` block).
- **Cause**: Both directional branches use the same hard-coded `edge_text = "─" + label + "──▶"` (line 1180 *and* line 1202). The right-to-left branch needs the mirrored form, and the placement loop derives `left_dashes` from the right edge rather than starting at `start` and filling toward `end`.

## Proposed Solution

In the `elif dst_right <= src_left:` branch:

1. Build `edge_text` as `"◀──" + label + "─"` (mirrored form).
2. Rewrite the placement loop in `layout.py:1206-1219` to place `◀` at `start` (adjacent to `dst_right`) and fill dashes toward `end`.
3. Continue to honor `_box_occ` exclusions on the cell-write loop so box-boundary columns are not overwritten.
4. If the stray `◀` next to `loop_complete_final` persists after the directional fix and BUG-1499 lands, audit the cell-overwrite logic in `_box_occ` to skip the box-boundary column on this code path.

## Steps to Reproduce

1. `cd /Users/brennon/AIProjects/ai-workspaces/blender-agents`
2. `ll-loop show eval-specfile-gold`
3. Inspect the `failed` / `loop_complete_final` row — observe the wrong-direction `▶` arrow.

A reduced reproduction can also be built as a unit case in `scripts/tests/test_ll_loop_display.py` with two states on the same layer and one right-to-left transition.

## Impact

- **Severity**: Low–medium (visual only; misleads readers about edge direction).
- **Affects**: Any FSM with same-layer edges whose destination is left of the source. Becomes more likely on wide loops with siblings on the same layer.
- **Workaround**: None at render time; readers must consult the YAML to confirm direction.

## Test Plan

Add a case in `scripts/tests/test_ll_loop_display.py`:

- Fixture: 2-state FSM with `A.on_yes → B` and `B.on_yes → A`, placed on the same layer.
- Assert the rendered line containing the right-to-left edge includes `◀` adjacent to the destination and contains no `▶`.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/cli/loop/layout.py` | Renderer under repair |
| `~/.claude/plans/investigate-the-fsm-loop-twinkly-bear.md` | Source investigation plan (Bug A) |

## Labels

- area:fsm-diagram
- area:renderer

## Status

- **Discovered**: 2026-05-16 via investigation plan against `eval-specfile-gold`
- **Captured by**: `/ll:capture-issue`

## Session Log
- `/ll:capture-issue` - 2026-05-16T14:12:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f204025d-307a-4f4d-80b2-206dfd3b1de1.jsonl`
