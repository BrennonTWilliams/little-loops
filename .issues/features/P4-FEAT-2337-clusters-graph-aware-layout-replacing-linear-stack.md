---
id: FEAT-2337
title: 'll-issues clusters: replace linear box-stack with a graph-aware layout'
type: FEAT
priority: P4
status: done
decision_needed: false
captured_at: '2026-06-26T23:56:00Z'
completed_at: '2026-07-14T23:25:56Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- ENH-2335
- ENH-2336
depends_on:
- ENH-2336
labels:
- captured
- cli
- ll-issues
- clusters
- output-styling
parent: EPIC-2370
confidence_score: 92
outcome_confidence: 78
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 20
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The three approaches above map to these concrete implementation options:

**Option A — Indented dependency tree (recommended default).**
> **Selected:** Option A — reuses `format_epic_tree()`'s existing tree-renderer
> pattern, generalizes cleanly to multi-root, and is the only option that
> satisfies the "no edge relegated to a trailing list" acceptance criterion for
> hub topologies; `--layout list`/`boxes` are retained as explicit alternates.

A near-identical
renderer already exists: `dependency_mapper/formatting.py:252` `format_epic_tree()`
draws `├──`/`└──` connectors (from `cli/output.py:54-61` — `BOX_ML`=`├`, `BOX_BL`=`└`,
`BOX_V`=`│`), carries an `extension` indent forward for annotation sub-lines, and is
cycle-tolerant (falls back to insertion order for nodes not covered by topo sort). It
is **single-root** (one EPIC → children), so it must be generalized to clusters'
**multi-root** case. Root selection can reuse the hub heuristic already computed at
`clusters.py:122` (`hub = min(cd.ids, key=lambda id_: (-len(neighbours.get(id_, set())), id_))`)
plus a "no incoming edge" pass (see `dependency_mapper/formatting.py`'s chain-builder
~lines 100-249 for the root-detection idiom: roots = nodes not in the set of edge
targets). Caveat: `_topo_sort_cluster` (`clusters.py:265`) returns only
`(result, has_cycle)` — its internal blocker→blocked `adj` map is **not** exposed, so a
tree renderer must rebuild adjacency from `cd.edges`/`edge_map` or extend
`_topo_sort_cluster`'s return signature.

**Option B — Adjacency-grouped compact list.** ENH-2336 **already shipped**
`_render_cluster_compact()` (`clusters.py:139-168`), wired to `--compact`/`--summary`
(`__init__.py:462-469`) and dispatched at `clusters.py:576-580`. Per the Scope Boundary
note, `--layout list` must alias/extend this single renderer rather than fork a second
one. Note `_cluster_edges` (`clusters.py:302`) dedups to **one edge per unordered pair**
(frozenset key + `_EDGE_PRIORITY`), so a graph-complete list form may need the raw
per-issue edges rather than the deduped `cd.edges`.

**Option C — Hybrid by size.** Keep `_render_cluster_diagram` (`clusters.py:352`) for
small clusters (≤ ~5 nodes) and auto-switch to tree/list above the threshold; lowest
risk since it preserves current output for the common small-cluster case.

**Recommended**: Option A (tree) as the new default, with `--layout {tree,list,boxes}`
where `list` aliases the existing ENH-2336 compact renderer (Option B) and `boxes` is
the legacy `_render_cluster_diagram`. This satisfies the Scope Boundary's
single-compact-path requirement while keeping the richer tree as default.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-14.

**Selected**: Option A — Indented dependency tree (recommended default)

**Reasoning**: `format_epic_tree()` (`dependency_mapper/formatting.py:252`) already
implements the exact `├──`/`└──` connector idiom needed and just requires
generalizing from single-root to multi-root using the existing hub heuristic
(`clusters.py:122`); this directly satisfies the "every edge in the primary
layout, no false adjacency" acceptance criteria that Options B and C only
partially address. Option B (already-shipped `_render_cluster_compact`) is
retained as `--layout list` per the Scope Boundary note rather than competing
as the default, and Option C's size-based hybrid is subsumed by exposing
`--layout {tree,list,boxes}` directly instead of an implicit threshold.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| A — Indented tree | 2/3 | 2/3 | 3/3 | 2/3 | 9/12 |
| B — Adjacency-grouped list | 3/3 | 3/3 | 3/3 | 1/3 | 10/12 |
| C — Hybrid by size | 2/3 | 2/3 | 2/3 | 1/3 | 7/12 |

**Key evidence**:
- Option A: near-identical renderer already exists (`format_epic_tree`), but is
  single-root and needs generalization; `_topo_sort_cluster` doesn't expose its
  `adj` map, so adjacency must be rebuilt from `cd.edges` (`clusters.py:265`).
- Option B: already shipped and wired (`clusters.py:139-168`, ENH-2336) with the
  highest raw score, but alone doesn't solve the hub-topology "graph rendered as
  boxes" problem the issue exists to fix — it's the compact companion, not the
  primary default.
- Option C: lowest risk but doesn't eliminate the core linear-stack weakness for
  large hub clusters — it only bounds where it applies.

