---
id: BUG-2303
type: BUG
priority: P2
status: done
size: Small
captured_at: '2026-06-26T01:38:21Z'
discovered_date: 2026-06-25
discovered_by: manual
relates_to:
- BUG-2284
decision_needed: false
completed_at: '2026-06-26T01:38:21Z'
---

# BUG-2303: FSM diagram action-body rows overflow their box borders

## Summary

`ll-loop` Unicode box diagrams were badly broken: action-body rows (e.g.
`echo "..."`, `ABS_DIR="${context.run_dir}"`) overflowed their boxes — the right
`│` was pushed ~2× too far out, dragging every box to its right out of alignment
and scattering stray `│` characters across the canvas. State-name rows and box
borders rendered correctly; only action rows broke. Reproduced from a real
`qa-pipeline` render (see `qa-pipeline-fsm-box-diagram.txt`).

## Root cause

`_draw_box()` in `scripts/little_loops/cli/loop/layout.py` renders into a
character grid where every cell is initialized to a single space
(`grid = [[" "] * total_width ...]`) and rows are emitted with `"".join(row)`.

For SGR batching, each content line is written as a **whole string into one grid
cell** (`grid[r][col+2] = line`). The **name row** (`i == 0`) followed this with a
loop that cleared the cells the string visually covered:

```python
for j in range(1, len(line)):
    if col + 2 + j < col + width - 1:
        grid[r][col + 2 + j] = ""
```

Both **action-row** branches (non-highlighted and highlighted) omitted that
clearing loop. The leftover single-space cells under each action string survived
the join and inflated the row by ~`len(line)-1` columns, pushing the right border
(and every box to its right in the shared grid) out of place.

A secondary defect: box sizing, truncation, and the clear loops used `len()`
(character count) rather than display width, so wide glyphs (CJK, etc.) also bled
past the border.

### How it shipped / why CI stayed green

- Regressed in commit `b075287f` (2026-06-24, "fix(layout): batch SGR sequences
  in `_draw_box`", BUG-2284), which replaced the prior char-by-char action
  rendering (self-aligning and self-clipping) with single-cell batched writes,
  porting the clear loop only to the name row.
- Snapshot goldens (`test_snapshot_loop_layout.ambr`) were then regenerated
  **after** the regression (commit `634dc67d`, 2026-06-25) via
  `pytest --snapshot-update`, baking the broken output in as "expected." No
  assertion verified that box borders actually align, so the snapshot tests
  passed on broken output.

## Changes

### Fix — `scripts/little_loops/cli/loop/layout.py`

- Unified all four content-row branches in `_draw_box()` into a single
  `_place_content_row()` helper that writes the leading space, the line, and a
  single trailing-fill run — and **clears every grid cell the multi-character
  strings visually cover** so the right border stays aligned. This preserves the
  SGR-batching optimization while fixing both the non-highlighted and highlighted
  action rows (the highlighted path had the same latent overflow).
- Added `_display_width()`, `_truncate_to_width()`, and `_wrap_to_width()` helpers
  and switched box sizing (`_compute_box_sizes`), truncation/wrapping
  (`_box_inner_lines`), the clear/fill arithmetic, diagram centering, the
  `_render_fsm_diagram` width estimate, and the neighborhood renderer's padding
  from `len()` to display width — so wide glyphs no longer overflow.

### Regression guard test — `scripts/tests/test_loop_layout_alignment.py` (new)

A structural-invariant test that renders several FSMs (long action body, verbose
multi-line, branching, wide-glyph CJK, highlighted) and asserts every box is a
clean rectangle: left/right `│` and `┌┐└┘` corners sit at equal display columns
(measured with wcwidth) on every row a box spans. It fails on the pre-fix code
and, unlike a snapshot, cannot be silenced by `--snapshot-update`.

### Snapshot goldens — `scripts/tests/__snapshots__/test_snapshot_loop_layout.ambr`

Regenerated against the fixed renderer; the diff shows every action row's border
now closes cleanly (`│ run-check │`, `│ echo fail │`, `│ echo start │`,
`│ echo middle │`).

## Verification

- New guard test fails on pre-fix `main`, passes after the fix (5/5).
- End-to-end: rendered the real `qa-pipeline.yaml` — every box (including the
  `ABS_DIR="${context.run_dir}"` rows that were the worst offenders) is a clean
  rectangle.
- Full suite: 4484 passed, 1 skipped, 16 snapshots passed.
- `ruff check` / `ruff format --check` clean; `mypy` unchanged (only the
  pre-existing `wcwidth` import-untyped note on line 15).


## Session Log
- `hook:posttooluse-status-done` - 2026-06-26T01:38:54 - `a8b9a749-e996-4176-b745-8390861cc45d.jsonl`
