# FEAT-670: Adaptive Layout Engine — Algorithm Research

**Date:** 2026-03-10
**Issue:** `.issues/features/P3-FEAT-670-fsm-diagram-adaptive-layout-engine.md`

---

## Current Implementation Analysis

The FSM diagram renderer lives in a single file: `scripts/little_loops/cli/loop/info.py`.

### How It Works Today

| Phase | Location | What It Does |
|---|---|---|
| Edge Collection | `info.py:384-401` | Iterates `fsm.states`, collects `(from, to, label)` tuples from 6 transition fields |
| BFS Ordering | `info.py:403-413` | BFS from `fsm.initial` → `bfs_order` list + `bfs_depth` dict |
| Main Path Detection | `info.py:415-433` | Greedy walk: `on_success > next > first route > default` |
| Edge Classification | `info.py:435-453` | Non-main edges split into `branches` (forward) vs `back_edges` (backward in BFS order) |
| Box Sizing | `info.py:499-554` | Computes `box_inner`, `box_width`, `box_height` per state |
| Main Path Layout | `info.py:557-573` | **Single horizontal row**, left-to-right, no wrapping |
| Off-Path Layout | `info.py:575-616` | **Single shared horizontal band** below main row |
| Grid Rendering | `info.py:626-993` | Character grid with Unicode box-drawing, arrows, U-route back-edges |
| Colorization | `info.py:282-295` | ANSI regex pass for label keywords |

### Key Limitation

The layout is a **two-row, left-to-right fixed grid**. Every additional state extends width, never height. No topology detection, no row-wrapping, no vertical stacking.

---

## Algorithm Research

### 1. Sugiyama / Layered Graph Drawing (Recommended Primary Algorithm)

The dominant algorithm for hierarchical directed graph layout. Used by Graphviz `dot`, ELK, dagre, grandalf.

#### Five Phases

**Phase 1: Cycle Removal**
- FSMs almost always have cycles. The algorithm requires a DAG.
- **Approach:** DFS-based back-edge reversal — reverse edges to gray (in-stack) ancestors. O(V+E).
- Reversed edges are tracked for later rendering as back-edges.
- **FSM note:** Back-edges carry transition labels (on_failure, on_error) — reversal metadata must preserve these.

**Phase 2: Layer Assignment**
- Assign nodes to discrete layers (rows) so all edges point downward.
- **Longest-path (simplest):** `layer[v] = 1 + max(layer[predecessors])`. O(V+E). Minimizes layer count but can create long edges.
- **Network Simplex (Graphviz default):** Frames as min-cost flow, minimizes total edge length. O(V*E) but fast in practice. Better aesthetics.
- **Coffman-Graham (width-constrained):** Respects a max-width W per layer. O(V^2). **Directly solves the terminal-width constraint.**
- **Dummy nodes:** Inserted wherever an edge spans >1 layer, ensuring all edges connect adjacent layers.

**Phase 3: Crossing Minimization**
- Reorder nodes within each layer to minimize edge crossings.
- **Barycenter heuristic:** Sort layer-k nodes by average position of their neighbors in layer k-1. Sweep top-down then bottom-up, repeat 3-10x. O(V+E) per sweep.
- **Median heuristic:** Same but uses median — more robust to outliers.
- At FSM scale (2-20 nodes), exact solutions are feasible.

**Phase 4: Coordinate Assignment**
- Assign x-coordinates within each layer consistent with the crossing-minimized ordering.
- **Brandes-Kopf algorithm:** O(V+E), compact layouts by aligning nodes with neighbors.
- For ASCII: x-coordinates map directly to character column positions.

**Phase 5: Edge Routing**
- Route edges through dummy nodes as `|`, `─`, `▼`, `▲` characters.
- Back-edges (reversed in Phase 1) rendered separately in margins.

#### Complexity at FSM Scale
All phases run in microseconds for 2-20 nodes. Even NP-hard subproblems can be solved exactly at this scale.

---

### 2. Topology Detection (for Strategy Selection)

A single DFS pass (O(V+E)) classifies the graph and its edges:

| Topology | Detection | Layout Strategy |
|---|---|---|
| Linear chain | All nodes have in-degree ≤ 1, out-degree ≤ 1 | Vertical stack (top-to-bottom) |
| Tree | DAG + every node has in-degree ≤ 1 | Hierarchical with branching |
| DAG with fan-out | Any node with out-degree > 1 | Sugiyama layered |
| DAG with fan-in | Any node with in-degree > 1 | Sugiyama with convergence grouping |
| Cyclic (most FSMs) | Back-edges found during DFS | Sugiyama on DAG + margin back-edges |
| Diamond | Fan-out followed by fan-in to same node | Sugiyama, diamond auto-detected |

**DFS edge classification:**
- **Tree edge:** to unvisited node
- **Back edge:** to ancestor (in-stack) node → cycle
- **Forward edge:** to descendant already visited
- **Cross edge:** to node in different subtree

---

### 3. Terminal-Width Constraint: Coffman-Graham Algorithm

The canonical solution for width-constrained layer assignment:

1. Compute topological ordering
2. Assign nodes to layers in reverse topological order
3. For each node v: place v in the lowest layer that is (a) above all successors and (b) has fewer than W nodes
4. `W = floor(terminal_width / (avg_node_width + min_gap))`

**Properties:**
- Optimal for W=2
- Within factor (2 - 2/W) of optimal for W > 2
- O(V^2) time

**Simpler alternative:** After standard layer assignment, if a layer exceeds W, split into sub-layers with dummy edges.

---

### 4. Back-Edge Rendering Strategies

