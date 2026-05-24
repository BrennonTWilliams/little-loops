---
id: ENH-654
type: ENH
priority: P4
status: open
discovered_date: 2026-03-08
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 72
decision_needed: false
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
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

Changes are isolated to `scripts/little_loops/cli/loop/layout.py`:

- **`_draw_box()` at `layout.py:567`**: add a pre-fill pass over all interior cells (content + padding rows, cols `col+1..col+width-2`) when `is_highlighted and bg_code`; update the name-row ANSI code to `f"30;{bg_code};1"` (dark fg + bg + bold) and content chars to `f"30;{bg_code}"`
- **`_render_neighborhood_diagram()` inline `_make_box()` at `layout.py:1702`**: update the two flanking space cells and the state name to use `bg_code` when highlighted

No config schema changes are strictly required if `highlight_color` is automatically converted from fg→bg (e.g., `"32"` → `"42"`). A separate `highlight_bg_color` config field could be added to `config-schema.json` for explicit control.

## Implementation Steps

1. **Read `_draw_box()` in `layout.py:567-668`** to understand the grid model (`grid` is `list[list[str]]`; cells are single-char strings; the empty-string trick stores an ANSI-wrapped string at `col+2` and sets subsequent cells to `""` so they emit nothing when joined)
2. **Compute `bg_code` safely** — add before the `_bc()` closure definition at `layout.py:585`:
   ```python
   try:
       bg_code: str | None = str(int(highlight_color) + 10)
   except ValueError:
       bg_code = None  # compound code like "38;5;208" — skip bg fill
   ```
3. **Add interior pre-fill pass** (`layout.py:~620`, before the content-rows loop): when `is_highlighted and bg_code`, iterate rows `row+1..row+height-2` and cols `col+1..col+width-2`, setting each to `colorize(" ", bg_code)` — covers interior of all content + padding rows; must run **before** content writes so subsequent char writes overwrite the spaces correctly
4. **Update name row rendering** (`layout.py:629-635`): for `is_highlighted and i == 0`, change `colorize(line, f"{highlight_color};1")` → `colorize(line, f"30;{bg_code};1")` (dark fg + bg + bold); the empty-string trick at col+3..col+2+len-1 still applies and overwrites the pre-filled cells, which is correct — those visual positions are occupied by the name's ANSI characters
5. **Update remaining content row rendering** (`layout.py:643-646`): for `is_highlighted and i > 0`, change `grid[r][col + 2 + j] = ch` → `grid[r][col + 2 + j] = colorize(ch, f"30;{bg_code}")` (individual chars get dark fg + bg)
6. **Update `_render_neighborhood_diagram()` `_make_box()` closure** (`layout.py:1702-1718`): add `bg_code` computation in the outer `_render_neighborhood_diagram()` scope (same `try/except` pattern); in the highlighted branch (line 1706), change the two flanking `" "` to `colorize(" ", bg_code)` (lines 1711 and 1713) and change the name to `colorize(padded, f"30;{bg_code};1")` (line 1712)
7. **Add test assertions** in `scripts/tests/test_ll_loop_display.py` (extend `test_highlighted_state_uses_configured_color` at line 1256 which uses `highlight_color="36"`): assert `"\033[46m "` (bg cyan fill) appears in the result for interior cells of the highlighted state
8. **Verify visually** with `ll-loop run <any-loop> --show-diagrams`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Verify `scripts/little_loops/cli/issues/clusters.py:137` (`_render_cluster_diagram`) is unaffected — `_draw_box` is called with `is_highlighted=False` so the `is_highlighted and bg_code` guard never fires; confirm no regression
10. Update `scripts/tests/test_ll_loop_display.py:1256` (`test_highlighted_state_uses_configured_color`) — change `assert "\033[36;1m" in result` → `assert "\033[30;46;1m" in result`; add `assert "\033[46m " in result`
11. Update `scripts/tests/test_ll_loop_display.py:1275` (`test_highlighted_state_default_green`) — add `assert "\033[42m " in result`
12. Verify badge assertion at `test_ll_loop_display.py:~2695` (`"\033[36m✦"`) — if `_bc()` border closure is unchanged, this passes; if border chars also get `bg_code`, update accordingly
13. Write new test in `TestRenderNeighborhoodDiagram` — follow `test_prev_state_pred_gets_orange_border` (line 3288) pattern; assert `f"\x1b[{bg_code}m "` in raw lines containing the active state label
14. Update `docs/reference/OUTPUT_STYLING.md` — revise `### State box format` and the active-state color sentence to describe background fill behavior
15. Update `docs/reference/CONFIGURATION.md` — revise `### cli.colors.fsm_active_state` to note the value also drives bg fill; add `highlight_bg_color` subsection if that config field is added

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — `_draw_box()` (lines 567–668): add `bg_code` computation + pre-fill pass + update name and content char rendering; `_render_neighborhood_diagram()` `_make_box()` closure (lines 1702–1718): add `bg_code` computation and update interior cells

