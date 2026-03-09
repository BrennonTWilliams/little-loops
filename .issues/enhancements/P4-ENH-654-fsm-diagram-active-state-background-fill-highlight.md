---
id: ENH-654
type: ENH
priority: P4
status: active
discovered_date: 2026-03-08
discovered_by: capture-issue
---

# ENH-654: FSM Diagram Active State Background Fill Highlight

## Summary

Enhance `ll-loop run --show-diagrams` so the active state box uses a background fill color in addition to (or instead of) the current border-only coloring, making the active state visually pop more clearly in the terminal diagram.

## Motivation

The current highlighting — colored border + bold state name — is subtle. A filled background (ANSI bg color applied to all interior cells) makes the active state unmistakably obvious at a glance, especially in complex FSMs with many states. This is purely a visual polish change with no functional impact.

## Current Behavior

When `ll-loop run --show-diagrams` renders the FSM diagram, the active state box is highlighted with:
- Colored `┌─┐│└┘` border characters (foreground color, e.g. green)
- Bold + colored state name text

Interior cells (spaces) remain the terminal's default background.

## Expected Behavior

The active state box renders with:
- All interior cells filled with the highlight background color (ANSI bg code, e.g. `42` for green)
- State name and content text rendered with a contrasting dark foreground (`30`) over the colored background
- Border characters retain their colored appearance (or also receive the bg color)

## Scope Boundaries

Changes are isolated to `scripts/little_loops/cli/loop/info.py`, in the `_render_2d_diagram()` function:

- **Main-path box rendering** (main highlighted-box block in `_render_2d_diagram()`): add a fill pass over interior cells for highlighted boxes
- **Off-path box rendering** (off-path block in `_render_2d_diagram()`): same fill pass (currently no highlighting at all — see ENH-638 for border fix first)

No config schema changes are strictly required if `highlight_color` is automatically converted from fg→bg (e.g., `"32"` → `"42"`). A separate `highlight_bg_color` config field could be added to `config-schema.json` for explicit control.

## Implementation Steps

1. **Read `_render_2d_diagram()` in `info.py`** to understand the grid model (`rows` / `off_grid` lists of `[" "] * total_width`)
2. **Add fill pass for main-path highlighted box**: after placing border chars, iterate every interior cell `(cx+1)..(cx+bw-2)` for all content and padding rows, setting each to `colorize(" ", bg_code)` where `bg_code = str(int(highlight_color) + 10)` (converts fg→bg for standard ANSI codes)
3. **Update content rendering**: for highlighted boxes, wrap each content char as `colorize(ch, f"30;{bg_code}")` (dark fg + colored bg) instead of just placing the raw char
4. **Apply same fill pass to off-path box rendering** (after ENH-638 adds off-path border highlighting)
5. **Handle edge case**: the `colored_line` trick in the main-path highlighted-box block of `_render_2d_diagram()` (where a single long colored string is stored at `rows[r][cx+2]` and subsequent cells set to `""`) must still work with the fill — ensure empty-string cells don't overwrite the bg-colored spaces placed in the fill pass
6. **Verify with `ll-loop run issue-refinement --show-diagrams`** that the active state box visually fills with color

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `_render_2d_diagram()`, main-path highlighted-box block and off-path block

### Dependent Files (Callers/Importers)
- N/A — `_render_2d_diagram()` is called internally by the `ll-loop run --show-diagrams` rendering path; no external callers import this function

### Similar Patterns
- `scripts/little_loops/cli/loop/info.py` — existing border-highlighting code (`colorize()` calls on border chars in the main-path block) is the pattern to extend with bg fill

### Tests
- `scripts/tests/test_fsm_executor.py` — run after changes to confirm no regressions
- `scripts/tests/test_sprint_integration.py` — run after changes to confirm no regressions
- No dedicated diagram rendering tests exist; verify visually with `ll-loop run issue-refinement --show-diagrams`

### Documentation
- N/A — internal rendering change; no user-facing docs reference active state fill styling

### Configuration
- `config-schema.json` — optionally add `highlight_bg_color` field alongside `highlight_color` for explicit bg color control; if not added, derive bg from fg automatically

### Issue Dependencies
- **ENH-638** (fix off-path border highlighting) should be implemented first; this issue extends that fix with fill behavior

## Acceptance Criteria

- [ ] Active state box in main-path has background-filled interior cells in the highlight color
- [ ] State name and content text render with contrasting dark foreground over colored background
- [ ] Non-highlighted boxes are unaffected
- [ ] Off-path active state box also fills (after ENH-638 is merged)
- [ ] `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_sprint_integration.py -v` passes

## Impact

- **Priority**: P4 — visual polish only; no functional change
- **Effort**: Small-Medium — ~40–60 lines of change; requires understanding the grid rendering model and the empty-string cell trick
- **Risk**: Low — isolated to diagram rendering; no data or state logic touched
- **Breaking Change**: No

## Related

- ENH-638: Fix off-path state highlighting (border only — prerequisite)
- FEAT-637: Initial active state box highlighting (completed)

## Labels

`enhancement`, `ux`, `ll-loop`, `diagrams`, `terminal`

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb1dacf-d3dc-4461-88d7-450e60c8640a.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5a9e18cb-659a-48f7-9438-2e4c4fdddd25.jsonl`

## Status

**Open** | Created: 2026-03-08 | Priority: P4
