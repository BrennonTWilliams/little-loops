---
id: BUG-1499
type: BUG
priority: P3
status: open
captured_at: "2026-05-16T14:12:59Z"
discovered_date: "2026-05-16"
discovered_by: capture-issue
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
- **Anchor**: `_render_layered_diagram`, back-edge label placement at `layout.py:1317-1323`.
- **Cause**: `used_cols` tracks pipe columns to avoid pipe collisions, but no analogous structure tracks `label_row_pos`. Two back-edges with the same midpoint write to the same cells.

## Proposed Solution

1. Introduce `used_label_rows: set[int]` (or a dict keyed by margin column if multiple margins are in play).
2. When the computed `label_row_pos` is already in the set, nudge ±1 row until a free row is found within `[top_row + 1, bot_row - 1]`.
3. If the search exhausts available rows (very short back-edges), fall back to the row adjacent to `top_row + 1`. As a last resort, prefix the label with the source-state initial or drop it.
4. Keep `label_start = rightmost_pipe_col + 2` so the right-margin column is preserved.
5. Share this `used_label_rows` set with the skip-forward label pass (see BUG-1501) so both passes coordinate.

## Steps to Reproduce

1. `cd /Users/brennon/AIProjects/ai-workspaces/blender-agents`
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

## Session Log
- `/ll:capture-issue` - 2026-05-16T14:12:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f204025d-307a-4f4d-80b2-206dfd3b1de1.jsonl`