Note: Option B scores highest on the 4-dimension rubric (it already exists and
is low-risk), but the rubric does not capture the issue's core requirement —
"no edge silently demoted to a trailing list" for hub topologies — which only
Option A satisfies as the *default* rendering path. Option A is selected as
default per the issue's own stated Acceptance Criteria; B remains available via
`--layout list`.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/cli/issues/clusters.py` — add `_render_cluster_tree()` alongside
  `_render_cluster_diagram()` (`clusters.py:352`) and `_render_cluster_compact()`
  (`clusters.py:139-168`); extend the render dispatch at `clusters.py:576-580` (currently
  branches only on `compact: bool`). May need to extend `_topo_sort_cluster()`
  (`clusters.py:265`) to return its internal `adj` map, or rebuild adjacency from
  `cd.edges`.
- `scripts/little_loops/cli/issues/__init__.py:440-492` — clusters subparser; add
  `--layout {tree,list,boxes}` enum-choice flag. Precedent for `choices=[...], default=`:
  `__init__.py:503-509` (`refine-status --format`). `--compact`/`--summary` live at
  `__init__.py:462-469` and must stay compatible (alias `--compact` → `--layout list`).

**Reusable Code (Similar Patterns)**
- `scripts/little_loops/dependency_mapper/formatting.py:252` — `format_epic_tree()`,
  the canonical `├──`/`└──` indented-tree renderer to model on (single-root; generalize
  to multi-root). Multi-root chain-builder in the same file (~lines 100-249) shows
  root-detection + fan-out handling.
- `scripts/little_loops/cli/output.py:54-61` — `BOX_H/V/TL/TR/BL/BR/ML/MR` connector
  constants.
- `scripts/little_loops/cli/issues/clusters.py:122` — hub/max-degree node selection,
  reusable as tree root heuristic.
- `scripts/little_loops/dependency_graph.py` — `topological_sort()` (line 301, raises on
  cycle) and `detect_cycles()` (line 355, DFS three-color returning full cycle paths) if
  richer cycle handling than `_topo_sort_cluster`'s tolerant `has_cycle` flag is wanted.

**Dependent / Insulated Paths**
- `--json` branch is fully independent of layout (`clusters.py:510-531`) — it already
  emits complete `edges: [{from,to,relationship}]` and is untouched by rendering choice,
  so the "JSON unchanged" AC is satisfied by construction.

**Tests**
- `scripts/tests/test_issues_cli.py` — existing clusters suite (26+ tests incl.
  `test_clusters_renders_skip_level_edges_for_fan_out`, `test_clusters_no_arrows_between_independent_roots`,
  `test_clusters_json_suppresses_box_diagram`). Add hub-topology, multi-root, cyclic, and
  per-`--layout`-value cases here.
- `scripts/tests/test_deps_cli.py` — `TestDepsTree` is the model for tree-output
  assertions: `patch.object(sys, "argv", [...])` + `main()` + `capsys.readouterr()`,
  asserting `"├── " in captured.out` / `"└── " in captured.out`.

**Documentation**
- `docs/reference/CLI.md:1424-1447` — `ll-issues clusters` flag table; document
  `--layout` and its default here (also missing the ENH-2336 `--cluster`/`--limit`/`--compact`
  flags in this snapshot).
- `CHANGELOG.md` — add a concrete versioned entry on ship.

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


## Resolution

Implemented Option A (indented multi-root dependency tree) as the new default
layout for `ll-issues clusters`, with `--layout {tree,list,boxes}`.

- `_render_cluster_tree()` (`scripts/little_loops/cli/issues/clusters.py`) builds
  undirected adjacency from `cd.edges`, roots each connected component at its
  highest-degree (hub) node — tie-broken by topo order — and walks it with the
  `├──`/`└──` connector idiom generalized from `format_epic_tree()`. Every edge is
  rendered in the primary layout: tree branches for the spanning tree and `⤷`
  cross-references for DAG cross-edges / cycle back-edges (deduped via a
  `rendered_edges` set so each edge prints exactly once). Cycles terminate safely
  via the `visited` set; the existing `has_cycle` warning is unchanged.
- `--layout` added in `cli/issues/__init__.py` (`choices=[tree,list,boxes]`,
  default `tree`). `--compact`/`--summary` is now an alias for `--layout list`
  (single compact path per the Scope Boundary / ENH-2336); an explicit `--layout`
  overrides `--compact`. `list` dispatches the existing `_render_cluster_compact`,
  `boxes` the legacy `_render_cluster_diagram`.
- `--json` output is untouched (independent code path) and asserted identical
  across all `--layout` values.
- Tests: new `TestIssuesCLIClustersTreeLayout` (tree-default, all-hub-edges,
  boxes/list/compact equivalence, explicit-layout-override, multi-root, DAG
  cross-edge, cycle-termination, JSON-unchanged). Pre-existing box-layout tests
  updated to opt into `--layout boxes`. Docs: `docs/reference/CLI.md` flag table +
  `CHANGELOG.md`.

Verification: `ruff check`, `mypy` clean on changed files; full suite
`14943 passed` (one pre-existing, unrelated failure in
`test_worktree_utils.py::...test_falsy_src_dir_leaves_pythonpath_uninjected`,
confirmed failing on clean HEAD).

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The `--layout list` compact rendering path in this issue and ENH-2336's `--compact`/`--summary` flag produce functionally equivalent one-line-per-issue output. To prevent two diverging compact renderers, this issue must extend or supersede ENH-2336's renderer rather than building a second one. Preferred resolution: when FEAT-2337 ships, make `--compact` an alias for `--layout list` so there is a single compact rendering path with one owner. This is why this issue declares `depends_on: ENH-2336` — ENH-2336 must ship the compact renderer first, and FEAT-2337 absorbs it. Related issue: ENH-2336.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-27T22:09:56 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:format-issue` - 2026-06-27T01:46:26 - `d17000fe-362f-45af-a322-565b1890ad14.jsonl`
- `/ll:refine-issue` - 2026-07-14T18:08:24 - `session-66390`
- `/ll:decide-issue` - 2026-07-14T18:04:17 - `session-66390`
- `/ll:manage-issue` - 2026-07-14T23:25:21 - `session-66390`
