# FEAT-670: FSM Diagram Adaptive Layout Engine — Implementation Plan

**Date:** 2026-03-11
**Issue:** `.issues/features/P3-FEAT-670-fsm-diagram-adaptive-layout-engine.md`
**Action:** implement

---

## Research Summary

- Current renderer (`info.py:255-1027`) uses a fixed two-row horizontal layout
- All states laid out left-to-right; no topology awareness
- Existing loop configs: `issue-refinement` (6-state cyclic), `fix-quality-and-tests` (5-state cyclic)
- Graph algorithms in `dependency_graph.py` provide DFS/BFS patterns to adapt
- Self-loop rendering (`↺`) already works but overwrites when multiple self-loops exist on same state

## Architecture Decision

**Approach:** Sugiyama-based layered layout with topology detection for strategy selection.

The new `layout.py` module will contain:
1. All diagram rendering logic extracted from `info.py:255-1027`
2. New topology detection and layout algorithm classes
3. Re-export of `_render_fsm_diagram` from `info.py` for backward compatibility

---

## Phase 1: Extract Layout Module

### 1.1 Create `scripts/little_loops/cli/loop/layout.py`

Move these from `info.py`:
- `_EDGE_LABEL_COLORS` (255-262)
- `_colorize_label` (265-279)
- `_colorize_diagram_labels` (282-295)
- `_box_inner_lines` (303-358)
- `_render_fsm_diagram` (367-469)
- `_render_2d_diagram` (472-1027)

Add imports:
```python
from __future__ import annotations
import re
from collections import deque
from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.cli.output import terminal_width, colorize
```

### 1.2 Update `info.py` re-export

Replace extracted code with:
```python
from little_loops.cli.loop.layout import _render_fsm_diagram  # noqa: F401
```

This preserves:
- `test_ll_loop_display.py:14` import
- `_helpers.py:324` lazy import
- `test_ll_loop_commands.py` patches

### Success Criteria
- [ ] `layout.py` created with all extracted functions
- [ ] `info.py` re-exports `_render_fsm_diagram`
- [ ] All existing tests pass with no changes

---

## Phase 2: Implement Topology Detection

### 2.1 `TopologyDetector` class

```python
class TopologyDetector:
    """Classify FSM graph topology for layout strategy selection."""

    def __init__(self, states: dict[str, StateConfig], initial: str):
        ...

    def classify(self) -> str:
        """Return 'linear', 'tree', or 'general'."""
        ...

    @property
    def back_edges(self) -> list[tuple[str, str, str]]:
        """Edges to ancestors (cycles)."""
        ...
```

DFS classification:
- **Linear:** Every node has at most 1 outgoing non-self-loop, non-back edge, and at most 1 incoming non-back edge
- **Tree:** DAG + every node has in-degree ≤ 1 (after removing back-edges)
- **General:** Everything else (Sugiyama needed)

### Success Criteria
- [ ] TopologyDetector correctly classifies 2-state, linear, branching, and cyclic FSMs

---

## Phase 3: Implement Sugiyama Layout Pipeline

### 3.1 `LayerAssigner`

Longest-path layer assignment + Coffman-Graham width constraint:
- `W = floor((terminal_width - margin) / (max_node_width + gap))`
- If W < 2, fall back to pure vertical

### 3.2 `CrossingMinimizer`

Barycenter heuristic with 3 sweeps (top-down, bottom-up, top-down).

### 3.3 `CoordinateAssigner`

Map layers + orderings to character row/column positions:
- Each layer = a vertical row of boxes
- Boxes within a layer are placed side-by-side horizontally
- Vertical arrows (`│▼`) connect layers

### Success Criteria
- [ ] Layer assignment respects terminal width
- [ ] Crossing minimization reduces visual complexity
- [ ] Coordinate assignment produces non-overlapping box positions

---

## Phase 4: Implement Rendering

### 4.1 Vertical linear rendering

For linear chains: top-to-bottom boxes with `│▼` arrows and edge labels.

### 4.2 Layered rendering

For general topologies:
- Boxes placed per layer assignment
- Forward edges as vertical `│▼` arrows between layers
- Horizontal edges within same layer
- Back-edges as left-margin vertical arrows with labels

### 4.3 Self-loop fix

Multiple self-loops on same state: render all labels (e.g., `↺ partial, error`) instead of overwriting.

### 4.4 Back-edge routing

Left-margin arrows for non-self cycles:
- Vertical line from source row down to target row
- Label on the line
- Arrow tip (▲) at target

### Success Criteria
- [ ] Linear chains render vertically
- [ ] Branching FSMs render branches side-by-side below branch point
- [ ] Fan-in states visually clear
- [ ] Back-edges render as labeled margin arrows to correct target
- [ ] Multiple self-loops all displayed
- [ ] No horizontal overflow

---

## Phase 5: Refactor `_render_2d_diagram`

Replace the current monolithic renderer with the Sugiyama pipeline:

```python
def _render_2d_diagram(...) -> str:
    detector = TopologyDetector(fsm_states, initial)
    topology = detector.classify()

    if topology == 'linear':
        return _render_linear(...)

    # General layered layout
    layers = LayerAssigner(edges, initial).assign()
    ordering = CrossingMinimizer(layers, edges).minimize()
    coords = CoordinateAssigner(ordering, box_sizes).assign()

    # Render to character grid
    ...
```

The signature of `_render_fsm_diagram` and `_render_2d_diagram` remain unchanged.

### Success Criteria
- [ ] Both loop configs render correctly
- [ ] All existing tests pass or are updated

---

## Phase 6: Update Tests

### 6.1 Update `test_main_flow_order` (line 771)

Rewrite to assert top-to-bottom vertical ordering for linear chains instead of left-to-right.

### 6.2 Update `test_issue_refinement_git_topology` (line 921)

Assert:
- Back-edges from `check_commit` and `commit` route to `evaluate` (correct target)
- Both `↺ partial` and `↺ error` (or `↺ success`) self-loops appear for `evaluate`

### 6.3 Add new topology-specific tests

- 2-state linear (verify vertical rendering)
- 4-state linear (verify vertical rendering)
- Diamond pattern (fan-out + fan-in)
- Fan-in with 3+ paths
- Terminal-width overflow (assert no line exceeds `terminal_width()`)

### 6.4 Update `test_linear_off_path_chain_all_states_visible`

This test (line 861) has a 5-state FSM that should now render using the layered layout since it has branches + back-edges. Update assertions if layout changes from horizontal to vertical.

### Success Criteria
- [ ] All 16 existing tests pass (updated as needed)
- [ ] New topology tests added and passing
- [ ] No horizontal overflow in any test

---

## Implementation Order

1. Extract to `layout.py` (Phase 1) — verify all tests pass
2. Add `TopologyDetector` (Phase 2)
3. Add layout pipeline classes (Phase 3)
4. Implement vertical linear rendering (Phase 4.1) — update `test_main_flow_order`
5. Implement layered rendering (Phase 4.2-4.4)
6. Wire into `_render_2d_diagram` (Phase 5)
7. Update and add tests (Phase 6)
8. Verify both loop configs render correctly

## Risk Assessment

- **Low risk**: Display-only change, no FSM execution impact
- **Main risk**: Breaking existing test assertions that depend on horizontal layout
- **Mitigation**: Phase 1 extraction verifies no regressions before layout changes
