---
discovered_date: 2026-03-18
discovered_by: capture-issue
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

Badge is right-aligned on the first content row inside the box:

```
┌───────────────────┐
│ commit          ✦ │
│ /ll:commit        │
└───────────────────┘
```

Implemented in `_box_inner_lines()` (~line 118):

```python
if badge:
    badge_w = _badge_display_width(badge)
    available = inner_width - badge_w - 1  # 1 space separator
    if available > 0:
        name_line = display_label[:available].ljust(available) + " " + badge
    else:
        name_line = badge
```

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

1. **Modify `_draw_box()`** to render the badge in the top border:
   - Replace the plain `─` fill with: `─ × fill_count` + ` ` + badge + ` ` before the closing `┐`
   - `fill_count = inner_width - badge_display_width(badge) - 2`
   - The badge parameter is already passed to `_draw_box()` (currently unused beyond API compat)

2. **Modify `_box_inner_lines()`** to stop placing the badge:
   - Remove the `if badge:` branch that right-aligns badge on the name line
   - Always use `name_line = display_label[:inner_width]` (full width available)

3. **Update `_compute_box_sizes()`** to adjust minimum width accounting:
   - Currently: `base_w = len(display_label) + (1 + badge_w if badge else 0)`
   - New: `base_w = max(len(display_label), badge_w + 2)` — the border must be wide enough for `" badge "` but the content row no longer needs extra width for it
   - The minimum box width must satisfy both: `len(display_label)` for content, and `badge_w + 4` for the border (2 spaces + 2 corner chars)

4. **Handle highlighted state coloring** in `_draw_box()`:
   - The badge in the border should use the same `_bc()` colorization as the border characters when the state is highlighted

5. **Update/add tests** in `scripts/tests/` for:
   - Badge appears in top border string, not in content row
   - Box width is correct when badge is wider than state name
   - Highlighted state colors the badge correctly

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py`
  - `_draw_box()` (~line 518) — top border rendering
  - `_box_inner_lines()` (~line 105) — remove badge from content row
  - `_compute_box_sizes()` (~line 471) — adjust minimum width logic

### Dependent Files
- `scripts/little_loops/cli/loop/layout.py` — all callers of `_draw_box()` already pass `badge=box_badge[sname]`; no call-site changes needed

### Similar Patterns
- BUG-806: `_ROUTE_BADGE` addition — route badge will also benefit from this fix
- ENH-732: original badge introduction (referenced in BUG-806)

### Tests
- `scripts/tests/test_ll_loop_display.py` — existing FSM layout tests; add/update snapshot expectations

## Impact

- **Priority**: P3 — visual polish; does not affect functionality or data
- **Effort**: Small-Medium — three function edits + test updates
- **Risk**: Low — isolated to box rendering; no FSM logic changes
- **Breaking Change**: No (visual output change only)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `rendering`, `fsm-diagram`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

**Open** | Created: 2026-03-18 | Priority: P3
