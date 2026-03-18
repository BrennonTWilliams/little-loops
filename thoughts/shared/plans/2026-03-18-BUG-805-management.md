# BUG-805 Implementation Plan: Move FSM Box Badge to First Content Row

**Date**: 2026-03-18
**Issue**: P3-BUG-805-fsm-box-badge-rendered-on-border-row-should-be-on-first-content-row
**File**: `scripts/little_loops/cli/loop/layout.py`

---

## Problem

Badges (`❯_`, `✦`, `↳⟳`, etc.) are overlaid on the top border row (`┌─…─┐`) by replacing `─`
characters. This makes them visually corrupt the box border. They should appear inside the box
on the first content row, right-aligned before the closing `│`.

## Root Cause

`_draw_box()` lines 541–553 overwrite `grid[row][pos]` (the top border row) with badge characters.
`_box_inner_lines()` explicitly excludes the badge (comment at line 118: "Badge is now rendered
in the top-right corner by _draw_box; name row is label only").

---

## Solution

### Phase 1: Write Tests (Red)

Add to `scripts/tests/test_ll_loop_display.py` class `TestStateBadges`:

1. `test_box_inner_lines_no_badge` — `_box_inner_lines(None, "init", False, 10)` returns `["init"]`
2. `test_box_inner_lines_with_badge` — `_box_inner_lines(None, "init", False, 10, "❯_")` returns
   name line with badge right-aligned: `"init    ❯_"` (ljust(7) + " " + "❯_")
3. `test_badge_on_content_row_not_border` — render FSM with a badged state; assert badge char
   is on a line containing `│`, NOT on a line containing only `┌`/`─`/`┐`
4. Update `test_diagram_contains_prompt_badge` comment (badge is now on content row, not top border)

### Phase 2: Implement

**Change 1: `_box_inner_lines()` (lines 106–144)**

Add `badge: str = ""` parameter. In the name line computation:
```python
if badge:
    badge_w = _badge_display_width(badge)
    available = inner_width - badge_w - 1
    if available > 0:
        name_line = display_label[:available].ljust(available) + " " + badge
    else:
        name_line = badge
else:
    name_line = display_label[:inner_width]
```
Update docstring and remove the "Badge is now rendered by _draw_box" comment.

**Change 2: `_compute_box_sizes()` (lines 464–508)**

Update `base_w` to fit both label AND badge on the same row:
```python
# Width must fit both: name label and badge on same content row
base_w = len(display_label[s]) + (1 + badge_w if badge else 0)
```
Pass `badge` to `_box_inner_lines()`:
```python
content = _box_inner_lines(state_obj, display_label[s], verbose, inner_w, badge)
```
Update comment on line 486.

**Change 3: `_draw_box()` (lines 511–595)**

Remove the badge overlay block (lines 541–553). Update docstring to remove reference to top-border
badge placement.

---

## Success Criteria

- [x] New tests fail against unmodified code (red phase)
- [x] All new tests pass after implementation
- [x] Full test suite passes (`python -m pytest scripts/tests/`)
- [x] Badge appears on first content row (`│` line) not on border row (`┌─…─┐` line)
- [x] Box width accounts for label + space + badge on content row
- [x] No regressions in existing diagram rendering tests
