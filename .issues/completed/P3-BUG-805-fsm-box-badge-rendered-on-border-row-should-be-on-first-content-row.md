---
discovered_date: 2026-03-18
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 86
---

# BUG-805: FSM box badge rendered on border row should be on first content row

## Summary

After ENH-732 introduced unicode composition badges, the badges (e.g., `❯_`, `✦`, `↳⟳`) are placed in the top border row of state boxes, replacing `─` characters. This makes the badge visually overlap or cross through the box border line rather than appearing inside the box. Badges should be rendered one row lower — on the first content row — so they appear cleanly inside the box without disturbing the border.

## Current Behavior

Badges are overlaid on the top border row (`grid[row]`) by `_draw_box()`, replacing `─` border characters:

```
┌────────────────────────────────────────❯_┐
│ → init                                   │
│ mkdir -p .loops/tmp && rm -f .loops/tmp… │
└──────────────────────────────────────────┘
```

The badge glyphs (`❯_`) appear embedded in the `┌─────┐` line, visually crossing the box border.

## Expected Behavior

Badges should appear on the first content row (inside the box), right-aligned before the `│` border character:

```
┌──────────────────────────────────────────┐
│ → init                                ❯_ │
│ mkdir -p .loops/tmp && rm -f .loops/tmp… │
└──────────────────────────────────────────┘
```

## Motivation

The border-placement approach was a visual shortcut that looks broken in terminal output — the badge glyphs replace `─` characters and appear to "cut through" the box outline. Moving badges to the first content row makes them clearly inside the box and doesn't corrupt the border drawing.

## Steps to Reproduce

1. Run `ll-loop show` or render any FSM loop that has shell/prompt/mcp states
2. Observe the top border row of any state box with a badge
3. Observe that `❯_`, `✦`, etc. appear in the `┌─────┐` line, not inside the box

## Proposed Solution

In `_draw_box()` (`layout.py`), move badge rendering from the top border row to the first content row:

- Remove the "Overlay badge in top-right corner" block (lines ~541–553)
- Instead, in the content rows loop (line ~556), when `i == 0` and `badge` is set, right-align the badge on row `r = row + 1` before the closing `│`

Alternatively, render the badge in `_box_inner_lines()` by appending it right-aligned on the name line:

```python
# In _box_inner_lines(), replace:
name_line = display_label[:inner_width]
# With:
if badge:
    badge_w = _badge_display_width(badge)
    available = inner_width - badge_w - 1  # 1 space separator
    name_line = display_label[:available].ljust(available) + " " + badge
else:
    name_line = display_label[:inner_width]
```

This approach keeps badge logic inside `_box_inner_lines()` and removes the need for the overlay hack in `_draw_box()`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — `_draw_box()` (remove border overlay), `_box_inner_lines()` (add badge to name row)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/layout.py` — callers of `_draw_box()`: `_render_layered_diagram()` (~line 934), `_render_horizontal_simple()` (~line 1509)
- `scripts/little_loops/cli/loop/_helpers.py` — uses layout module

### Similar Patterns
- ENH-732 completion in `.issues/completed/P4-ENH-732-replace-fsm-state-box-badges-with-unicode-compositions.md` for original badge placement context

### Tests
- `scripts/tests/` — search for FSM layout/diagram tests to update expected output snapshots

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Move badge rendering from `_draw_box()` top border into `_box_inner_lines()` name row
2. Update `_draw_box()` signature/callers if badge param changes (or pass through unchanged)
3. Verify box width computation in `_compute_box_sizes()` still accounts for badge width on content row
4. Run existing tests and update any snapshot expectations for box rendering

## Impact

- **Priority**: P3 — visual bug, not functional; affects all state boxes with badges
- **Effort**: Small — confined to `_draw_box()` / `_box_inner_lines()` interaction
- **Risk**: Low — rendering-only change, no logic paths affected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Resolution

- Moved badge rendering from `_draw_box()` border overlay to `_box_inner_lines()` name row
- `_box_inner_lines()` now accepts `badge` param and right-aligns it on the name line
- `_compute_box_sizes()` updated `base_w` to `len(label) + 1 + badge_w` so box fits both
- Removed `_draw_box()` border overlay block (lines 541-553) and unused `_wcwidth` import
- Added 4 new tests: `test_box_inner_lines_*` and `test_badge_on_content_row_not_border_row`

## Labels

`bug`, `rendering`, `fsm-diagram`, `resolved`

## Session Log
- `/ll:ready-issue` - 2026-03-18T22:10:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed383bd6-0956-4dcb-8bad-a0f7df6066fc.jsonl`

- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/18f420b1-0c39-4794-9ebd-f0386a21c8dd.jsonl`
- `/ll:confidence-check` - 2026-03-18T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9957234-b252-4dee-a7f0-8db37b7c163b.jsonl`
- `/ll:manage-issue` - 2026-03-18T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

**Resolved** | Created: 2026-03-18 | Completed: 2026-03-18 | Priority: P3
