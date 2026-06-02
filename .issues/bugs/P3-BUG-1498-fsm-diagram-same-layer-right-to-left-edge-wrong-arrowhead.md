---
id: BUG-1498
type: BUG
priority: P3
status: done
captured_at: '2026-05-16T14:12:59Z'
completed_at: '2026-05-17T23:11:40Z'
discovered_date: '2026-05-16'
discovered_by: capture-issue
depends_on: ENH-839
decision_needed: false
confidence_score: 95
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Bug site**: `layout.py:1223` — `edge_text = "─" + label + "──▶"` is identical in both branches; the right-to-left branch needs `"◀──" + label + "─"` (`◀──label─`).
- **Placement issue**: the current loop uses `left_dashes = available - len(edge_text)` (right-alignment), which pushes `▶` toward `src_left`. The fix needs **left-alignment** (`left_dashes = 0`) so `◀` lands at `start = dst_right`, then trailing dashes fill `start + len(edge_text)` through `end - 1`.
- **Reference for correct `◀` usage**: `layout.py:1454` (forward skip-layer tip) uses `grid[dst_row][dst_right] = _lc("◀")` — a direct cell write. The same-layer renderer embeds the arrowhead in `edge_text`, so the string must be built in the opposite orientation rather than using a direct write.
- **`_box_occ` guard is already in place** at lines 1228–1240; no change needed there — the `pos not in _row_boxes` check already prevents box-boundary overwrites.

## Steps to Reproduce

1. `cd ~/AIProjects/ai-workspaces/blender-agents`
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

Follow the assertion pattern from `TestRenderFsmDiagram.test_branch_to_terminal_skip_layer_renders_edge` (line 1030):
```python
result = _render_fsm_diagram(fsm)
assert "◀" in result, f"Right-to-left same-layer edge should have ◀ arrowhead.\n{result}"
```
The existing test `test_same_layer_edge_does_not_occlude_intermediate_box` (line 1171) covers `_box_occ` occlusion but does **not** assert arrowhead direction — the new test is complementary.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py:1219-1240` — right-to-left branch in `_render_layered_diagram()`; change `edge_text` construction (line 1223) and flip to left-aligned placement

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:16-22` — imports and calls `_render_fsm_diagram()` for `ll-loop show`
- `scripts/little_loops/cli/loop/_helpers.py:408-410,427` — calls `_render_fsm_diagram()` for `ll-loop run --show-diagrams`

### Similar Patterns (Reference)
- `layout.py:1454` — `◀` (`◀`) placed correctly as a direct cell write for forward skip-layer tip (right margin)
- `layout.py:1336` — `▶` (`▶`) placed correctly as a direct cell write for back-edge tip (left margin)

### Tests
- `scripts/tests/test_ll_loop_display.py` — `TestRenderFsmDiagram` class (line 640)
  - `test_same_layer_edge_does_not_occlude_intermediate_box` (line 1171) — existing same-layer coverage, no direction assertion
  - New test to add (see Test Plan)
- `scripts/tests/test_ll_loop_commands.py` — `TestCmdShow.test_show_displays_diagram` (line 1289) — existing E2E coverage for `ll-loop show`; asserts section headers and state names only, no arrowhead direction; no update needed [Agent 3 finding, _wiring pass added by `/ll:wire-issue`_]

### Documentation
- `docs/reference/OUTPUT_STYLING.md` — documents FSM diagram rendering and glyph conventions; may need minor update if arrowhead conventions are described
  - _Wiring pass added by `/ll:wire-issue`:_ specifically the `### Edge arrows` section — add `◀──label─` as the right-to-left same-layer form, mirroring the existing `──label──▶` entry [Agent 2 finding]

## Implementation Steps

1. **Fix `edge_text` in `layout.py:1223`**: change `"─" + label + "──▶"` to `"◀──" + label + "─"` (i.e., `◀──label─`)
2. **Fix placement loop in `layout.py:1227-1240`**: remove `left_dashes` right-alignment; set `left_dashes = 0` so `◀` writes at `start = dst_right`; after writing `edge_text`, add a trailing-dashes pass from `start + len(edge_text)` to `end - 1` (mirroring the left-to-right branch's leading-dashes pass)
3. **Add test in `TestRenderFsmDiagram`** (`test_ll_loop_display.py`): 2-state same-layer fixture (`A.on_yes → B`, `B.on_yes → A`), assert `"◀" in result` and optionally that `▶` does not appear on the right-to-left row
4. **Verify** with `python -m pytest scripts/tests/test_ll_loop_display.py -v -k "same_layer"` and visually check `ll-loop show eval-specfile-gold` in the `blender-agents` workspace

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

## Resolution

Fixed in `scripts/little_loops/cli/loop/layout.py` (`_render_layered_diagram`, right-to-left branch):
- Changed `edge_text` from `"─label──▶"` to `"◄──label─"` (left-aligned, arrowhead at destination)
- Replaced right-aligned leading-dashes loop with left-aligned placement: writes `edge_text` at `start = dst_right`, then fills trailing dashes from `start + len(edge_text)` to `end - 1`
- Added regression test `test_same_layer_right_to_left_edge_has_correct_arrowhead` in `scripts/tests/test_ll_loop_display.py`
- Updated `test_branching_fsm_shows_branches_section` to accept `◄` as a valid arrowhead (the `fix → done` edge in that test is legitimately right-to-left)

## Session Log
- `/ll:manage-issue` - 2026-05-17T23:11:40Z
- `/ll:ready-issue` - 2026-05-17T23:06:29 - `d5ab478e-beb2-4a23-ad03-18f9718dcc6b.jsonl`
- `/ll:confidence-check` - 2026-05-17T23:30:00 - `4f8ebccd-978d-4ea8-82c6-c1e4e6f0e1e9.jsonl`
- `/ll:wire-issue` - 2026-05-17T23:03:02 - `07bcc90f-c1cb-4e31-a39c-5e5fad281c38.jsonl`
- `/ll:refine-issue` - 2026-05-17T22:58:00 - `81514626-4858-4e0f-b637-be7914aaeea1.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-17T18:46:34 - `ebf7abce-1ef1-46c8-8cbc-56d9f857d730.jsonl`
- `/ll:refine-issue` - 2026-05-17T14:48:54 - `70b5ac5f-6894-4bfd-9384-d9d089bceb7e.jsonl`
- `/ll:capture-issue` - 2026-05-16T14:12:59Z - `f204025d-307a-4f4d-80b2-206dfd3b1de1.jsonl`
