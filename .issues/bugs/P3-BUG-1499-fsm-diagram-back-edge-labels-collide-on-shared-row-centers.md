---
id: BUG-1499
type: BUG
priority: P3
status: done
captured_at: '2026-05-16T14:12:59Z'
completed_at: '2026-05-17T13:50:39Z'
discovered_date: '2026-05-16'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-1499: FSM diagram back-edge labels collide on shared row centers

## Summary

`_render_layered_diagram` writes every back-edge label at `label_row_pos = (top_row + bot_row) // 2`. When two long back-edges share the same midpoint row, their labels are written to the same cells and clobber one another, producing run-together text like `nexterror` and `yesor` in the left margin of the `eval-specfile-gold` diagram.

## Current Behavior

Lines 44 and 47 of the rendered diagram show garbled labels `nexterror` and `yesor` in the back-edge margin. These are the labels `next` + `error` and `yes` + `or` (from a longer label) overlaid on each other because:

- `apply_fix → run_specfile (next, error)`
- `log_and_continue → run_specfile (next, error)`
- `create_issue → skip_specfile`
- `skip_specfile → advance_specfile`
- `refine_cycle → run_specfile (yes/error)`
- `advance_specfile → run_specfile`

…have overlapping vertical spans, and several happen to share `(top_row + bot_row) // 2`.

## Expected Behavior

Each back-edge label should appear on a unique row in the back-edge margin, readable and unambiguous.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: `_render_layered_diagram`, back-edge label placement at `layout.py:1326-1331`.
- **Cause**: `used_cols` tracks pipe columns to avoid pipe collisions, but no analogous structure tracks `label_row_pos`. Two back-edges with the same midpoint write to the same cells.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Back-edge label write: `layout.py:1326-1331` — `label_row_pos = (top_row + bot_row) // 2` then `grid[label_row_pos][label_start + j] = _lc(ch)` with no collision check (note: 1317-1323 in the issue is the pipe-corner rendering just above this)
- Skip-forward symmetric write: `layout.py:1431-1439` — identical formula; shares `grid`; both passes clobber each other when midpoints coincide
- `used_cols` template: `layout.py:1236-1250` — the direct structural analogue; initialize `used_cols: list[int] = []`, then bump `col += 2` for each conflict before committing with `used_cols.append(col)`
- `rightmost_pipe_col` is pre-computed at `layout.py:1238` before the per-edge loop — `used_label_rows` init should follow the same placement

## Proposed Solution

1. Introduce `used_label_rows: set[int]` (or a dict keyed by margin column if multiple margins are in play).
2. When the computed `label_row_pos` is already in the set, nudge ±1 row until a free row is found within `[top_row + 1, bot_row - 1]`.
3. If the search exhausts available rows (very short back-edges), fall back to the row adjacent to `top_row + 1`. As a last resort, prefix the label with the source-state initial or drop it.
4. Keep `label_start = rightmost_pipe_col + 2` so the right-margin column is preserved.
5. Share this `used_label_rows` set with the skip-forward label pass (see BUG-1501) so both passes coordinate.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — introduce `used_label_rows: set[int]` before back-edge loop (line ~1236 near `used_cols` init); apply nudge logic at lines 1326-1331 (back-edge) and coordinate at lines 1431-1439 (skip-forward)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:408-410,427` — calls `_render_fsm_diagram()` for `ll-loop run --show-diagrams` display
- `scripts/little_loops/cli/loop/info.py:16-22` — imports `_render_fsm_diagram` for `ll-loop show`
- `scripts/little_loops/cli/issues/clusters.py:121` — imports `_draw_box` only (not affected)

### Similar Patterns
- `layout.py:1236-1250` — `used_cols` bump-loop: exact structural template for `used_label_rows`
- `layout.py:1341-1354` — `used_fwd_cols` (skip-forward symmetric twin of `used_cols`)
- `layout.py:1431-1439` — skip-forward label write: must share or coordinate with `used_label_rows` (see BUG-1501)

### Tests
- `scripts/tests/test_ll_loop_display.py` — `TestRenderFsmDiagram` class (line 640): add new test here
- Existing back-edge tests to not regress: `test_cyclic_fsm_shows_back_edges_section` (line 716), `test_bidirectional_back_edge_both_pipes_on_label_rows` (line 797), `test_main_path_cycle_renders_back_edge` (line 1000)

_Wiring pass added by `/ll:wire-issue`:_
- `test_issue_refinement_git_topology` (line 909, `TestRenderFsmDiagram`) — has a garbled-label guard (`│[a-zA-Z]` regex at line 982) that directly catches the exact collision this bug fixes; must stay green

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/OUTPUT_STYLING.md` — line 196 documents "separate label rows to prevent overlap"; the fix extends this guarantee to back-edge left-margin labels; no text change needed, but verify the rendered behavior matches the documented intent

