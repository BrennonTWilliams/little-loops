---
discovered_date: 2026-03-18
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# ENH-807: FSM state box badge should appear in top border, not first content row

## Summary

State box badges (unicode characters indicating state type) are currently rendered inside the box on the first content row, right-aligned next to the state name. They should instead be embedded in the **top border line** of the box with one space of padding on each side, creating a visual gap between the badge and the corner characters:

```
┌──────────────── ✦ ┐
│ commit            │
│ /ll:commit        │
└───────────────────┘

┌─────────────── ❯_ ┐
│ check_commit      │
│mkdir -p .loops/tmp│
└───────────────────┘
```

This makes the badge a structural part of the box frame rather than content, which is visually cleaner and frees the first content row for the state name at full width.

## Motivation

The current placement puts the badge inline with the state name, compressing the available width for the label. Embedding the badge in the top border is a conventional UI pattern (similar to labeled box borders) that:

1. Makes the badge immediately visible as a box-level annotation, not data
2. Gives the state name its full row width
3. Creates a cleaner visual hierarchy — frame metadata vs box content

## Current Behavior

Badge is rendered in the top border, right-aligned with **no space padding** — placed immediately before the `┐` corner:

```
┌──────────────────✦┐
│ commit            │
│ /ll:commit        │
└───────────────────┘
```

`_box_inner_lines()` at line 121–122 already renders the name at full width (badge-free):

```python
# Badge is now rendered in the top-right corner by _draw_box; name row is label only
name_line = display_label[:inner_width]
```

`_draw_box()` at lines 544–556 overlays the badge directly before `┐` with no space:

```python
# Overlay badge in top-right corner (before ┐)
if badge:
    badge_w = _badge_display_width(badge)
    pos = col + width - 1 - badge_w  # immediately before ┐ — no space
    for ch in badge:
        ...
        grid[row][pos] = ch  # written without _bc() — not colorized on highlight
```

> **Note**: The "badge on content row" layout described in early versions of this issue was the post-BUG-805 state, which was reverted in commit `9d5c4ce`. The current code (after revert) already has the badge on the top border; the remaining gap is the missing space padding and missing `_bc()` colorization.

## Expected Behavior

Badge is embedded in the top border with one space gap on each side:

```
┌──────────────── ✦ ┐
│ commit            │
│ /ll:commit        │
└───────────────────┘
```

Top border rendering (in `_draw_box()`):

```
┌ [─ × N] [ ] [badge] [ ] ┐
```

Where N = `inner_width - badge_display_width - 2` (the two spaces).

## Implementation Steps

1. **Modify `_draw_box()` to add space padding** (`layout.py:544–556`):
   - Shift badge position left by 1: `pos = col + width - 1 - badge_w - 1` (one space before `┐`)
   - Write a space character at `col + width - 2` (the cell between badge end and `┐`) — or rely on the existing `─` cell; to get an actual space (not `─`), explicitly write `" "` there
   - Wrap each badge character write with `_bc()` for highlighted colorization:
     `grid[row][pos] = _bc(ch)` instead of `grid[row][pos] = ch`
   - Update docstring: change "immediately before the ┐ corner character" to "with one space of padding on each side"

2. **Steps 2 already done** — `_box_inner_lines()` at line 118–119 already renders the full-width name with no badge. No change needed.

3. **Update `_compute_box_sizes()` width accounting** (`layout.py:490`):
   - Currently (`layout.py:490`): `base_w = max(len(display_label[s]), badge_w)`
   - Change to: `base_w = max(len(display_label[s]), badge_w + 2)`
   - The `+2` reserves space for the two padding spaces (` badge `) in the top border
   - Update comment on line 489 accordingly

4. **Apply `_bc()` to badge in border** — handled in step 1 above. Currently the badge characters bypass `_bc()` and are never colorized even when the state is highlighted.

5. **Update tests** in `scripts/tests/test_ll_loop_display.py`:
   - `TestStateBadges.test_diagram_contains_prompt_badge` (line 1723): currently only checks `"\u2726" in result` (presence). Add a check that the badge is surrounded by spaces on the top border row, e.g.:
     ```python
     top_border = next(ln for ln in result.split("\n") if "\u250c" in ln)
     assert " \u2726 " in top_border  # space padding on each side
     ```
   - Add test: box width correct when badge is wider than state name (badge_w + 2 > label_w)
   - Add test: highlighted state colorizes badge (use `patch.object(output_mod, "_USE_COLOR", True)` pattern from line ~1212)

## Scope Boundaries

