---
id: FEAT-670
type: FEAT
priority: P3
status: active
discovered_date: 2026-03-10
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 79
---

# FEAT-670: FSM Diagram Adaptive Layout Engine

## Summary

The FSM ASCII Box Diagram Generator must support any possible configuration of a Finite State Machine. Currently, it can render simple FSMs but only grows horizontally as more states are added. The layout engine needs to intelligently adapt to the FSM topology it diagrams — handling linear chains, branches, cycles, fan-out/fan-in, diamond patterns, and complex multi-path graphs.

## Use Case

A developer runs `ll-loop show <name>` on an FSM with 6+ states including branches, parallel paths, and back-edges. Instead of a garbled or impossibly wide diagram, the generator automatically selects an appropriate layout strategy — vertical for linear chains, side-by-side for branches, wrapped rows for wide graphs — producing a readable diagram that fits within terminal width regardless of FSM complexity.

## Current Behavior

The diagram renderer lays out states horizontally in a single row. Linear chains overflow terminal width. Branching FSMs with multiple outgoing transitions produce overlapping or garbled output. Complex topologies (diamonds, cycles with multiple entry points, fan-out/fan-in) are not handled gracefully.

## Expected Behavior

The layout engine should:
- Detect FSM topology (linear chain, tree, DAG, cyclic graph) and select an appropriate layout strategy
- Render linear chains vertically (top-to-bottom) to use unlimited terminal scroll space
- Place branching states side-by-side horizontally, with the branch point above
- Handle fan-out (one state → many) and fan-in (many → one state) with clear visual grouping
- Render back-edges (cycles) as labeled arrows on the margin without crossing state boxes
- Respect terminal width constraints, wrapping or reflowing as needed
- Support any valid FSM configuration without garbled output

## Motivation

The FSM diagram is the primary visual tool for understanding loop configurations. As users create more complex FSMs (hierarchical loops, multi-stage pipelines with error recovery, conditional branching), the current horizontal-only layout becomes unusable. An adaptive layout engine makes `ll-loop show` reliable for any FSM, not just trivial ones.

## Proposed Solution

**Primary algorithm:** Sugiyama/layered graph drawing (5-phase pipeline: cycle removal → layer assignment → crossing minimization → coordinate assignment → edge routing).

- **Topology detection:** DFS-based classification to select layout strategy — linear chains → vertical stack, branching → tree layout, general DAG/cyclic → full Sugiyama
- **Width constraint:** Coffman-Graham algorithm to cap nodes per layer based on terminal width: `W = floor((terminal_width - margin) / (max_node_width + gap))`
- **Back-edges:** Left/right margin arrows for cycles (with label preservation), `↺` for self-loops (existing self-loop rendering is reusable)
- **Architecture:** Extract layout logic from `info.py` into new `layout.py` module with `TopologyDetector`, `LayerAssigner`, `CrossingMinimizer`, `CoordinateAssigner`, `BackEdgeRenderer`
- **No external dependencies needed** — no single library covers the full pipeline; custom implementation combining ideas from grandalf, asciidag

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — current renderer (refactor `_render_fsm_diagram` at line 367 and `_render_2d_diagram` at line 472; function ends at line 1027)
- `scripts/little_loops/cli/loop/layout.py` — **new file** for extracted layout engine

### Helper Functions Requiring Relocation Decision
The full extraction scope from `info.py` is **lines 255-1027** (not just 367-1027):
- `info.py:255-262` — `_EDGE_LABEL_COLORS: dict[str, str]` — maps `"success"/"fail"/"error"/"partial"/"next"/"_"` to ANSI codes
- `info.py:265-279` — `_colorize_label(label: str) -> str` — keyword colorizer used by `_colorize_diagram_labels`
- `info.py:282-295` — `_colorize_diagram_labels(diagram: str) -> str` — regex post-processing pass; called as the final step of `_render_2d_diagram:1027`
- `info.py:303-358` — `_box_inner_lines(state, display_label, verbose, inner_width) -> list[str]` — per-state box content lines; called during coordinate assignment

