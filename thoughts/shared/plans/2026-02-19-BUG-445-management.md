# BUG-445: Fix FSM diagram non-main-path edge rendering

## Issue Summary
Non-main-path edges (branches, back-edges) are rendered as plain text annotations instead of 2D routed lines with box-drawing characters.

## Research Findings
- `_render_2d_diagram()` at `info.py:171-307` already computes `col_start`, `col_center`, `off_path`, `total_width`
- Lines 298-306 append plain text `"src ──(label)──▶ dst"` for all non-main-path edges
- Self-loops (line 285-296) are already handled with `↺` markers
- Tests use string-presence assertions (not exact layout), so updating rendering won't break most tests

## Implementation Plan

### Phase 1: Replace text annotations with 2D routed edges

**File**: `scripts/little_loops/cli/loop/info.py` lines 298-306

Replace the text annotation loop with grid-based 2D edge routing:

1. **Separate edges into back-edges and forward branches**
2. **For back-edges** (dst is earlier in main path than src):
   - Draw vertical `│` drop from `col_center[src]`
   - Draw horizontal `─` run from src column to dst column
   - Place label along horizontal segment
   - Draw `▲` arrow up into `col_center[dst]`
   - Use `└` and `┘` corner characters at turns
   - Stack multiple back-edges at increasing vertical offsets
3. **For forward branches to off-path states**:
   - Draw vertical `│` drop from `col_center[src]`
   - Render off-path target as a box below
   - Draw connecting lines with labels
4. **For edges between off-path states and main-path states** (e.g., fix → evaluate):
   - Route similarly with vertical/horizontal segments

### Phase 2: Update tests

**File**: `scripts/tests/test_ll_loop_display.py`

- Update `test_branching_fsm_shows_branches_section` to verify box-drawing chars for branches
- Update `test_cyclic_fsm_shows_back_edges_section` to verify 2D routing characters
- Add assertions for `│`, `└`, `▲` characters in routed edges

### Success Criteria
- [ ] Back-edges rendered as 2D routed lines with box-drawing characters
- [ ] Off-path states rendered as boxes
- [ ] Edge labels placed along routed lines
- [ ] Multiple back-edges stack without overlap
- [ ] All existing tests pass
- [ ] New assertions verify 2D routing
