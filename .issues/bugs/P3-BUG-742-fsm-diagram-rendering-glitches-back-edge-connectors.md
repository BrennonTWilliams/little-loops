---
id: BUG-742
type: BUG
priority: P3
status: completed
discovered_date: 2026-03-14
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
---

# BUG-742: FSM diagram rendering glitches — back-edge connectors corrupt boxes and produce disconnected junctions

## Summary

Two distinct rendering bugs in `scripts/little_loops/cli/loop/layout.py` (`_render_layered_diagram`) caused visual glitches in `ll-loop s issue-refinement`. Back-edge horizontal connectors overwrote intermediate state box content, and multi-destination pipe junctions used disconnected `│` instead of `├`/`┤`.

## Bug 1: State boxes disrupted by back-edge horizontal connectors

### Root Cause

Back-edge horizontal connectors (src connector and dst connector loops) drew `─` lines from the left margin to the source/destination box boundary by iterating over all columns in that range with no `_box_occ` check. When an intermediate state box sat between the margin and the target on the same row, the connector overwrote its cells:

- Box left border `│` → `┼`
- Box content characters → `─`
- Box right border `│` → `┼`

The source/destination boxes were unaffected because the loop stopped at `col_start[src/dst]`. Only intermediate boxes had no protection.

**Visible symptom:**
```
│ │ └─────next───┼─format_issues──[prompt]──────────┼──────│ route_score │─...
```
`format_issues` box content row was overwritten; its border chars became `┼`.

### Fix

Added `_box_occ` guards to both connector loops so columns occupied by any box are skipped, making the `─` line appear to pass behind intermediate boxes:

```python
# src connector
_src_row_boxes = _box_occ.get(src_row, set())
for c in range(col + 1, src_left):
    if c < total_width and c not in _src_row_boxes:
        ...

# dst connector
_dst_row_boxes = _box_occ.get(dst_row, set())
for c in range(col + 1, dst_left):
    if c < total_width and c not in _dst_row_boxes:
        ...
```

## Bug 2: Disconnected `│─` and `─│` junction characters

### Root Cause

The post-pass that fills `─` between two destination pipe columns at `arrow_start_row` operated on `range(left + 1, right)` — exclusive of both endpoints. When both pipe positions contained `│` (pipes starting directly below the source box), the horizontal bar was drawn between them but the boundary positions were never updated:

- Position `left`: `│` stayed `│`, but the bar exited to its right → should be `├`
- Position `right`: `│` stayed `│`, but the bar arrived from its left → should be `┤`

**Visible symptom:**
```
│─success/error──────────────│ fail
```

### Fix

Added boundary updates immediately after the `for c in range(left + 1, right)` loop:

```python
if 0 <= left < total_width and grid[arrow_start_row][left] == "\u2502":  # │ → ├
    grid[arrow_start_row][left] = "\u251c"
if 0 <= right < total_width and grid[arrow_start_row][right] == "\u2502":  # │ → ┤
    grid[arrow_start_row][right] = "\u2524"
```

Only the `│` case is handled — corner chars (`┌`, `┐`, `┬`) already represent the correct direction.

**After fix:**
```
├─success/error──────────────┤ fail
```

## Verification

```
ll-loop s issue-refinement
```

- `format_issues` box shows correct `│ format_issues  [prompt]          │` — no `┼` corruption.
- `├─success/error──────────────┤ fail` — proper junction chars on both sides.

## Files Changed

- `scripts/little_loops/cli/loop/layout.py` — `_render_layered_diagram`:
  - Lines ~994–1011: post-pass block — added `├`/`┤` boundary updates after horizontal-fill loop
  - Lines ~1116–1135: src connector loop — added `_src_row_boxes` guard
  - Lines ~1137–1153: dst connector loop — added `_dst_row_boxes` guard
