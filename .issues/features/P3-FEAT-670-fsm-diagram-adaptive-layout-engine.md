---
id: FEAT-670
type: FEAT
priority: P3
status: active
discovered_date: 2026-03-10
discovered_by: capture-issue
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
- `scripts/little_loops/cli/loop/info.py` — current renderer (refactor `_render_fsm_diagram` at line 367 and `_render_2d_diagram` at line 472)
- `scripts/little_loops/cli/loop/layout.py` — **new file** for extracted layout engine

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:1226` — `cmd_show` calls `_render_fsm_diagram`
- `scripts/little_loops/cli/loop/_helpers.py:319-325` — `run_foreground()` calls `_render_fsm_diagram` on `state_enter` events
- `scripts/little_loops/fsm/schema.py` — provides `FSMLoop`, `StateConfig`, `RouteConfig` consumed by renderer
- `scripts/little_loops/cli/output.py` — provides `terminal_width()`, `colorize()`

### Similar Patterns
- P3-ENH-666: FSM box diagram vertical layout (superseded by this issue)
- P4-ENH-542: Render FSM diagram list index in loop
- P4-ENH-654: FSM diagram active state background fill highlight

### Tests
- `scripts/tests/test_ll_loop_display.py` — imports `_render_fsm_diagram` directly; update existing tests and add new topology-specific test cases

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Extract layout logic from `info.py:367-993` into new `layout.py` module
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
- [ ] Back-edges (cycles) render as labeled margin arrows without overlapping state boxes
- [ ] Diagrams respect terminal width — no horizontal overflow for any supported topology
- [ ] All existing FSM loop configs in the project render correctly
- [ ] Existing diagram tests pass or are updated

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
- `/ll:capture-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/000d1e34-e885-4aae-83d4-999718fb8e90.jsonl`
- `/ll:format-issue` - 2026-03-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/644cb258-98f9-4276-9d10-660523431e43.jsonl`

---

**Open** | Created: 2026-03-10 | Priority: P3
