---
discovered_date: "2026-03-11"
discovered_by: capture-issue
---

# BUG-672: FSM diagram back-edge rendering bugs

## Summary

The adaptive layout engine (`layout.py`) renders back-edges incorrectly in the `issue-refinement-git` loop diagram. Three distinct bugs produce garbled output: duplicate back-edge pipes for same-pair edges, labels overlapping vertical pipes, and horizontal connectors overwriting box borders.

## Current Behavior

1. **Duplicate back-edge pipes**: `check_commit→evaluate` has both "fail" and "error" edges rendered as 2 separate margin pipes instead of 1 combined "error/fail" pipe, creating 3 pipes (▲─▲─▲) when there should be 2.
2. **Labels overlap vertical pipes**: Back-edge labels placed at `col + 2` overwrite other pipes at columns 3 and 5, producing garbled output like `│aerror` and `e│t` instead of clean labels.
3. **Horizontal connector on bottom border row**: `src_row` is set to the box's bottom border row (`└───┘`), so `─` connectors overwrite border characters.

## Expected Behavior

1. Same-pair back-edges should be combined into a single pipe with a merged label (e.g., "error/fail").
2. Labels should be placed to the right of ALL back-edge vertical pipes, not overlapping any pipe columns.
3. Horizontal connectors should originate from a content row (name row), not the box border row.

## Steps to Reproduce

1. Load the `issue-refinement-git` loop: `.loops/issue-refinement-git.yaml`
2. Render its FSM diagram via `_render_fsm_diagram(fsm, verbose=False)`
3. Observe garbled labels (`│aerror`, `e│t`), 3 pipes instead of 2, and border overwriting

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: `in function _render_layered_diagram()`, back-edge rendering block (from `non_self_back_initial` construction through `sorted_back` iteration)
- **Cause**:
  1. `non_self_back_initial` list comprehension doesn't combine edges with same `(src, dst)` pair before computing `back_edge_margin`
  2. In the `for src, dst, label in sorted_back:` loop, `label_start = col + 2` positions the label relative to the current pipe column instead of the rightmost pipe column
  3. In the same loop, `src_row` is computed as `row_start[src] + box_height[src] - 1` (bottom border row `└───┘`) instead of `row_start[src] + 1` (name/content row)

## Motivation

FSM diagrams are the primary visual feedback for loop configuration. Garbled back-edge rendering makes diagrams unreadable for any loop with multiple back-edges to the same target state (e.g., error + fail → evaluate), undermining user trust in loop correctness and making debugging loop configurations harder.

## Proposed Solution

### 1. Combine same-pair back-edge labels (in `non_self_back_initial` construction and after reclassification into `non_self_back`)

Before computing `back_edge_margin`, consolidate back-edges with same `(src, dst)` into a single entry with joined labels (e.g., "error/fail"). Apply the same consolidation after the layer-based reclassification loop that builds `non_self_back`.

### 2. Fix label positioning (in `for src, dst, label in sorted_back:` loop, `label_start` assignment)

Before the `sorted_back` loop, compute `rightmost_pipe_col = 1 + (len(sorted_back) - 1) * 2`. Replace `label_start = col + 2` with `label_start = rightmost_pipe_col + 2`.

### 3. Fix source connector row (in `for src, dst, label in sorted_back:` loop, `src_row` assignment)

Change `src_row = row_start.get(src, 0) + box_height.get(src, 2) - 1` to `src_row = row_start.get(src, 0) + 1` (name row, not border).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — `_render_layered_diagram()` function

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/display.py` — calls `_render_fsm_diagram()`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_ll_loop_display.py` — add test for `issue-refinement-git` back-edge rendering

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Combine same-pair back-edge entries before margin sizing and after reclassification
2. Fix label positioning to use rightmost pipe column
3. Fix source connector row to use content row instead of border row
4. Add test verifying combined labels, no garbled output, correct pipe count
5. Run full test suite to verify no regressions

## Impact

- **Priority**: P2 - Produces visually broken diagram output for any loop with multiple back-edges to the same target
- **Effort**: Small - All changes are localized to `_render_layered_diagram()` in `layout.py`
- **Risk**: Low - Changes are isolated to rendering logic with no side effects on FSM execution
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | System design context for CLI loop module |

## Labels

`bug`, `cli`, `fsm-diagram`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2628af2a-aca0-4d4e-ad1b-655fd8aab5a9.jsonl`
- `/ll:format-issue` - 2026-03-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd96b75e-fbd0-4dcc-ba9f-72fc5447a846.jsonl`

---

## Status

**Open** | Created: 2026-03-11 | Priority: P2
