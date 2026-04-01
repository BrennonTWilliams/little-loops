---
discovered_commit: 8c6cf90
discovered_branch: main
discovered_date: 2026-03-19T00:00:00Z
discovered_by: audit-architecture
focus_area: large-files
confidence_score: 100
outcome_confidence: 71
---

# ENH-839: Split layout.py diagram rendering into focused modules

## Summary

Architectural issue found by `/ll:audit-architecture`.

`cli/loop/layout.py` is the largest source file at 1,617 lines. It contains 3 classes and 23 functions mixing graph algorithms, box rendering, and diagram composition into a single module.

## Current Behavior

`cli/loop/layout.py` (1,617 lines) mixes three distinct concerns in a single file: graph algorithms (topology detection, layer assignment, edge crossing minimization), box rendering (individual state box drawing with Rich-style formatting), and diagram composition (orchestrating full diagram output). Changes to any one concern require navigating the entire file, and risk unintended coupling with the other two areas.

## Expected Behavior

The layout functionality is organized into a `layout/` subpackage with three focused modules: `graph.py` for graph algorithms, `boxes.py` for box rendering, and `__init__.py` for diagram composition and orchestration. Each module is independently readable and modifiable without requiring comprehension of the full 1,617-line file. Public behavior and visual output remain identical.

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

## Motivation

The monolithic `layout.py` creates friction for contributors working on any one of the three concern areas. Developers must navigate 1,617 lines to safely modify rendering behavior, increasing the risk of accidental regressions across unrelated areas. Splitting into focused modules enables targeted changes with lower cognitive overhead, clearer test boundaries, and faster code reviews. This is a pure internal refactor with no user-facing behavioral change.

## Proposed Solution

Split into a `layout/` subpackage or three focused modules:

### Suggested Approach

1. Extract graph algorithm classes and helpers into `layout_graph.py` (or `layout/graph.py`)
2. Extract box rendering functions into `layout_boxes.py` (or `layout/boxes.py`)
3. Keep diagram composition as the main orchestrator in `layout.py` (or `layout/__init__.py`)
4. Update imports in `cli/loop/info.py` which is the primary consumer

## Scope Boundaries

- Out of scope: any changes to rendering behavior or visual output — this is a pure structural refactor
- Out of scope: performance optimization or algorithmic improvements to graph or box logic
- Out of scope: changes to other CLI modules outside `cli/loop/layout*`
- Out of scope: public-facing API changes — `info.py` import path may change but the callable interface stays the same

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` → split into `layout/` subpackage (`__init__.py`, `graph.py`, `boxes.py`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` — primary consumer; imports will need updating to new subpackage paths
- `scripts/little_loops/cli/loop/_helpers.py:324` — imports `_render_fsm_diagram`; must be updated

### Similar Patterns
- N/A — no other modules in the codebase have a similar splitting candidate

### Tests
- `scripts/tests/test_ll_loop_display.py` — directly imports from `little_loops.cli.loop.layout`; import paths must be updated after split

### Documentation
- N/A — no docs reference internal `layout` module structure

### Configuration
- N/A

## Implementation Steps

1. Create `scripts/little_loops/cli/loop/layout/` directory with `__init__.py`
2. Extract graph algorithm classes (`TopologyDetector`, `LayerAssigner`, `CrossingMinimizer`) and helpers (`_bfs_order`, `_trace_main_path`, `_classify_edges`, `_collect_edges`) into `layout/graph.py`
3. Extract box rendering functions (`_draw_box`, `_compute_box_sizes`, `_compute_display_labels`, `_box_inner_lines`, `_get_state_badge`, `_badge_display_width`) into `layout/boxes.py`
4. Move diagram composition functions (`_render_layered_diagram`, `_render_fsm_diagram`, `_render_horizontal_simple`, `_colorize_diagram_labels`) into `layout/__init__.py` as orchestrator
5. Update imports in `cli/loop/info.py` and any other callers to use new subpackage paths
6. Run test suite to verify no regressions in diagram output

## Impact

- **Priority**: P3 — Non-critical quality improvement; no user-facing impact, addresses maintainability debt
- **Effort**: Medium — Requires careful extraction of interdependent functions across 3 concern areas plus import tracing
- **Risk**: Low — Pure internal refactor with no behavioral changes; well-contained within `cli/loop/` module
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Verification Notes

**Verified**: 2026-04-01 | **Verdict**: NEEDS_UPDATE

- ✅ File `scripts/little_loops/cli/loop/layout.py` exists at **1,630 lines** (was 1,617 — grew 13 lines)
- ✅ 3 classes confirmed: `TopologyDetector` (line 280), `LayerAssigner` (line 325), `CrossingMinimizer` (line 418)
- ⚠️ `_render_2d_diagram` no longer exists — function was renamed/restructured. `_render_fsm_diagram` at line 1434.
- ⚠️ **Function count**: 19 top-level defs + 3 classes
- ⚠️ **Integration Map incomplete**: `_helpers.py` imports `_render_fsm_diagram` from `layout` — must be updated during split
- No `layout/` subpackage created. Enhancement not yet applied.

## Session Log
- `/ll:verify-issues` - 2026-04-01T17:45:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:08:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:format-issue` - 2026-03-19T23:06:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`

---

## Status

**Open** | Created: 2026-03-19 | Priority: P3