### Dependent Files (Callers/Importers)

_Codebase Research: full call chain with line refs:_
- `scripts/little_loops/cli/loop/run.py:169` — reads `fsm_active_state` color from config as `_highlight_color`; passes to `run_foreground()` at line 356
- `scripts/little_loops/cli/loop/_helpers.py:601` — `run_foreground()` signature: `highlight_color: str = "32"`; calls `_render_fsm_diagram()` at lines 283, 295, 660, 746, 781
- `scripts/little_loops/cli/loop/layout.py:1534` — `_render_fsm_diagram()` dispatches to `_render_layered_diagram()`, `_render_horizontal_simple()`, or `_render_neighborhood_diagram()`
- `scripts/little_loops/cli/loop/layout.py:1008–1018` — `_render_layered_diagram()` calls `_draw_box()`
- `scripts/little_loops/cli/loop/layout.py:1812–1822` — `_render_horizontal_simple()` calls `_draw_box()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/clusters.py:137` — calls `_draw_box(grid, row, _BOX_MARGIN, box_width, _BOX_HEIGHT, content, False, "0")` in `_render_cluster_diagram()`; always passes `is_highlighted=False` so the bg_code guard is safe — verify the non-highlighted path remains unaffected after changes
- `scripts/little_loops/cli/loop/info.py:823` — calls `_render_fsm_diagram(fsm, verbose)` without `highlight_state`/`highlight_color` in `cmd_show()`; uses defaults — verify signature remains compatible

### Similar Patterns
- `scripts/little_loops/cli/loop/layout.py:585–586` — `_bc()` helper closure inside `_draw_box()`: `return colorize(ch, highlight_color) if is_highlighted else ch`; follow the same pattern for `bg_code` guard before the closure
- `scripts/little_loops/cli/loop/layout.py:629–635` — `colored_line` trick: ANSI-wrapped string at `col+2`, subsequent cells set to `""`; current highlighted code is `f"{highlight_color};1"` → change to `f"30;{bg_code};1"` for dark fg + bg + bold
- `scripts/little_loops/cli/output.py:107` — `colorize(text, code)` definition: accepts any ANSI SGR string (e.g., `"30;42;1"` for dark fg + green bg + bold), wraps with `\033[{code}m...\033[0m`

### Tests
- `scripts/tests/test_ll_loop_display.py:1256` — `test_highlighted_state_uses_configured_color()`: asserts `"\033[36m"` (border) and `"\033[36;1m"` (bold name) — **add bg fill assertion here**: `assert "\033[46m "` in result (bg cyan for `highlight_color="36"`)
- `scripts/tests/test_ll_loop_display.py:1275` — `test_highlighted_state_default_green()`: add assertion for `"\033[42m "` (green bg fill for default `highlight_color="32"`)
- `scripts/tests/test_cli_output.py:80` — `TestColorize`: `colorize()` unit tests; reference for compound-code assertions
- `scripts/tests/test_fsm_executor.py` — run after changes to confirm no regressions
- `scripts/tests/test_sprint_integration.py` — run after changes to confirm no regressions

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_display.py:1256` (BREAKS) — `test_highlighted_state_uses_configured_color`: the `"\033[36;1m"` assertion breaks after step 4 changes name-row code from `f"{highlight_color};1"` → `f"30;{bg_code};1"`; must update to assert `"\033[30;46;1m"` and add `assert "\033[46m " in result`
- `scripts/tests/test_ll_loop_display.py:~2695` (MAY BREAK) — badge `"\033[36m✦"` assertion in badge rendering tests; if `_bc()` closure inside `_draw_box` is NOT changed (only interior fill is added), border chars still use fg color so this assertion remains valid — verify after implementation
- `scripts/tests/test_ll_loop_display.py:TestRenderNeighborhoodDiagram` (NEW) — no existing test covers bg fill in `_make_box` highlighted branch; write new test following `test_prev_state_pred_gets_orange_border` pattern (line 3288): mock `_USE_COLOR=True`, call `_render_neighborhood_diagram()`, assert `f"\x1b[{bg_code}m "` in raw output lines containing the active state label
- `scripts/tests/test_config.py:TestCliColorsConfig` (CONDITIONAL) — if `highlight_bg_color` config field is added, add parallel tests for its default and override (`test_fsm_active_state_*` pattern at line 1877)
- `scripts/tests/test_cli_loop_worktree.py:614,649,675` (CONDITIONAL) — mocks set `mock_cfg.return_value.cli.colors.fsm_active_state = None`; if `run_foreground()` signature gains a new `highlight_bg_color` param, analogous `= None` mock lines are needed here

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/OUTPUT_STYLING.md` — `### State box format` section and active-state color sentence (~line 240) describe border-only coloring; update to describe background fill behavior and the fg→bg auto-derivation (`"32"` → `"42"`)
- `docs/reference/CONFIGURATION.md` — `### cli.colors.fsm_active_state` section (lines 669–687) documents the key as a foreground/border color only; update description to note the same value also controls bg fill; if `highlight_bg_color` is added as a separate field, add a new subsection here

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

