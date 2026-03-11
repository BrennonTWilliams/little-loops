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
- **Anchor**: `_render_layered_diagram()`, back-edge rendering block (lines 854–910)
- **Cause**:
  1. **Duplicate pipes** — `non_self_back_initial` at line 628 is a simple list comprehension `[(s, d, lbl) for s, d, lbl in back_edges if s != d]` that doesn't combine edges with same `(src, dst)` pair before computing `back_edge_margin` (line 630–632). The reclassification loop at lines 686–697 rebuilding `non_self_back` also doesn't combine.
  2. **Label overlap** — At line 907, `label_start = col + 2` positions each label relative to its own pipe column. When multiple pipes exist (col=1, col=3, col=5), labels at `col + 2` (e.g., col 3 for the first pipe) land on top of other pipes' columns, producing garbled output like `│aerror`.
  3. **Border overwrite** — At line 865, `src_row = row_start.get(src, 0) + box_height.get(src, 2) - 1` resolves to the `└───┘` border row. The horizontal connector loop at lines 891–895 then overwrites border characters with `─`.

## Motivation

FSM diagrams are the primary visual feedback for loop configuration. Garbled back-edge rendering makes diagrams unreadable for any loop with multiple back-edges to the same target state (e.g., error + fail → evaluate), undermining user trust in loop correctness and making debugging loop configurations harder.

## Proposed Solution

### 1. Combine same-pair back-edge labels (lines 628 and 686–697)

Follow the same pattern used for forward edges at `layout.py:607-624`:

**At line 628** — Replace the list comprehension with a dict-based consolidation:
```python
# Before: non_self_back_initial = [(s, d, lbl) for s, d, lbl in back_edges if s != d]
back_edge_labels: dict[tuple[str, str], str] = {}
for s, d, lbl in back_edges:
    if s != d:
        if (s, d) in back_edge_labels:
            back_edge_labels[(s, d)] += "/" + lbl
        else:
            back_edge_labels[(s, d)] = lbl
non_self_back_initial = [(s, d, lbl) for (s, d), lbl in back_edge_labels.items()]
```

**At lines 686–697** — Apply the same consolidation after reclassification builds `non_self_back`.

### 2. Fix label positioning (line 907)

Before the `sorted_back` loop, compute the rightmost pipe column. Replace `label_start = col + 2` with:
```python
rightmost_pipe_col = 1 + (len(sorted_back) - 1) * 2
# ... inside loop:
label_start = rightmost_pipe_col + 2  # right of ALL pipes
```

### 3. Fix source connector row (line 865)

Change to use the name/content row (1 below box top):
```python
# Before: src_row = row_start.get(src, 0) + box_height.get(src, 2) - 1
src_row = row_start.get(src, 0) + 1  # name row, not bottom border
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — `_render_layered_diagram()` lines 628–632 (combine same-pair edges), lines 686–697 (reclassification combine), line 865 (src_row fix), line 907 (label_start fix)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:20` — re-exports `_render_fsm_diagram` from `layout.py`
- `scripts/little_loops/cli/loop/info.py:457` — calls `_render_fsm_diagram(fsm, verbose=verbose)`
- `scripts/little_loops/cli/loop/_helpers.py:324-326` — calls `_render_fsm_diagram()` for diagram display during loop execution

### Similar Patterns
- `layout.py:607-624` — Forward edge label combining uses `forward_edge_labels` dict with `(src, dst)` keys and `+= "/" + lbl` for duplicate pairs. The same pattern should be applied to `non_self_back_initial` and `non_self_back`.

### Tests
- `scripts/tests/test_ll_loop_display.py:908-969` — Existing `test_issue_refinement_git_loop_all_states_and_back_edges` tests the issue-refinement-git pattern; currently asserts `▲` count ≥ 2 but does NOT check for label garbling, correct pipe count, or border integrity. Needs additional assertions.
- `scripts/tests/test_ll_loop_display.py:789` — `test_bidirectional_back_edge_both_pipes_on_label_rows` tests bidirectional back-edges.

### Documentation
- N/A

### Configuration
- `.loops/issue-refinement-git.yaml` — The loop config that triggers this bug. Has `check_commit` state with `on_failure: evaluate` and `on_error: evaluate` (same-pair back-edges), plus `commit` state with `next: evaluate` (third back-edge).

## Implementation Steps

1. **Combine same-pair back-edges** — In `layout.py:628`, replace list comprehension with dict-based consolidation (same pattern as `forward_edge_labels` at line 607). Apply same consolidation in the reclassification block at lines 686–697.
2. **Fix label positioning** — In `layout.py:907`, compute `rightmost_pipe_col = 1 + (len(sorted_back) - 1) * 2` before the loop; replace `label_start = col + 2` with `label_start = rightmost_pipe_col + 2`.
3. **Fix source connector row** — In `layout.py:865`, change `row_start.get(src, 0) + box_height.get(src, 2) - 1` to `row_start.get(src, 0) + 1`.
4. **Extend test** — In `test_ll_loop_display.py:933`, add assertions to `test_issue_refinement_git_loop_all_states_and_back_edges`:
   - `check_commit→evaluate` fail/error edges should produce exactly 2 `▲` arrows (not 3)
   - No garbled substrings like `│a` followed by a letter on the same line
   - `└` and `┘` border characters should not be overwritten by `─`
5. **Run full test suite**: `python -m pytest scripts/tests/test_ll_loop_display.py -v`

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
- `/ll:refine-issue` - 2026-03-11T20:05:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Status

**Open** | Created: 2026-03-11 | Priority: P2
