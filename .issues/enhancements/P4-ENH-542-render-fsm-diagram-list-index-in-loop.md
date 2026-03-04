---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# ENH-542: `_render_fsm_diagram` Uses O(n) `list.index()` Inside Edge-Classification Loop

## Summary

`_render_fsm_diagram` classifies edges as forward vs back edges by calling `bfs_order.index(src)` and `bfs_order.index(dst)` inside the edge loop. Both are O(n) list scans. The function already builds `bfs_depth: dict[str, int]` during BFS traversal that maps state names to their depth, providing the same position information in O(1) lookup. The `bfs_depth` dict is not used in the edge-classification code.

## Location

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Line(s)**: 155–164 (at scan commit: 47c81c8)
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

```python
for i, (src, dst, label) in enumerate(edges):
    if i in main_consumed:
        continue
    src_pos = bfs_depth.get(src, len(bfs_order))   # O(1), was O(n) × 2
    dst_pos = bfs_depth.get(dst, len(bfs_order))   # O(1), was O(n) × 2
    if dst == src or dst_pos < src_pos:
        back_edges.append((src, dst, label))
    else:
        branches.append((src, dst, label))
```

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

1. Replace `bfs_order.index(src) if src in bfs_order else len(bfs_order)` with `bfs_depth.get(src, len(bfs_order))`
2. Apply same replacement for `dst`
3. Confirm `ll-loop show` diagram output is visually identical

## Impact

- **Priority**: P4 — Minor performance; primarily code clarity (using the right data structure)
- **Effort**: Small — 2-line change
- **Risk**: Low — Semantically identical; `bfs_depth` and `bfs_order.index` return the same position values
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | CLI interface — FSM diagram rendering via `ll-loop show` (line 1381) |
| `docs/guides/LOOPS_GUIDE.md` | Loop inspection and diagram walkthrough (line 191) |

## Labels

`enhancement`, `ll-loop`, `performance`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; noted `info.py:155` `bfs_order.index()` as fix target
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-03 | Priority: P4
