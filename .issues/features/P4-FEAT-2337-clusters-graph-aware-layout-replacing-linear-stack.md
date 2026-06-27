---
id: FEAT-2337
title: 'll-issues clusters: replace linear box-stack with a graph-aware layout'
type: FEAT
priority: P4
status: open
captured_at: '2026-06-26T23:56:00Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- ENH-2335
- ENH-2336
labels:
- captured
- cli
- ll-issues
- clusters
- output-styling
---

# FEAT-2337: `ll-issues clusters` — graph-aware layout to replace the linear box-stack

## Summary

The root weakness of `clusters` is that it renders a **graph** as a **linear vertical
stack** and only draws arrows between *consecutive* boxes; every other edge is demoted
to a flat text "skip-edge" list. For hub/star topologies this collapses entirely —
the structure the command exists to show becomes a text dump. Replace the layout with
one that fits dependency graphs (indented tree and/or adjacency-grouped list),
optionally keeping boxes only for small clusters.

## Current Behavior

- **Linear stack is the wrong shape (A1).** `_render_cluster_diagram` topo-sorts the
  cluster into a vertical stack and draws an arrow only between consecutive boxes
  (`clusters.py:254-267`). Non-consecutive edges are appended as a flat text list
  (`clusters.py:280-289`).
- **Hub topologies collapse.** Measured on the live backlog: Cluster 1 (24 issues,
  EPIC-1463 + ~10 `parent` children) draws ~3 inline arrows and dumps **31 edges**
  into the skip-edge list. The diagram conveys almost none of the actual structure.
- **False adjacency (A2).** Consecutive boxes with no edge still get two blank gap
  rows, visually implying a relationship that doesn't exist; stack order (topo, then
  alphabetical) is the only thing connecting them.

## Expected Behavior

`ll-issues clusters` should render all dependency edges in the **primary** layout — no edge silently demoted to a trailing skip-edge list:

- An indented dependency tree (or adjacency-grouped list) replaces the flat vertical box-stack for clusters with complex topology.
- Hub/parent hierarchies (e.g. one EPIC with many `parent:` children) show depth naturally; no false-adjacency between unrelated consecutive boxes.
- Cycles are represented safely (reuse `_topo_sort_cluster`'s `has_cycle` flag) without breaking the layout.
- `--json` output is unchanged.
- If `--layout {tree,list,boxes}` is added, `tree` is the new default; the flag is documented and each value is tested.

## Proposed Solution

Replace or augment `_render_cluster_diagram`. Options, roughly increasing cost:

1. **Indented dependency tree** rooted at hub/sink nodes — fits `parent` /
   `blocked_by` DAGs far better than a flat stack and shows depth naturally. Handle
   multiple roots and cycles (the existing `_topo_sort_cluster` already detects
   cycles and returns `has_cycle`).
2. **Adjacency-grouped compact list** — per issue, list its edges inline
   (`ENH-2191 → depends_on: ENH-2184, ENH-2185, FEAT-2186`), eliminating the
   skip-edge dump. (Overlaps with ENH-2336's compact mode; this is the richer,
   graph-complete form.)
3. **Hybrid by size** — keep the current boxes only for small clusters (≤ ~5 nodes),
   auto-switch to tree/list above that threshold.

Pick one as the new default (tree is the strongest candidate for these DAGs), and
consider exposing `--layout {tree,list,boxes}` so callers can choose. Coordinate the
default with ENH-2336's `--compact` so the two compact paths don't diverge.

## Implementation Steps

1. Audit `_render_cluster_diagram` and `_topo_sort_cluster` in `clusters.py`; map all call sites and understand cycle-detection output.
2. Implement indented dependency-tree renderer rooted at hub/sink nodes; handle multiple roots and cycle marking.
3. Wire new renderer into `_render_cluster_diagram`; apply hybrid threshold (boxes only for ≤ ~5-node clusters).
4. Add optional `--layout {tree,list,boxes}` flag in `__init__.py:398-441`; set `tree` as new default.
5. Coordinate `--layout` default with ENH-2336's `--compact` to avoid diverging compact paths.
6. Write tests covering hub topology, multi-root DAGs, and cyclic clusters under `scripts/tests/`.

## Acceptance Criteria

- For a hub cluster (e.g. one EPIC with many `parent` children), every edge is
  represented in the primary layout — no edges silently relegated to a trailing list
  that the main diagram omits.
- No false-adjacency artifact: visually adjacent items are actually related.
- Cycles are represented without breaking the layout (reuse `_topo_sort_cluster`'s
  `has_cycle`).
- `--json` output is unchanged.
- If `--layout` is added, each value is documented and tested; a sensible default is
  chosen and noted in help.
- Tests cover hub topology, multi-root, and cyclic clusters.

## Out of Scope

- Legend / palette / filter echo (ENH-2335).
- Scoping flags and per-cluster header enrichment (ENH-2336) — though the compact
  list form may be shared.

## Integration Map

- `scripts/little_loops/cli/issues/clusters.py` — new layout renderer(s) replacing or
  alongside `_render_cluster_diagram`; reuse `_get_components`, `_cluster_edges`,
  `_topo_sort_cluster`.
- `scripts/little_loops/cli/issues/__init__.py:398-441` — optional `--layout` flag.
- `scripts/little_loops/cli/loop/layout.py` — current `_draw_box` primitive (only used
  if boxes are retained for small clusters).
- Tests under `scripts/tests/`.

## Impact

- **Priority**: P4 — Largest-effort item and the command is functional today; the
  payoff is high (it fixes the core "graph rendered as a list" problem) but it is not
  blocking. Sequence after ENH-2335/ENH-2336.
- **Effort**: Medium-Large — new rendering model, root/cycle handling, and broader
  test coverage.
- **Risk**: Medium — changes the command's whole visual model; `--json` consumers are
  insulated, but anyone parsing text output would be affected.
- **Breaking Change**: No (text layout change only; JSON contract preserved).

---
**Open** | Created: 2026-06-26 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-06-27T01:46:26 - `d17000fe-362f-45af-a322-565b1890ad14.jsonl`
