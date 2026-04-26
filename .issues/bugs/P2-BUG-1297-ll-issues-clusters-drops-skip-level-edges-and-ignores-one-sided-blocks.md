---
captured_at: "2026-04-26T23:28:16Z"
discovered_date: 2026-04-26
discovered_by: capture-issue
---

# BUG-1297: `ll-issues clusters` drops skip-level edges and ignores one-sided `blocks:` declarations

## Summary

Two bugs in `ll-issues clusters` produce incomplete dependency diagrams. First, `_render_cluster_diagram()` only inspects consecutive node pairs in topological order, silently omitting any edge where the source and target are non-adjacent (fan-out, fan-in, diamond). Second, `DependencyGraph.from_issues()` only processes `issue.blocked_by`, so edges declared only via `blocks:` frontmatter (without a matching `blocked_by:` on the target) are never added to the graph.

## Context

Identified from plan `~/.claude/plans/ll-issues-clusters-cli-output-synthetic-parasol.md`, which provides detailed root cause analysis, worked examples, and a complete fix specification.

## Root Cause

### Root Cause 1 — Rendering drops non-consecutive edges (`clusters.py:143-155`)

`_render_cluster_diagram()` iterates `range(n - 1)` and checks only the pair `(ordered_ids[i], ordered_ids[i+1])`. Edges between non-adjacent nodes exist in `edge_map` but are never rendered.

**Example (fan-out):**
- Issues: A, B, C; edges: A→B, A→C; topo order: [A, B, C]
- `edge_map`: `{(A,B): "blocks", (A,C): "blocks"}`
- Loop checks (A,B) → renders ✓; checks (B,C) → no edge (correct); A→C silently omitted ✗

Affects any cluster with branching: fan-out, fan-in, or diamond shapes.

**File:** `scripts/little_loops/cli/issues/clusters.py:143-155`

### Root Cause 2 — `from_issues()` ignores `issue.blocks` (`dependency_graph.py:93-108`)

`DependencyGraph.from_issues()` only iterates `issue.blocked_by`. If an issue declares a relationship via `blocks:` without a corresponding `blocked_by:` on the target, the edge is never added to `graph.blocks`. Since `_cluster_edges()` only reads `graph.blocks`, those edges are completely absent from both text and JSON output.

**File:** `scripts/little_loops/dependency_graph.py:93-108`

## Steps to Reproduce

**Bug 1 (skip-level edges):** Create three issues where A blocks both B and C. Run `ll-issues clusters`. The A→C edge is absent from the diagram even though it exists in `edge_map`.

**Bug 2 (one-sided `blocks:`):** Create issue A with `blocks: [B]` in frontmatter but no `blocked_by:` on issue B. Run `ll-issues clusters`. The A→B edge is missing entirely from both text and JSON output.

## Proposed Fix

### Fix 1 — Append skip-edge annotations below the diagram

After the existing grid rendering in `_render_cluster_diagram()`, compute a `pos` mapping from id → sorted index. Find all edges in `edge_map` where `pos[t] - pos[f] > 1` (skip edges). Append them as annotated lines:

```python
# After: while lines and not lines[-1].strip(): lines.pop()
pos = {id_: i for i, id_ in enumerate(ordered_ids)}
skip_edges = [
    (f, t, r)
    for (f, t), r in sorted(edge_map.items())
    if pos[t] - pos[f] > 1
]
if skip_edges:
    lines.append("")
    for f, t, r in skip_edges:
        color = EDGE_COLOR.get(r, "37")
        lines.append(f"  {f} {colorize('→', color)} {t}  ({r})")
```

The existing consecutive-arrow grid is unchanged; skip-level edges get a clear text listing below the diagram.

### Fix 2 — Process `issue.blocks` in `from_issues()`

After the existing `blocked_by` loop (line 108), add a second loop over `issue.blocks` with a guard to avoid double-adding symmetrically declared edges:

```python
for issue in issues:
    for blocked_id in issue.blocks:
        if blocked_id in completed:
            continue
        if blocked_id not in all_issue_ids:
            if all_known_ids is None or blocked_id not in all_known_ids:
                logger.warning(
                    f"Issue {issue.issue_id} blocks unknown issue {blocked_id}"
                )
            continue
        if issue.issue_id not in graph.blocked_by.get(blocked_id, set()):
            graph.blocked_by[blocked_id].add(issue.issue_id)
            graph.blocks[issue.issue_id].add(blocked_id)
```

### Fix 3 — Add fan-out rendering test

Add a test in `scripts/tests/test_issues_cli.py` (after `test_clusters_no_arrows_between_independent_roots`, ~line 3438) asserting that a fan-out cluster (A blocks B and A blocks C) shows both edge annotations in text output.

## Implementation Steps

1. Apply Fix 1 in `scripts/little_loops/cli/issues/clusters.py` — append skip-edge lines after diagram
2. Apply Fix 2 in `scripts/little_loops/dependency_graph.py` — add `issue.blocks` loop after `blocked_by` loop
3. Add fan-out test in `scripts/tests/test_issues_cli.py`
4. Run `python -m pytest scripts/tests/test_issues_cli.py -k "clusters" -v` — all must pass
5. Manual smoke: `ll-issues clusters` on a project with fan-out cluster; verify A→C edge appears

## Affected Files

| File | Change |
|------|--------|
| `scripts/little_loops/cli/issues/clusters.py` | Fix 1: append skip-edges after diagram |
| `scripts/little_loops/dependency_graph.py` | Fix 2: also process `issue.blocks` |
| `scripts/tests/test_issues_cli.py` | Fix 3: add fan-out rendering test |

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Dependency graph and cluster rendering architecture |
| architecture | docs/reference/API.md | `DependencyGraph.from_issues()` public API |

## Labels

`bug`, `ll-issues`, `clusters`, `rendering`, `dependency-graph`, `captured`

---

## Status

**Open** | Created: 2026-04-26 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-04-26T23:28:16Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e50c6bce-0407-46f5-8b96-1044f97de9cd.jsonl`