### Related Issues
- BUG-1501: skip-forward label collision — proposes sharing `used_label_rows` between both passes; fix BUG-1499 first, then BUG-1501 extends to the right-margin pass

## Steps to Reproduce

1. `cd ~/AIProjects/ai-workspaces/blender-agents`
2. `ll-loop show eval-specfile-gold > /tmp/diagram.txt`
3. Inspect lines 44 and 47 — observe garbled `nexterror` / `yesor` glyphs.

## Impact

- **Severity**: Medium (labels become unreadable on dense loops).
- **Affects**: Loops with many back-edges of overlapping vertical spans — increasingly common as FSMs grow.
- **Workaround**: None; readers must cross-reference the YAML.

## Test Plan

Add a case in `scripts/tests/test_ll_loop_display.py`:

- Fixture: 3-state FSM where two back-edges (different labels) have identical `(top_row + bot_row) // 2` after layout.
- Assert each label appears intact on its own row in the rendered margin (substring search for both full labels).

## Implementation Steps

1. In `layout.py` `_render_layered_diagram()`, immediately after the `used_cols: list[int] = []` declaration (line ~1236), add `used_label_rows: set[int] = set()`.
2. After `label_row_pos = (top_row + bot_row) // 2` (line 1326): nudge the candidate row ±1 until a free slot is found within `[top_row + 1, bot_row - 1]`; fallback to `top_row + 1` if the range is exhausted; commit with `used_label_rows.add(label_row_pos)`.
3. Pass `used_label_rows` into (or hoist it above) the skip-forward block (line ~1335) so the right-margin pass at lines 1431-1439 checks the same set — coordinating with BUG-1501.
4. Add a test in `TestRenderFsmDiagram` (`test_ll_loop_display.py:640`) using `_make_fsm()` with 3+ states that force two back-edges to share `(top_row + bot_row) // 2`; assert both full label strings appear on distinct lines of `result.split("\n")`.
5. Run `python -m pytest scripts/tests/test_ll_loop_display.py -v` and confirm no regressions in `test_bidirectional_back_edge_both_pipes_on_label_rows`, `test_cyclic_fsm_shows_back_edges_section`, and `test_issue_refinement_git_topology` (the garbled-label guard at line 982 is the canonical collision detector).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/cli/loop/layout.py` | Renderer under repair |
| `~/.claude/plans/investigate-the-fsm-loop-twinkly-bear.md` | Source investigation plan (Bug B) |

Closely related (now closed): BUG-672, BUG-755 — earlier back-edge fixes did not introduce per-row coordination.

## Labels

- area:fsm-diagram
- area:renderer

## Status

- **Discovered**: 2026-05-16 via investigation plan against `eval-specfile-gold`
- **Captured by**: `/ll:capture-issue`

## Resolution

- Introduced `used_label_rows: set[int]` before both the back-edge and skip-forward rendering blocks in `_render_layered_diagram` (`layout.py:1229`).
- Added nudge logic at each label placement: if the computed midpoint row is already taken, search ±1 offsets within `[top_row+1, bot_row-1]`; fall back to `top_row+1` if all interior rows are exhausted.
- Applied the same nudge to the skip-forward (right-margin) label pass using the shared `used_label_rows` set, coordinating both passes.
- Added `test_back_edge_labels_no_collision_on_shared_midpoint` in `TestRenderFsmDiagram` — 149/149 tests pass.

## Session Log
- `/ll:manage-issue` - 2026-05-17T13:50:39Z - `current.jsonl`
- `/ll:ready-issue` - 2026-05-17T13:42:37 - `e56cd245-0d2f-482a-8131-acf6fe22dda9.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `34c2b455-ee2b-4f98-9bb6-33fc0c80efb0.jsonl`
- `/ll:wire-issue` - 2026-05-17T13:39:46 - `70fe2c68-541d-4c01-b532-297806a96cec.jsonl`
- `/ll:refine-issue` - 2026-05-17T13:32:22 - `54eb6e1c-0574-4269-a396-569a67d5a08a.jsonl`
- `/ll:capture-issue` - 2026-05-16T14:12:59Z - `f204025d-307a-4f4d-80b2-206dfd3b1de1.jsonl`