Out of scope:
- Route badge (`_ROUTE_BADGE`) space-padding — that is a follow-on from BUG-806; once this fix lands, the route badge will benefit automatically since it goes through the same `_draw_box()` path
- Any changes to FSM logic, state transitions, or non-rendering code
- Changing the badge character set or which states receive badges
- Verbose/compact mode behavior differences (both use `_draw_box()` unchanged)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py`
  - `_draw_box()` (lines 514–595+, badge overlay at 544–556) — add space padding + `_bc()` colorization
  - `_compute_box_sizes()` (lines 467–511, width calc at 490) — change `badge_w` to `badge_w + 2`
  - **`_box_inner_lines()` does NOT need changes** — badge already absent from content row (line 118–119)

### Dependent Files (Call Sites)
- `layout.py:946` (`_render_layered_diagram`) — calls `_draw_box(..., badge=box_badge[sname])`; no change needed
- `layout.py:1521` (`_render_horizontal_simple`) — calls `_draw_box(..., badge=box_badge[sname])`; no change needed

### Similar Patterns
- `info.py:596–674` — uses `─ {label} ─` pattern (plain strings) for separator lines with embedded text; same visual convention, different implementation (no grid)
- BUG-806: `_ROUTE_BADGE` addition — route badge will also benefit from this fix once badge is in the border with space padding

### Tests
- `scripts/tests/test_ll_loop_display.py`
  - `TestStateBadges` class (line 1683) — update `test_diagram_contains_prompt_badge` (line 1723) to verify space-padded border placement
  - Color test pattern: use `patch.object(output_mod, "_USE_COLOR", True)` (lines ~1212–1263 for reference)
  - Box-line pattern: `next(ln for ln in result.split("\n") if "\u250c" in ln)` to get top border line

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified line numbers and actual current code state:_

- `_badge_display_width()`: `layout.py:83–86`
- `_get_state_badge()`: `layout.py:89–99`
- `_box_inner_lines()` (badge-absent name row): `layout.py:109–144`, specifically line 121–122
- `_compute_box_sizes()` (badge-aware width): `layout.py:467–511`, specifically line 490
- `_draw_box()` top border draw: `layout.py:535–542`
- `_draw_box()` badge overlay (no spaces, no `_bc()`): `layout.py:544–556`
- `_bc()` closure: `layout.py:532–533`
- Both `_draw_box()` call sites already pass `badge=box_badge[sname]`; no call-site changes needed
- `TestStateBadges.test_diagram_contains_prompt_badge`: `test_ll_loop_display.py:1723` — only checks presence, not space-padded border placement

## Impact

- **Priority**: P3 — visual polish; does not affect functionality or data
- **Effort**: Small-Medium — three function edits + test updates
- **Risk**: Low — isolated to box rendering; no FSM logic changes
- **Breaking Change**: No (visual output change only)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `rendering`, `fsm-diagram`, `captured`

## Resolution

**Status**: Completed 2026-03-18

### Changes Made

- `scripts/little_loops/cli/loop/layout.py`
  - `_compute_box_sizes()`: Changed `base_w = max(len(display_label[s]), badge_w)` to `max(len(display_label[s]), badge_w + 2 if badge_w else 0)` to reserve space for both padding spaces
  - `_draw_box()`: Shifted badge position left by 1, added explicit leading space (`_bc(" ")`) and trailing space (`_bc(" ")`), wrapped badge character writes with `_bc()` for highlight colorization; updated docstring
- `scripts/tests/test_ll_loop_display.py`
  - Updated `test_diagram_contains_prompt_badge` to assert `" ✦ "` in the top border line
  - Added `test_badge_border_width_accounts_for_padding` — wide badge on short label renders correctly
  - Added `test_highlighted_badge_is_colorized` — badge uses highlight color when state is highlighted

### Verification

- All 3703 tests pass (`python -m pytest scripts/tests/`)
- `ruff check scripts/` clean
- `python -m mypy scripts/little_loops/cli/loop/layout.py` — only pre-existing wcwidth stub warning

## Session Log
- `/ll:ready-issue` - 2026-03-18T22:41:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7c9e65b-b14e-49db-a2dd-f906380c418c.jsonl`
- `/ll:refine-issue` - 2026-03-18T22:36:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b466204-2c32-4956-a07d-e0d2c0840e7e.jsonl`
- `/ll:confidence-check` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9dd6b13-1607-4caf-b3d5-461e82aa833e.jsonl`

- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

**Completed** | Created: 2026-03-18 | Completed: 2026-03-18 | Priority: P3
