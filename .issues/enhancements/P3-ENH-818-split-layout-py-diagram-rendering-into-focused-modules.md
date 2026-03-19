---
discovered_commit: 8c6cf90
discovered_branch: main
discovered_date: 2026-03-19T00:00:00Z
discovered_by: audit-architecture
focus_area: large-files
---

# ENH-818: Split layout.py diagram rendering into focused modules

## Summary

Architectural issue found by `/ll:audit-architecture`.

`cli/loop/layout.py` is the largest source file at 1,617 lines. It contains 3 classes and 23 functions mixing graph algorithms, box rendering, and diagram composition into a single module.

## Location

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Line(s)**: 1-1617 (entire file)
- **Module**: `little_loops.cli.loop.layout`

## Finding

### Current State

The file contains three distinct concern areas:

1. **Graph algorithms** (classes `TopologyDetector`, `LayerAssigner`, `CrossingMinimizer` + helpers like `_bfs_order`, `_trace_main_path`, `_classify_edges`, `_collect_edges`) — topology detection, layer assignment, edge crossing minimization
2. **Box rendering** (`_draw_box`, `_compute_box_sizes`, `_compute_display_labels`, `_box_inner_lines`, `_get_state_badge`, `_badge_display_width`) — individual state box drawing with Rich-style formatting
3. **Diagram composition** (`_render_layered_diagram`, `_render_fsm_diagram`, `_render_horizontal_simple`, `_colorize_diagram_labels`, `_colorize_label`, `_edge_line_color`) — orchestrating full diagram output from boxes and edges

### Impact

- **Development velocity**: Difficult to work on diagram rendering without understanding the full 1,617-line file
- **Maintainability**: Changes to graph algorithms risk breaking box rendering and vice versa
- **Risk**: Low runtime risk, but high cognitive load for contributors

## Proposed Solution

Split into a `layout/` subpackage or three focused modules:

### Suggested Approach

1. Extract graph algorithm classes and helpers into `layout_graph.py` (or `layout/graph.py`)
2. Extract box rendering functions into `layout_boxes.py` (or `layout/boxes.py`)
3. Keep diagram composition as the main orchestrator in `layout.py` (or `layout/__init__.py`)
4. Update imports in `cli/loop/info.py` which is the primary consumer

## Impact Assessment

- **Severity**: Medium
- **Effort**: Medium
- **Risk**: Low — internal refactor, no public API changes
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

---

## Status

**Open** | Created: 2026-03-19 | Priority: P3
