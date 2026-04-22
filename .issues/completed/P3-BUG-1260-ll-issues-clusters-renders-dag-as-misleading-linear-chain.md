---
captured_at: "2026-04-22T21:44:08Z"
completed_at: "2026-04-22T22:52:29Z"
discovered_date: 2026-04-22
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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
- **Anchor**: `_render_cluster_diagram`, lines 114–119 (signature), 149–162 (bug)
- **Cause**: The loop `for i in range(n - 1)` iterates over all consecutive node pairs in the topologically-sorted list and unconditionally places `│` and `▼` in the grid. The `edge_map` lookup on line 159 only adds a colored label when an edge exists — it does not suppress the connector. Every pair of topo-adjacent nodes gets an arrow regardless of whether they are directly related.

```python
# clusters.py:114-119 — function signature
def _render_cluster_diagram(
    ordered_ids: list[str],
    issues_map: dict[str, IssueInfo],
    edge_map: dict[tuple[str, str], str],
    box_width: int,
) -> list[str]:

# clusters.py:149-162 — the bug
for i in range(n - 1):
    a_id = ordered_ids[i]
    b_id = ordered_ids[i + 1]
    gap_row = box_start[a_id] + _BOX_HEIGHT
    if gap_row < grid_h:
        grid[gap_row][center_col] = "│"   # line 155 — always drawn
    if gap_row + 1 < grid_h:
        grid[gap_row + 1][center_col] = "▼"  # line 157 — always drawn
    rel = edge_map.get((a_id, b_id)) or edge_map.get((b_id, a_id))  # line 159
    if rel:
        ...  # only label, never suppresses the arrow
```

`edge_map` is built in `cmd_clusters` (line 262) from `_cluster_edges` (lines 102–111), which only yields real `blocks` relationships. The topological sort (`_topo_sort_cluster`, lines 63–99) uses Kahn's algorithm seeded from `graph.blocked_by`; independent root nodes (in_degree == 0) appear consecutively in sorted order but have no edge between them.

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
- `scripts/little_loops/cli/issues/clusters.py` — `_render_cluster_diagram`, lines 149–162 (gate `│`/`▼` on `rel`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py` — wires `clusters` subcommand via `cmd_clusters`
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph` class (lines 32–110); `graph.blocked_by` feeds `_topo_sort_cluster`, `graph.blocks` feeds `_cluster_edges` → `edge_map`

### Tests
- `scripts/tests/test_issues_cli.py:3021` — `TestIssuesCLIClusters` class, 12+ test methods
- `scripts/tests/test_issues_cli.py:2978` — `issues_dir_with_deps` fixture (BUG-001→BUG-002→BUG-003, FEAT-001→FEAT-002); **no multi-root DAG fixture exists** — new fixture/test case needed for this bug

### Similar Patterns
- `scripts/little_loops/cli/loop/layout.py:557` — `_draw_box` definition (borrowed by clusters)
- `scripts/little_loops/cli/loop/layout.py:1040-1045` — conditional arrow pattern to follow: `label = forward_edge_labels.get((src, dst)); if label is not None: inter_edges.append(...)` — only draws arrows for real edges

## Implementation Steps

1. In `clusters.py:149-162`, move the `rel = edge_map.get(...)` lookup **above** the `│`/`▼` placement and gate both on `rel` being truthy (see Proposed Solution code block)
2. Add a test to `TestIssuesCLIClusters` (`test_issues_cli.py:3021`) using a new fixture with ≥2 independent root nodes (no `blocks` relationship between them); assert `"▼" not in captured.out` between those roots, following the `not in` assertion pattern at `test_issues_cli.py:3134`
3. Manually verify with `ll-issues clusters` that independent root nodes appear without connectors between them

## Impact

- **Priority**: P3 — Misleading output; no data corruption
- **Effort**: Small — one-line conditional change for the basic fix
- **Risk**: Low — purely cosmetic/rendering change
- **Breaking Change**: No

## Related Key Documentation

- `CHANGELOG.md` — documents `ll-issues clusters` feature and related bug fixes
- `README.md:405-447` — `ll-issues clusters` CLI usage reference

## Labels

`bug`, `clusters`, `visualization`, `captured`

## Resolution

**Fixed** in `scripts/little_loops/cli/issues/clusters.py` `_render_cluster_diagram`.

Moved the `rel = edge_map.get(...)` lookup above the `│`/`▼` placement and gated both connector characters on `rel` being truthy. Independent root nodes in topological sort order no longer emit false arrows between them.

Added `issues_dir_multi_root` fixture and `test_clusters_no_arrows_between_independent_roots` test to `scripts/tests/test_issues_cli.py` to cover this case.

## Status

**Closed** | Created: 2026-04-22 | Resolved: 2026-04-22 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-04-22T22:49:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b5f3384-28eb-4ee5-89e8-fa72930a2e62.jsonl`
- `/ll:confidence-check` - 2026-04-22T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffdba525-8a76-4b36-acf7-cf777c803de6.jsonl`
- `/ll:wire-issue` - 2026-04-22T22:46:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe238444-7e3f-4dd6-b772-5488e2f50306.jsonl`
- `/ll:refine-issue` - 2026-04-22T22:41:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74ff7167-2f52-41ea-83db-f23663476581.jsonl`
- `/ll:capture-issue` - 2026-04-22T21:44:08Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7542f113-71e7-4fa6-a71a-914c65cf0077.jsonl`
