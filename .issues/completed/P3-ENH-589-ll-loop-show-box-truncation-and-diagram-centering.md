---
discovered_date: 2026-03-05
discovered_by: user
confidence_score: 98
completed_date: 2026-03-05
---

# ENH-589: Fix `ll-loop show` box truncation and add diagram centering

## Summary

`ll-loop show` rendered ASCII FSM diagrams with two usability problems: action previews in non-verbose boxes were truncated to nearly useless snippets (~13–19 chars), and the diagram was left-aligned with only a 2-char margin, leaving wasted space on wider terminals.

## Changes Made

### 1. Expand box inner width in non-verbose mode (`info.py` lines 341–346)

`max_box_inner` was previously hardcoded to `0` in non-verbose mode, causing action previews to be trimmed to the name+badge line width. Now computed for both modes:

- **Verbose**: `max(20, min(60, (tw - 4) // num_main - 6))` (unchanged)
- **Non-verbose**: `max(20, min(40, (tw - 4) // num_main - 6))` (new)

### 2. Use first action line for non-verbose width expansion (`info.py` lines 364–369)

The `inner_w` expansion block previously only ran in verbose mode. Now runs for both modes:

- **Verbose**: expands to the longest action line (multi-line preview, unchanged)
- **Non-verbose**: expands to the length of the first non-empty action line only (since only one line is shown)

**Effect** (issue-refinement loop, tw=80, 2 main states): `max_box_inner = 32`. The `evaluate` box shows `ll-issues refine-status --no-key` in full; the `fix` box shows the first 32 chars of its action — readable and clearly identifies the task.

### 3. Center the diagram in the terminal (`info.py` lines 416–421, 495–499, 700–703)

After `total_width` is finalized, a `diagram_indent` is computed:

```python
diagram_indent = max(0, (tw - total_width) // 2)
```

Applied at both return sites by prepending spaces to non-empty rendered lines. The underlying column math (`col_start`, `anchor_cc`, `down_col`) is unchanged — centering is pure post-processing.

**Effect**: On an 80-char terminal with `total_width ≈ 65`, `diagram_indent = 7`. On a 120-char terminal, `diagram_indent = 27`, shifting `down_col` rightward so back-edge labels more often fit on the left side naturally.

### 4. Raise summary table action preview cap (`info.py` line 778)

- Cap: `35` → `50` chars
- Width allocation: `remaining // 2` (50%) → `remaining * 3 // 5` (60%)

This gives the Action Preview column more room relative to the Transitions column.

## Files Modified

- `scripts/little_loops/cli/loop/info.py`

## Verification

- `ll-loop show issue-refinement` — boxes show full/useful action previews; diagram centered
- `ll-loop show issue-refinement --verbose` — unaffected
- `ll-loop show code-quality` — layout sane
- `python -m pytest scripts/tests/ -q` — 3287 passed, 4 skipped
