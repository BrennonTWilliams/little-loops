---
id: ENH-839
title: Split layout.py diagram rendering into focused modules
type: ENH
priority: P3
status: deferred
discovered_commit: 8c6cf90
discovered_branch: main
discovered_date: 2026-03-19 00:00:00+00:00
discovered_by: audit-architecture
focus_area: large-files
confidence_score: 100
outcome_confidence: 71
milestone: refined-ready
parent: EPIC-1812
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
- **Line(s)**: 1-1645 (entire file)
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
- `scripts/little_loops/cli/loop/_helpers.py` (`_build_pinned_pane`) — imports `_render_fsm_diagram`; must be updated

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

**Verified**: 2026-06-03 | **Verdict**: VALID (line count confirmed stable)

- File `scripts/little_loops/cli/loop/layout.py` exists at **1,981 lines** (unchanged from 2026-05-31)
- 3 classes still present: `TopologyDetector`, `LayerAssigner`, `CrossingMinimizer`
- No `layout/` subpackage created; refactor plan still accurate

**Verified**: 2026-05-31 | **Verdict**: VALID (line counts refreshed)

- File `scripts/little_loops/cli/loop/layout.py` exists at **1,981 lines** (was 1,967 on 2026-05-24)
- 3 classes still present: `TopologyDetector`, `LayerAssigner`, `CrossingMinimizer`
- Refactor plan still accurate; no `layout/` subpackage yet
- File continues to grow — +14 lines since 2026-05-24 verification

**Verified**: 2026-05-24 | **Verdict**: VALID (line counts refreshed)

- File `scripts/little_loops/cli/loop/layout.py` exists at **1,967 lines** (was 1,699 on 2026-05-22)
- 3 classes still present: `TopologyDetector`, `LayerAssigner`, `CrossingMinimizer`
- Refactor plan still accurate; no `layout/` subpackage yet
- File continues to grow — +268 lines since 2026-05-22 verification

**Verified**: 2026-05-22 | **Verdict**: VALID (line counts refreshed)

- File `scripts/little_loops/cli/loop/layout.py` exists at **1,699 lines** (was 1,701 on 2026-05-17)
- 3 classes still present: `TopologyDetector`, `LayerAssigner`, `CrossingMinimizer`
- Refactor plan still accurate; no `layout/` subpackage yet
- Slow accretion continues — file is now ~80 lines larger than the 2026-04-23 baseline (1,635 → 1,699)

**Verified**: 2026-05-17 | **Verdict**: VALID (line counts refreshed)

- File `scripts/little_loops/cli/loop/layout.py` exists at **1,701 lines** (was 1,645 on 2026-05-14)
- 3 classes still present: `TopologyDetector`, `LayerAssigner`, `CrossingMinimizer`
- Refactor plan still accurate; no `layout/` subpackage yet
- Integration Map note re: `_helpers.py` import of `_render_fsm_diagram` still applies

**Verified**: 2026-05-14 | **Verdict**: VALID (line counts refreshed)

- File `scripts/little_loops/cli/loop/layout.py` exists at **1,645 lines** (was 1,635 on 2026-04-23)
- 3 classes still present: `TopologyDetector`, `LayerAssigner`, `CrossingMinimizer`
- Refactor plan still accurate; no `layout/` subpackage yet
- Integration Map note re: `_helpers.py` import of `_render_fsm_diagram` still applies

## Session Log
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-04T22:14:35 - `ab906855-95d7-4c4f-93f3-78db8cba1111.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:21:13 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:04 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:verify-issues` - 2026-05-31T20:34:10 - `52d78c58-d750-467e-9092-de587a96595e.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:18 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:ready-issue` - 2026-05-24T17:46:46 - `a0e276a3-13b8-43b1-8581-1cb2cbdbf771.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:43 - `2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:verify-issues` - 2026-05-17T17:04:58 - `907d2d29-7e38-4120-a77d-deb597ac2df4.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:04 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:54 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:05 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:18 - `5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:04:59 - `5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:02:03 - `4aa69027-63ea-4746-aed4-e426ab30885a.jsonl`
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:verify-issues` - 2026-04-03T02:58:18 - `7b02a8b8-608b-4a1c-989a-390b7334b1d4.jsonl`
- `/ll:verify-issues` - 2026-04-01T17:45:20 - `712d1434-5c33-48b6-9de5-782d16771df5.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:08:07 - `518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:format-issue` - 2026-03-19T23:06:44 - `518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`

---

## Status

**Open** | Created: 2026-03-19 | Priority: P3
