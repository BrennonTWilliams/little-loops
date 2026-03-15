---
id: ENH-654
type: ENH
priority: P4
status: active
discovered_date: 2026-03-08
discovered_by: capture-issue
confidence_score: 85
outcome_confidence: 78
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

1. **Read `_render_2d_diagram()` in `info.py:463-964`** to understand the grid model (`rows`/`off_grid` are `list[list[str]]` initialized to `[" "] * total_width`)
2. **Compute `bg_code` safely** — add a helper near line 601 (before the main-path loop):
   ```python
   # fg→bg: works for simple codes 30-37 and 90-97; guard against compound codes like "38;5;208"
   try:
       bg_code = str(int(highlight_color) + 10)
   except ValueError:
       bg_code = None  # compound code — skip bg fill
   ```
3. **Add fill pass for main-path highlighted box** (`info.py:601-644`): when `is_highlighted and bg_code`:
   - After writing border chars, add a pre-fill pass over all content + padding rows: iterate columns `cx+1` through `cx+w-2` (inclusive), setting each to `colorize(" ", bg_code)` — this covers interior padding
   - The fill pass must run **before** the content/colored_line writes so that subsequent char writes overwrite the spaces correctly
4. **Update content rendering for highlighted boxes** (`info.py:618-632`): for `i == 0` (colored_line trick at line 622-628), change to `colorize(line, f"30;{bg_code};1")` (dark fg + bg + bold); for `i > 0` content chars (plain assignment at 629-632), wrap as `colorize(ch, f"30;{bg_code}")`
5. **Handle `colored_line` trick compatibility**: the empty-string cells (`""`) at `cx+3..cx+2+len(line)-1` are placed **after** the fill pass, so they replace the bg-colored spaces — this is intentional; the ANSI sequence at `cx+2` includes its own bg code, so the output is correct when joined
6. **Apply same fill pass to off-path block** (`info.py:889-928`): mirror the fill pass using `off_grid` and `bx`/`bw`; **do not** fill `bx+1` with bg color (that cell is restored to `" "` at the `off_grid[br][bx + 1] = " "` line ~909 for arrow continuity)
7. **Add test assertions** in `scripts/tests/test_ll_loop_display.py:928-977`: assert `"\033[42m "` (or `f"\033[{bg_code}m "`) appears in the result for the highlighted state's interior rows
8. **Verify visually** with `ll-loop run issue-refinement --show-diagrams`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `_render_2d_diagram()`, main-path highlighted-box block and off-path block

### Dependent Files (Callers/Importers)
- N/A — `_render_2d_diagram()` is called internally by the `ll-loop run --show-diagrams` rendering path; no external callers import this function

_Codebase Research: full call chain with line refs:_
- `scripts/little_loops/cli/loop/run.py:125-126` — reads `highlight_color` from config, calls `run_foreground()`
- `scripts/little_loops/cli/loop/_helpers.py:283-323` — `run_foreground()` subscribes to `state_enter` events; calls `_render_fsm_diagram(fsm, highlight_state=state, highlight_color=highlight_color)` at line `322-323`
- `scripts/little_loops/cli/loop/info.py:358-460` — `_render_fsm_diagram()` delegates to `_render_2d_diagram()` at line `458-459`
- `scripts/little_loops/cli/loop/info.py:463-964` — `_render_2d_diagram()` — all box rendering

### Similar Patterns
- `scripts/little_loops/cli/loop/info.py:601-644` — **main-path highlighted-box block**: `_bc()` helper closure (line 607-609), border chars colorized individually, first content row uses the `colored_line` trick (lines 622-628) where one ANSI string is stored at `rows[r][cx+2]` and subsequent cells set to `""`
- `scripts/little_loops/cli/loop/info.py:889-928` — **off-path highlighted-box block**: mirrors main-path exactly using `_bc_off()` and `off_grid`; note line `off_grid[br][bx + 1] = " "` (restores space overwritten by connector arrows — important: fill pass must not overwrite this cell for `bx+1`)
- `scripts/little_loops/cli/output.py:89-93` — `colorize(text, code)` definition: accepts any ANSI SGR string, wraps with `\033[{code}m...\033[0m`

### Tests
- `scripts/tests/test_ll_loop_display.py:928-977` — **primary diagram rendering tests** (missed in original issue): covers `_render_fsm_diagram` with `highlight_color` assertions; patches `output_mod._USE_COLOR = True`; asserts `"\033[36m"` in result (border) and `"\033[36;1m"` (bold name) — **new bg fill assertions should be added here**
- `scripts/tests/test_cli_output.py:58-64` — `colorize()` unit tests
- `scripts/tests/test_fsm_executor.py` — run after changes to confirm no regressions
- `scripts/tests/test_sprint_integration.py` — run after changes to confirm no regressions

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

## Verification Notes

**Verdict**: OUTDATED — 2026-03-14

- `_render_2d_diagram()` no longer exists in `info.py`; diagram rendering was refactored into `layout.py`
- `info.py` is now **751 lines** (previously noted as 570); all implementation step line references remain invalid
- ENH-638 referenced as prerequisite does not exist in any .issues directory
- **Action needed**: Rewrite implementation steps to target `layout.py` functions; remove or update ENH-638 dependency reference

## Session Log
- `/ll:verify-issues` - 2026-03-15T00:11:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb1dacf-d3dc-4461-88d7-450e60c8640a.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5a9e18cb-659a-48f7-9438-2e4c4fdddd25.jsonl`
- `/ll:confidence-check` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0a53c6fa-fc4b-421b-b487-38a43f4dff4a.jsonl`
- `/ll:refine-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f46a5b1-a489-4906-a03e-8e3d129e5c8a.jsonl`
- `/ll:ready-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/12d9282f-0d38-4934-975d-426a4e8789d4.jsonl`
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9511adcf-591f-4199-b7c1-7ff5d368c8f0.jsonl` — OUTDATED: `_render_2d_diagram()` refactored to `layout.py`; all line refs invalid; ENH-638 dep missing

## Status

**Open** | Created: 2026-03-08 | Priority: P4

## Blocked By
- ENH-665
