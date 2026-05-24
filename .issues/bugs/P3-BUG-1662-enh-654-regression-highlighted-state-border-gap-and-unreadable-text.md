---
id: BUG-1662
type: BUG
priority: P3
status: open
captured_at: "2026-05-24T04:15:48Z"
discovered_date: 2026-05-24
discovered_by: capture-issue
relates_to:
  - ENH-654
testable: true
---

# BUG-1662: ENH-654 Regression — Highlighted State Box Has Border Gap and Unreadable Text

## Summary

ENH-654 added a background-fill highlight to the active state box in `ll-loop run --show-diagrams`, but introduced two visible rendering defects: (1) a visible gap between border glyphs and the interior fill because borders are colorized fg-only while cells are fill-only, and (2) unreadable text because the name row and content chars use ANSI `30` (black) as foreground over the fill color, which is illegible on dark terminal themes.

## Root Cause

**File:** `scripts/little_loops/cli/loop/layout.py`

1. **Border gap** — `_draw_box()._bc()` closure (~line 603) applies `highlight_color` to border glyphs as fg-only (`\033[32m│\033[0m`), while interior cells receive the bg fill (`\033[42m \033[0m`). The cell behind each border glyph remains at the terminal default background, producing a visible discontinuity: `[default-bg │] [bg-fill ] [bg-fill name] [bg-fill ] [default-bg │]`.

2. **Poor contrast** — The name row (~line 657) and content chars (~line 675) in `_draw_box()` use `f"30;{bg_code};1"` / `f"30;{bg_code}"` — ANSI black (`30`) on the fill. On dark terminal themes where ANSI green (`42`) renders as deep saturated green, black-on-fill is illegible. The same defect exists in `_render_neighborhood_diagram()._make_box()` (~line 1784).

## Steps to Reproduce

```bash
ll-loop run <any-loop-with-3+-states> --show-diagrams
```

Observe the active (highlighted) state box: border glyphs sit on a different background than the interior, and the state name is difficult or impossible to read on dark terminal themes.

## Expected Behavior

- Every border glyph (`┌ ─ ┐ │ └ ┘`) emits `\033[32;42m│\033[0m` (fg+bg compound), so the fill is seamless from edge to edge.
- State name and content lines use bright white (`97`) over the fill for universal legibility on both light and dark terminal themes.

## Fix

### 1. Close the gap — borders carry the bg fill when highlighted

In `_draw_box()._bc()` (~line 603), compose fg+bg when `is_highlighted` and `bg_code` are truthy:

```python
def _bc(ch: str) -> str:
    if not is_highlighted:
        return ch
    if bg_code:
        return colorize(ch, f"{highlight_color};{bg_code}")
    return colorize(ch, highlight_color)
```

Mirror in `_render_neighborhood_diagram()._make_box()` (~lines 1777–1795):

```python
border_code = f"{highlight_color};{nd_bg_code}" if nd_bg_code else highlight_color
top = colorize(top, border_code)
bot = colorize(bot, border_code)
mid = (
    colorize("│", border_code)
    + colorize(" ", nd_bg_code)
    + colorize(padded, f"97;{nd_bg_code};1")
    + colorize(" ", nd_bg_code)
    + colorize("│", border_code)
)
```

### 2. High-contrast text — switch `30` → `97`

- `_draw_box()` name row (~line 657): `f"30;{bg_code};1"` → `f"97;{bg_code};1"`
- `_draw_box()` content chars (~line 675): `f"30;{bg_code}"` → `f"97;{bg_code}"`
- `_make_box()` name (~line 1784): `f"30;{nd_bg_code};1"` → `f"97;{nd_bg_code};1"`

The `bg_code is None` fallback paths are unchanged — those render text in `highlight_color` directly without a fill.

### 3. Update tests

In `scripts/tests/test_ll_loop_display.py`:

- `test_highlighted_state_uses_configured_color` (line 1256):
  - `assert "\033[36m" in result` → `assert "\033[36;46m" in result`
  - `assert "\033[30;46;1m" in result` → `assert "\033[97;46;1m" in result`
- `test_highlighted_state_default_green` (line 1277):
  - `assert "\033[32m" in result` → `assert "\033[32;42m" in result`
- `test_highlighted_badge_is_colorized` (line 2817):
  - `assert "\033[36m✦" in result` → `assert "\033[36;46m✦" in result`
- `test_highlighted_active_state_uses_bg_fill` (line 3608):
  - `assert "\x1b[30;46;1m" in out` → `assert "\x1b[97;46;1m" in out`

### 4. Update docs

`docs/reference/OUTPUT_STYLING.md` line 240 — replace the "contrasting dark foreground (`30`)" sentence with "bright white foreground (`97`)" and note that border chars are also filled (`\033[32;42m│`), eliminating the visible gap.

## Verification

```bash
python -m pytest scripts/tests/test_ll_loop_display.py -v
python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_sprint_integration.py -v
ll-loop run <loop> --show-diagrams   # confirm no gap, readable text
```

Also confirm `_render_cluster_diagram` in `scripts/little_loops/cli/issues/clusters.py:137` is unaffected (it calls `_draw_box(..., is_highlighted=False, ...)`).

## Affected Files

- `scripts/little_loops/cli/loop/layout.py` — `_bc()` (~line 603), name/content codes (~lines 657, 675), `_make_box()` (~lines 1777–1795)
- `scripts/tests/test_ll_loop_display.py` — four test assertions
- `docs/reference/OUTPUT_STYLING.md` — line 240

---

## Session Log
- `/ll:capture-issue` - 2026-05-24T04:15:48Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/deae5e40-09d5-4d75-a993-bc876564ab27.jsonl`