All four must move to `layout.py`. Do not create import cycles by importing from `info.py` within `layout.py`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:1226` — `cmd_show` calls `_render_fsm_diagram`
- `scripts/little_loops/cli/loop/_helpers.py:324-326` — `run_foreground()` calls `_render_fsm_diagram` on `state_enter` events
- `scripts/little_loops/fsm/schema.py` — provides `FSMLoop`, `StateConfig`, `RouteConfig` consumed by renderer
- `scripts/little_loops/cli/output.py` — provides `terminal_width()`, `colorize()`

### Similar Patterns
- P3-ENH-666: FSM box diagram vertical layout (superseded by this issue)
- P4-ENH-542: Render FSM diagram list index in loop
- P4-ENH-654: FSM diagram active state background fill highlight

### Tests
- `scripts/tests/test_ll_loop_display.py` — imports `_render_fsm_diagram` directly at line 14 (`from little_loops.cli.loop.info import _render_fsm_diagram`); `TestRenderFsmDiagram` class at line 634 has 16 test functions
- `scripts/tests/test_ll_loop_commands.py:724` — `test_show_displays_diagram` calls `main_loop()` which internally invokes `_render_fsm_diagram`; `test_show_diagram_appears_before_states` at line 1270 does same — **both tests call through `main_loop()` and will fail post-extraction unless `info.py` re-exports `_render_fsm_diagram` from `layout.py`**

The class uses an inner `_make_fsm(self, name, initial, states)` factory that constructs `FSMLoop` directly (not via `make_test_fsm`). The module also has top-level `make_test_state` / `make_test_fsm` helpers at lines 47-95.

**Test requiring update (will break with vertical linear rendering):**
- `test_main_flow_order` (line 771) — asserts horizontal order via `result.split("\n")[1]` position comparison; assumes states appear left-to-right on line index 1; must be rewritten to assert top-to-bottom vertical ordering for linear chains

**Tests to preserve/verify (16 total in TestRenderFsmDiagram):**
- `test_single_terminal_state` (645), `test_linear_flow_shows_labels` (655), `test_next_transition_label` (675) — basic correctness
- `test_branching_fsm_shows_branches_section` (687), `test_cyclic_fsm_shows_back_edges_section` (710), `test_self_loop_annotated` (730) — complex topology
- `test_route_table_branches` (746), `test_bidirectional_back_edge_both_pipes_on_label_rows` (789), `test_multiple_off_path_states_same_depth` (813) — specific rendering
- `test_linear_off_path_chain_all_states_visible` — BUG-658 regression
- `test_issue_refinement_git_topology` (921) — 6-state cyclic regression (BUG-664); **must be updated**: assert back-edges from `check_commit` and `commit` route to `evaluate` (the correct YAML target), not to `format_issues` (the incorrect level shown in `fixed-ref-git-fsm-diagram.txt`); also assert both `↺ partial` and `↺ error` self-loops appear for `evaluate`
- 4x highlighted-state tests: `test_highlighted_state_uses_configured_color` (985), `test_highlighted_state_default_green` (1004), `test_no_highlight_state_unchanged`, `test_unknown_highlight_state_no_crash` — ANSI color assertions with `patch.object(output_mod, "_USE_COLOR", True)`

**New topology-specific tests to add** (per acceptance criteria):
- 2-state linear, 4-state linear (verify vertical rendering)
- Diamond pattern, fan-in with 3+ paths
- Terminal-width overflow — assert no line exceeds `terminal_width()` characters

### Documentation
- `docs/reference/OUTPUT_STYLING.md:136,180,184` — documents `_render_fsm_diagram`, `_colorize_diagram_labels`, `terminal_width` usage; may need updates if the public interface changes

### Configuration
- N/A

## Implementation Steps

1. Extract layout logic from `info.py:255-1027` into new `layout.py` module — includes `_EDGE_LABEL_COLORS`, `_colorize_label`, `_colorize_diagram_labels`, `_box_inner_lines`, `_render_fsm_diagram`, `_render_2d_diagram` (note: `_render_2d_diagram` ends at line 1027, not 993)
2. Implement `TopologyDetector` — DFS classification (linear/tree/DAG/cyclic), back-edge extraction with label preservation
3. Implement `LayerAssigner` — longest-path assignment + Coffman-Graham width constraint (`W = floor((terminal_width - margin) / (max_node_width + gap))`)
4. Implement `CrossingMinimizer` — barycenter heuristic with 3 top-down/bottom-up sweeps
5. Implement `CoordinateAssigner` — map layers + orderings to character column/row positions
6. Implement vertical rendering for linear chains (top-to-bottom boxes with `│▼` arrows)
7. Implement side-by-side branch rendering for fan-out states
8. Implement back-edge margin arrows (left margin for non-self cycles, `↺` for self-loops — existing self-loop rendering is reusable)
9. Refactor `_render_2d_diagram` to call the new layout pipeline
10. Update `test_ll_loop_display.py` with topology-specific test cases (2-state, linear, branching, diamond, cyclic, complex)

## Acceptance Criteria

- [ ] Linear chain FSMs render vertically (top-to-bottom) instead of horizontally
- [ ] Branching FSMs (multiple outgoing transitions) render branches side-by-side below the branch point
- [ ] Fan-in states (multiple incoming transitions) are visually clear
- [ ] Back-edges (cycles) render as labeled margin arrows routed to their **correct target state** without overlapping state boxes
- [ ] States with multiple self-loops (e.g., both `on_partial` and `on_error` returning to self) display all self-loop labels, not just the last one written
- [ ] Diagrams respect terminal width — no horizontal overflow for any supported topology
- [ ] All existing FSM loop configs in the project render correctly
- [ ] Existing diagram tests pass or are updated

> **Note on `fixed-ref-git-fsm-diagram.txt`**: This file is illustrative only and contains two known inaccuracies that the implementation must NOT replicate:
> 1. **Wrong back-edge targets**: The diagram shows back-edges from `check_commit` (on_failure/on_error) and `commit` (next) terminating at the `format_issues` level, but both transition targets in the YAML are `evaluate`. Correct rendering must route these arrows all the way up to `evaluate`.
> 2. **Missing self-loop**: `evaluate` has both `on_partial: evaluate` and `on_error: evaluate` self-loops, but the diagram only shows `↺ partial`. The current renderer silently drops `↺ error` because both labels overwrite the same cell. Both must be rendered.

## Scope Boundaries

- **In scope**: Adaptive layout algorithm, topology detection, vertical/horizontal/mixed rendering, terminal-width constraints, back-edge rendering
- **Out of scope**: Interactive/animated diagrams, export to image formats, changes to FSM execution logic, YAML config format changes

## Impact

- **Priority**: P3 — Usability improvement; current renderer works for simple cases but fails on complex FSMs
- **Effort**: Medium-High — New module extraction, 5-phase algorithm pipeline, multiple rendering strategies, test updates; isolated to diagram rendering with no execution logic changes
- **Risk**: Low — Display-only change; no impact on FSM execution, YAML format, or loop behavior
- **Breaking Change**: No

## API/Interface

N/A — display-only change. No public API additions or modifications. The internal `_render_fsm_diagram` function signature is preserved; layout logic is extracted into `layout.py` as internal implementation detail.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Reusable graph algorithms in `dependency_graph.py`
**Key finding**: The codebase already has graph traversal implementations that the `TopologyDetector` and `LayerAssigner` can model after — do not reinvent from scratch:

- `dependency_graph.py:278-321` — DFS cycle detection with WHITE/GRAY/BLACK coloring; back-edge detection via GRAY ancestor check — directly applicable to cycle removal phase
- `dependency_graph.py:224-276` — Kahn's algorithm topological sort using `deque` — applicable to layer assignment after cycle removal
- `dependency_graph.py:138-185` — BFS wave grouping (`get_execution_waves`) — equivalent to topological layer assignment

These operate on `DependencyGraph` (issue-tracking objects), not `FSMLoop`, so cannot be called directly. But the algorithms should be ported/adapted.

### Required imports for `layout.py`
```python
from __future__ import annotations
import re
from collections import deque
from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.cli.output import terminal_width, colorize
```

### Preserved Public Signatures

Both signatures must remain unchanged after extraction (any rename breaks callers):

```python
# info.py:367-372 — entry point; must remain importable from info.py (re-export if moved)
def _render_fsm_diagram(
    fsm: FSMLoop,
    verbose: bool = False,
    highlight_state: str | None = None,
    highlight_color: str = "32",
) -> str: ...