**Verdict**: REFINED — 2026-05-23

- `_render_2d_diagram()` no longer exists; rendering now split across `_draw_box()` (line 567), `_render_layered_diagram()` (line 675), `_render_horizontal_simple()` (line 1760), and `_render_neighborhood_diagram()` (line 1653) — all in `layout.py`
- `_render_fsm_diagram()` at `layout.py:1534`
- Implementation steps rewritten to target correct `layout.py` functions with verified line numbers
- ENH-638 prerequisite still does not exist; main-path fix in `_draw_box()` does not depend on it; off-path (`_render_neighborhood_diagram`) can proceed independently

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-23_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- **Test breakage expected**: `test_highlighted_state_uses_configured_color` (line 1256) asserts `"\033[36;1m"` which breaks after step 4 changes the name code to `"30;46;1"` — update first so test suite stays green
- **Badge assertion at ~2695 needs verification**: if `_bc()` closure is unchanged (borders keep fg color), it passes; confirm during implementation rather than after
- **Optional config field decision deferred**: "highlight_bg_color could be added" — resolve explicitly during implementation (auto-derive fg→bg or add field) to avoid revisiting
- **Grid model complexity**: the empty-string cell trick for wide ANSI strings must be respected in the pre-fill pass (pre-fill runs before content writes, which is correct per step 3)

## Session Log
- `/ll:confidence-check` - 2026-05-23T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/94d3a774-727b-48c4-982b-4324047ede61.jsonl`
- `/ll:wire-issue` - 2026-05-24T00:45:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8177277-27a8-4514-86b4-2e9d9e6a5787.jsonl`
- `/ll:refine-issue` - 2026-05-24T00:28:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ba7a251-01eb-435c-ba22-90efa9dacf11.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:02:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4aa69027-63ea-4746-aed4-e426ab30885a.jsonl`
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:verify-issues` - 2026-04-03T02:58:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b02a8b8-608b-4a1c-989a-390b7334b1d4.jsonl`
- `/ll:verify-issues` - 2026-04-01T17:45:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:tradeoff-review-issues` - 2026-03-22T05:05:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7a58662a-8ea7-4c74-bb16-c6d77d559e08.jsonl`
- `/ll:verify-issues` - 2026-03-15T00:11:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb1dacf-d3dc-4461-88d7-450e60c8640a.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5a9e18cb-659a-48f7-9438-2e4c4fdddd25.jsonl`
- `/ll:confidence-check` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0a53c6fa-fc4b-421b-b487-38a43f4dff4a.jsonl`
- `/ll:refine-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f46a5b1-a489-4906-a03e-8e3d129e5c8a.jsonl`
- `/ll:ready-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/12d9282f-0d38-4934-975d-426a4e8789d4.jsonl`
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9511adcf-591f-4199-b7c1-7ff5d368c8f0.jsonl` — OUTDATED: `_render_2d_diagram()` refactored to `layout.py`; all line refs invalid; ENH-638 dep missing

## Deferral Note

~~**Deferred**: 2026-04-11~~ — Resolved 2026-05-23: implementation steps rewritten to target correct `layout.py` functions.

## Status

**Open** | Created: 2026-03-08 | Priority: P4

## Blocked By

---

## Tradeoff Review Note

**Reviewed**: 2026-03-22 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | LOW |
| Implementation effort | MEDIUM |
| Complexity added | MEDIUM |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - Implementation steps are OUTDATED: `_render_2d_diagram()` was refactored to `layout.py` and no longer exists in `info.py`. All file:line references in the implementation steps are invalid. Rewrite implementation steps targeting the correct functions in `layout.py` before implementing. Visual polish only with no functional impact.