| Strategy | Description | Pros | Cons |
|---|---|---|---|
| **Left/right margin arrows** | Vertical lines in margin connecting source→target with label | No crossing of main layout; clear | Requires reserving margin columns |
| **U-route below** | Current implementation — U-shaped connectors appended below | Simple to implement | Can grow unbounded downward |
| **Inline annotation** | Self-loops as `↺ label` at the node | Compact | Only works for self-loops |
| **Duplicate node stub** | Show target node again at bottom with `...` indicator | Familiar from manual diagrams | Confusing for complex graphs |

**Recommended:** Left/right margin arrows for non-self back-edges, `↺` for self-loops (current behavior is good for self-loops).

---

### 5. Python Libraries

| Library | Layout | ASCII Output | Cycles | Notes |
|---|---|---|---|---|
| **grandalf** | Sugiyama (600 LOC) | No (coords only) | Requires manual FAS | Pure Python, hackable, focused |
| **asciidag** | git-style columns | Yes | DAG only | Port of git's graph code |
| **PHART** | 10+ strategies | Yes (Unicode/ANSI) | Claims support | Most complete; newer (Feb 2026) |
| **NetworkX** | `topological_generations` | No (matplotlib) | DAG functions | Layer assignment only |
| **pysugiyama** | Sugiyama | No | Unknown | Minimal Python impl |

**No single library does the full pipeline** (cycle detection → Sugiyama → ASCII → back-edge margins). Implementation will combine ideas from these.

---

### 6. Reference: Graphviz `dot` Internals

`dot` implements Sugiyama with:
- DFS back-edge reversal for cycles
- Network simplex for layer assignment
- Barycenter heuristic with iterative sweeps for crossing minimization
- Virtual/dummy nodes for multi-layer edge spans
- Outputs float coordinates (not ASCII) — would need discretization

---

### 7. Academic Reference

**"Visualisation of state machines using the Sugiyama method"** (Chalmers University thesis) — directly addresses FSM + Sugiyama. Key insight: FSM back-edges are semantically meaningful (carry transition labels), so reversal must preserve metadata for correct rendering.

---

## Recommended Approach for FEAT-670

### Architecture

```
FSMLoop
  │
  ▼
TopologyDetector          ← classify graph shape
  │
  ▼
LayoutStrategy (selected) ← one of: Linear, Branching, Sugiyama
  │
  ├── Phase 1: Cycle removal (DFS back-edge reversal)
  ├── Phase 2: Layer assignment (longest-path + Coffman-Graham width cap)
  ├── Phase 3: Crossing minimization (barycenter sweep)
  ├── Phase 4: Coordinate assignment (column positions)
  └── Phase 5: Edge routing
  │
  ▼
ASCIIRenderer             ← character grid painter
  ├── Box rendering (existing logic, mostly reusable)
  ├── Forward edge rendering (vertical `│▼` between layers)
  ├── Horizontal arrows (within same layer for branches)
  ├── Back-edge margin rendering (labeled `│` in left margin)
  └── Colorization (existing `_colorize_diagram_labels`)
```

### Strategy Selection

| Detected Topology | Strategy | Rendering |
|---|---|---|
| Linear chain (≤1 out-degree per node) | **Vertical stack** | Top-to-bottom boxes with `│▼` arrows |
| Simple branch (1 fan-out point, no cycles) | **Tree layout** | Branch point above, children side-by-side below |
| DAG or cyclic (general case) | **Sugiyama layered** | Full 5-phase pipeline with margin back-edges |

### Width Constraint

Use Coffman-Graham to cap nodes per layer at `W = floor((terminal_width - margin) / (max_node_width + gap))`. If terminal is too narrow for even 2 nodes side-by-side, fall back to pure vertical layout.

### Implementation Plan

1. **Extract layout logic** from `info.py` into a new module `scripts/little_loops/cli/loop/layout.py`
2. **Implement `TopologyDetector`** — DFS classification, back-edge extraction
3. **Implement `LayerAssigner`** — longest-path + Coffman-Graham width constraint
4. **Implement `CrossingMinimizer`** — barycenter heuristic (3 sweeps sufficient for FSM scale)
5. **Implement `CoordinateAssigner`** — map layers + orderings to character columns/rows
6. **Implement `BackEdgeRenderer`** — margin arrows with labels
7. **Refactor `_render_2d_diagram`** to use the new layout pipeline
8. **Update tests** in `test_ll_loop_display.py`

### Complexity Budget

At FSM scale (2-20 nodes, 3-40 edges), the entire Sugiyama pipeline completes in <1ms. No performance concerns.

---

## Key Sources

- [Sugiyama Method (disy.net)](https://blog.disy.net/sugiyama-method/)
- [Layered graph drawing (Wikipedia)](https://en.wikipedia.org/wiki/Layered_graph_drawing)
- [Coffman-Graham algorithm (Wikipedia)](https://en.wikipedia.org/wiki/Coffman%E2%80%93Graham_algorithm)
- [grandalf (GitHub)](https://github.com/bdcht/grandalf) — Python Sugiyama, ~600 LOC
- [asciidag (GitHub)](https://github.com/sambrightman/asciidag) — git-style ASCII DAG rendering
- [PHART (GitHub)](https://github.com/scottvr/phart/) — Python hierarchical ASCII rendering
- [NetworkX topological_generations](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.dag.topological_generations.html)
- [FSM + Sugiyama thesis (Chalmers)](https://publications.lib.chalmers.se/records/fulltext/161388.pdf)
- [ELK Layered algorithm](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html)
- [dagre (GitHub)](https://github.com/dagrejs/dagre) — JS Sugiyama with network simplex
