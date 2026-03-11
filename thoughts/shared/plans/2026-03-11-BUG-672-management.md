# BUG-672: FSM diagram back-edge rendering bugs — Implementation Plan

## Summary
Fix three back-edge rendering bugs in `layout.py:_render_layered_diagram()`.

## Changes

### Fix 1: Combine same-pair back-edges (line 628)
Replace list comprehension with dict-based consolidation matching the forward-edge pattern at lines 607-624.

### Fix 2: Combine same-pair back-edges after reclassification (lines 686-697)
Apply same consolidation to `non_self_back` after the reclassification loop.

### Fix 3: Fix source connector row (line 865)
Change `row_start.get(src, 0) + box_height.get(src, 2) - 1` → `row_start.get(src, 0) + 1` (name row).

### Fix 4: Fix label positioning (line 907)
Compute `rightmost_pipe_col` before the sorted_back loop, position all labels right of ALL pipes.

### Tests
Extend `test_issue_refinement_git_topology` with `on_error` on check_commit to reproduce the duplicate pipe bug. Add assertions for:
- Exactly 2 `▲` arrows (not 3)
- No garbled label substrings
- Border characters preserved

## Success Criteria
- [ ] Same-pair back-edges combined into single pipe
- [ ] Labels don't overlap pipes
- [ ] Horizontal connectors don't overwrite box borders
- [ ] All existing tests pass
- [ ] New test assertions pass