# info.py:472-485 — internal; may move to layout.py without re-export
def _render_2d_diagram(
    main_path: list[str],
    edges: list[tuple[str, str, str]],
    main_edge_set: set[tuple[str, str]],
    branches: list[tuple[str, str, str]],
    back_edges: list[tuple[str, str, str]],
    bfs_order: list[str],
    initial: str = "",
    terminal_states: set[str] | None = None,
    fsm_states: dict[str, StateConfig] | None = None,
    verbose: bool = False,
    highlight_state: str | None = None,
    highlight_color: str = "32",
) -> str: ...

# info.py:303-308 — moves to layout.py
def _box_inner_lines(
    state: StateConfig | None,
    display_label: str,
    verbose: bool,
    inner_width: int,
) -> list[str]: ...
```

**Re-export requirement**: `test_ll_loop_display.py:14` imports `_render_fsm_diagram` from `info.py`; `test_ll_loop_commands.py:724,1270` patches `info_mod._render_fsm_diagram`. After moving to `layout.py`, keep `info.py` re-exporting: `from little_loops.cli.loop.layout import _render_fsm_diagram`. The `_helpers.py:320` lazy import (`from little_loops.cli.loop.info import _render_fsm_diagram`) also relies on this re-export.

### Internal mechanisms to preserve in `layout.py`

- **`diagram_indent` centering** (`info.py:624`): `diagram_indent = max(0, (tw - total_width) // 2)` — centers diagram in terminal; applied to all rendered lines. Must be preserved.
- **`highlight_state` / `highlight_color` params** — consumed by `_helpers.py:322-323` (`_render_fsm_diagram(fsm, highlight_state=state, highlight_color=highlight_color)`); `verbose` is NOT passed (defaults to `False`). Public signature of `_render_fsm_diagram` must stay unchanged.
- **`verbose` mode box-width branching** (`info.py:512-516`) — `max_box_inner` formula differs in verbose vs. normal mode. Must be preserved in coordinate assignment.

### `_render_2d_diagram` actual end line
The function ends with `return _colorize_diagram_labels("\n".join(lines))` at line **1027**, not 993. Line 993 is mid-function (inside off-path grid rendering). Extraction scope: `info.py:367-1027`.

### FSMLoop data structure fields consumed by renderer
From `fsm/schema.py`: `FSMLoop.states: dict[str, StateConfig]`, `FSMLoop.initial: str`. Per `StateConfig`: `on_success`, `on_failure`, `on_error`, `on_partial`, `next`, `route` (`RouteConfig`), `terminal`, `action_type`, `action`. `RouteConfig.routes: dict[str, str]`, `RouteConfig.default: str | None`.

## Related Key Documentation

- `thoughts/FEAT-670-layout-engine-research.md` — algorithm research, current implementation analysis, library survey

## Labels

`feature`, `cli-output`, `fsm`, `ux`

## Related Issues

- P3-ENH-666: FSM box diagram vertical layout (superseded — this issue is a superset)
- P4-ENH-542: Render FSM diagram list index in loop
- P4-ENH-654: FSM diagram active state background fill highlight
- P2-BUG-658: FSM diagram garbled for 4-state loops (completed — motivated this broader fix)
- P3-BUG-664: FSM diagram off-path arrows and back-edges broken (completed)

## Session Log
- `/ll:confidence-check` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/54edef10-3495-4074-a73f-5fbf089e106e.jsonl`
- `/ll:capture-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/000d1e34-e885-4aae-83d4-999718fb8e90.jsonl`
- `/ll:format-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/644cb258-98f9-4276-9d10-660523431e43.jsonl`
- `/ll:refine-issue` - 2026-03-11T03:23:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fee81fea-8bf1-4d92-a43d-05577978a440.jsonl`
- `/ll:refine-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53dc25b3-91cb-457d-a0cc-95d8fe9087b3.jsonl`
- `/ll:ready-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27c058d4-81a2-4f93-b6c1-3154d2afbb85.jsonl`
- `/ll:ready-issue` - 2026-03-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a385813-1230-48e4-9557-8fcd4a2fbd09.jsonl`

---

**Open** | Created: 2026-03-10 | Priority: P3

## Blocks
- ENH-654
