---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
confidence_score: 90
outcome_confidence: 100
---

# ENH-542: `_render_fsm_diagram` Uses O(n) `list.index()` Inside Edge-Classification Loop

## Summary

`_render_fsm_diagram` classifies edges as forward vs back edges by calling `bfs_order.index(src)` and `bfs_order.index(dst)` inside the edge loop. Both are O(n) list scans. The function already builds `bfs_depth: dict[str, int]` during BFS traversal that maps state names to their depth, providing the same position information in O(1) lookup. The `bfs_depth` dict is not used in the edge-classification code.

## Location

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Line(s)**: 279–287 (current; 155–164 at scan commit: 47c81c8)
- **Anchor**: `in function _render_fsm_diagram()`, edge-classification loop
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/cli/loop/info.py#L155-L164)
- **Code**:
```python
for i, (src, dst, label) in enumerate(edges):
    if i in main_consumed:
        continue
    src_pos = bfs_order.index(src) if src in bfs_order else len(bfs_order)   # O(n)
    dst_pos = bfs_order.index(dst) if dst in bfs_order else len(bfs_order)   # O(n)
    if dst == src or dst_pos < src_pos:
        back_edges.append((src, dst, label))
    else:
        branches.append((src, dst, label))
```

`bfs_depth` is built at line 114 as `bfs_depth: dict[str, int]` — same information, O(1) access.

## Current Behavior

For each edge, two O(n) list scans run. With E edges and N states, total cost is O(E × N). For a 20-state FSM with 30 edges, that's 1,200 list comparisons instead of 60 dict lookups.

## Expected Behavior

`bfs_depth.get(src, len(bfs_order))` replaces `bfs_order.index(src) if src in bfs_order else len(bfs_order)`, giving O(1) lookup.

## Motivation

Minor performance improvement. The fix also removes the redundant `if src in bfs_order` membership test (O(n) for list, replaced by `dict.get` default). The existing `bfs_depth` dict is the right tool that's already computed but unused here.

## Proposed Solution

Build a `bfs_pos` position-lookup dict from `bfs_order` after the BFS loop, then use it in the edge-classification loop:

```python
# After BFS loop (line ~247), add:
bfs_pos: dict[str, int] = {node: i for i, node in enumerate(bfs_order)}

# In edge-classification loop (lines 282–283), replace:
#   src_pos = bfs_order.index(src) if src in bfs_order else len(bfs_order)
#   dst_pos = bfs_order.index(dst) if dst in bfs_order else len(bfs_order)
# With:
src_pos = bfs_pos.get(src, len(bfs_order))   # O(1), was O(n)
dst_pos = bfs_pos.get(dst, len(bfs_order))   # O(1), was O(n)
```

**Note**: `bfs_depth` cannot substitute for `bfs_order.index()`. `bfs_depth` records depth levels, not list positions — two sibling nodes at the same depth have equal `bfs_depth` values but distinct `bfs_order` positions. Using `bfs_depth` would misclassify sibling-to-sibling edges (e.g., edge C→B where both are at depth 1 would be classified as a branch instead of a back-edge).

## Scope Boundaries

- Only `_render_fsm_diagram` edge-classification loop
- Does not change diagram output or edge classification semantics
- Does not affect `bfs_order` or `bfs_depth` construction

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `_render_fsm_diagram()`, edge-classification loop

### Dependent Files (Callers/Importers)
- `cmd_show()` calls `_render_fsm_diagram()`; no interface change

### Similar Patterns
- `bfs_depth` construction at line 114 — already uses dict for O(1) access pattern

### Tests
- Existing diagram rendering tests cover this path; no new tests needed

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. After the BFS loop in `_render_fsm_diagram()` (~line 247), add: `bfs_pos: dict[str, int] = {node: i for i, node in enumerate(bfs_order)}`
2. Replace `bfs_order.index(src) if src in bfs_order else len(bfs_order)` with `bfs_pos.get(src, len(bfs_order))`
3. Apply same replacement for `dst`
4. Confirm `ll-loop show` diagram output is visually identical

## Impact

- **Priority**: P4 — Minor performance; primarily code clarity (using the right data structure)
- **Effort**: Small — 3-line change (add `bfs_pos` dict after BFS loop, replace 2 `index()` calls)
- **Risk**: Low — `bfs_pos` dict built from `bfs_order` is semantically identical to `bfs_order.index()`; existing diagram tests cover this path
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | CLI interface — FSM diagram rendering via `ll-loop show` (line 1381) |
| `docs/guides/LOOPS_GUIDE.md` | Loop inspection and diagram walkthrough (line 191) |

## Labels

`enhancement`, `ll-loop`, `performance`, `scan-codebase`

## Verification Notes

- **Verdict**: NEEDS_UPDATE (2026-03-05)
- **Code verified**: `bfs_order.index()` calls at lines 282–283 confirmed present (moved from 155–164 at scan commit)
- **Proposed solution corrected**: Original proposed fix used `bfs_depth.get()` which is semantically incorrect — `bfs_depth` records depth levels while `bfs_order.index()` returns list positions; these differ for sibling nodes at the same depth. The correct fix uses a `bfs_pos` position-lookup dict built from `bfs_order`.
- **Dependencies**: BUG-530 is satisfied (completed); ENH-541 is active with correct backlink
- **Tests**: `scripts/tests/test_ll_loop_display.py` covers `_render_fsm_diagram()`; no new tests needed

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: O(n) index() calls at info.py:394-395

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; noted `info.py:155` `bfs_order.index()` as fix target
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d766fe-2cc3-467b-a046-6a331a5941d9.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d766fe-2cc3-467b-a046-6a331a5941d9.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d766fe-2cc3-467b-a046-6a331a5941d9.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl` — VALID: `bfs_order.index()` calls confirmed at lines 394–395; `bfs_pos` dict not yet added; Verification Notes corrected solution (bfs_pos not bfs_depth) already present
- `/ll:verify-issues` - 2026-03-06T07:14:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e7a87dd5-a8d5-4b8f-9271-78a1114bf527.jsonl` — VALID: `bfs_order.index()` still at lines 394–395; corrected `bfs_pos` solution in Verification Notes is accurate
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `bfs_order.index()` confirmed at `info.py:437-438` (shifted from 394-395); `bfs_pos` dict not yet added

---

## Blocked By

- ENH-540
- ENH-541

---

## Status

**Open** | Created: 2026-03-03 | Priority: P4
