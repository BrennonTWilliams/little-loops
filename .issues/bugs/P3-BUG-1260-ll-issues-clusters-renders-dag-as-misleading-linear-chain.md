---
captured_at: "2026-04-22T21:44:08Z"
discovered_date: 2026-04-22
discovered_by: capture-issue
---

# BUG-1260: `ll-issues clusters` renders DAG as misleading linear chain

## Summary

The `clusters` subcommand visualizes dependency clusters as a vertical stack of boxes connected by arrows. However, `_render_cluster_diagram` draws `│ ▼` connectors between **every pair of consecutive nodes in topological sort order**, not just nodes with a real direct edge. The edge label ("blocks") only appears when a real relationship exists, but the arrow is always drawn. This makes a complex multi-root DAG look like a single long linear chain, hiding the actual branching structure.

## Current Behavior

A cluster with 5 independent root nodes (ENH-1092, ENH-753, FEAT-1002, FEAT-1116, FEAT-918) and many nodes with multiple parents is rendered as:

```
ENH-1092 → ENH-753 → FEAT-1002 → FEAT-1116 → FEAT-918 → ENH-494 → ...
```

Arrows between unrelated nodes (e.g., ENH-1092 → ENH-753) are drawn without labels, making them indistinguishable from real edges at a glance. Only the very last two arrows (FEAT-962 →(blocks) FEAT-957 →(blocks) FEAT-992) are labeled.

## Expected Behavior

Arrows should only be drawn between nodes that share a direct blocking relationship. Independent root nodes should each appear without a connector to the next root. The diagram should convey the DAG structure, not a flat sequence.

## Motivation

The linear chain visualization actively misleads. Users inferring dependency structure from the diagram will believe ENH-1092 directly blocks ENH-753, etc. — none of which is true. This undermines the core purpose of the `clusters` command.

## Steps to Reproduce

1. Run `ll-issues clusters`
2. Observe Cluster 1 with multiple root nodes displayed as a chain with unlabeled arrows between them
3. Check that those roots (e.g., ENH-1092 and ENH-753) have no direct blocking relationship in their frontmatter

## Root Cause

- **File**: `scripts/little_loops/cli/issues/clusters.py`
- **Anchor**: `in _render_cluster_diagram`, lines 149–162
- **Cause**: The loop `for i in range(n - 1)` iterates over all consecutive node pairs in the topologically-sorted list and unconditionally places `│` and `▼` in the grid. The `edge_map` lookup on line 159 only adds a colored label when an edge exists — it does not suppress the connector. Every pair of topo-adjacent nodes gets an arrow regardless of whether they are directly related.

```python
for i in range(n - 1):
    a_id = ordered_ids[i]
    b_id = ordered_ids[i + 1]
    gap_row = box_start[a_id] + _BOX_HEIGHT
    if gap_row < grid_h:
        grid[gap_row][center_col] = "│"   # always drawn
    if gap_row + 1 < grid_h:
        grid[gap_row + 1][center_col] = "▼"  # always drawn
    rel = edge_map.get((a_id, b_id)) or edge_map.get((b_id, a_id))
    if rel:
        ...  # only label, never suppresses the arrow
```

## Proposed Solution

Conditionally draw the connector only when a real edge exists between the two consecutive nodes:

```python
rel = edge_map.get((a_id, b_id)) or edge_map.get((b_id, a_id))
if rel:
    if gap_row < grid_h:
        grid[gap_row][center_col] = "│"
    if gap_row + 1 < grid_h:
        grid[gap_row + 1][center_col] = "▼"
    color = EDGE_COLOR.get(rel, "37")
    arrow_labels[gap_row] = colorize(f" {rel}", color)
```

For a fuller fix, consider a multi-column layout that can render multiple branches side-by-side for nodes with multiple parents/children. The simple single-column fix stops drawing false edges; a tree/DAG layout would be a follow-up enhancement.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/clusters.py` — `_render_cluster_diagram`, lines ~149–162

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py` — wires `clusters` subcommand
- `scripts/tests/test_issues_cli.py` — may have snapshot tests for cluster output

### Similar Patterns
- `scripts/little_loops/cli/loop/layout.py` — `_draw_box` is borrowed by clusters; similar grid rendering

## Implementation Steps

1. In `_render_cluster_diagram`, gate the `│`/`▼` placement on `rel` being non-None
2. Update or add tests in `test_issues_cli.py` verifying no arrows appear between unrelated consecutive nodes
3. Manually verify with `ll-issues clusters` that independent root nodes appear without connectors

## Impact

- **Priority**: P3 — Misleading output; no data corruption
- **Effort**: Small — one-line conditional change for the basic fix
- **Risk**: Low — purely cosmetic/rendering change
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `clusters`, `visualization`, `captured`

## Status

**Open** | Created: 2026-04-22 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-22T21:44:08Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7542f113-71e7-4fa6-a71a-914c65cf0077.jsonl`
