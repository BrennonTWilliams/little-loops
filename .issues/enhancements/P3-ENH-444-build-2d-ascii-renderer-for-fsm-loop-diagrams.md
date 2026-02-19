---
discovered_date: 2026-02-19
discovered_by: capture-issue
follows: ENH-443
confidence_score: 95
---

# ENH-444: Build 2D ASCII renderer for FSM loop diagrams

## Summary

Replace the current flat 1D linear text diagram in `ll-loop show` with a purpose-built 2D terminal graph renderer that draws labeled boxes and edges using Unicode box-drawing characters. The current renderer (shipped in ENH-443) produces a single horizontal line for the main path with separate lists for branches and back-edges, which is visually disappointing for anything beyond trivial loops.

## Current Behavior

`ll-loop show` renders the FSM as a flat horizontal chain with supplementary edge lists:

```
  [step_0] ──(next)──▶ [step_1] ──(next)──▶ [step_2] ──(next)──▶ [check_done] ──(success)──▶ [done]

  Back-edges (↺):
    [check_done] ──(fail)──▶ [step_0]  ↺
```

This does not visually communicate the graph structure — branching, merging, and cycles are invisible in the main flow and relegated to text lists.

## Expected Behavior

`ll-loop show` renders a proper 2D layered graph in the terminal:

```
  ┌─────────┐  next   ┌─────────┐  next   ┌─────────┐  next   ┌────────────┐  success  ┌──────┐
  │ step_0  │────────▶│ step_1  │────────▶│ step_2  │────────▶│ check_done │─────────▶│ done │
  └─────────┘         └─────────┘         └─────────┘         └────────────┘          └──────┘
       ▲                                                             │
       └─────────────────────────── fail ────────────────────────────┘
```

Key requirements:
- States rendered as Unicode box-drawn rectangles
- Edges drawn as lines with labeled transitions (success, fail, next, error, verdict names)
- Back-edges routed visually (below or around the main flow)
- Branching and merging visible in the 2D layout
- Self-loops clearly indicated
- Readable at typical terminal widths (80-120 columns)

## Motivation

The terminal is the sole UI for `ll-loop`. A proper 2D diagram makes loop structure comprehensible at a glance, especially for loops with branching evaluation states (route tables with multiple verdicts), back-edges (retry/cycle patterns), and non-linear topologies. The current 1D output forces users to mentally reconstruct the graph shape.

## Proposed Solution

Build a purpose-built Sugiyama-lite layered layout renderer (~150-200 lines) rather than depending on an external graph library. Research showed no Python library fits all constraints:

| Library | Issue |
|---------|-------|
| [phart](https://github.com/scottvr/phart) | No edge label support |
| [graphscii](https://github.com/etano/graphscii) | Requires manual x,y positioning |
| [box-of-rain](https://github.com/switz/box-of-rain) | TypeScript/npm — wrong ecosystem |
| `graph-easy` | Perl dependency |

### Approach: Sugiyama-lite layered layout

1. **Layer assignment**: Use existing BFS depth from `fsm.initial` to assign each state to a layer (column or row)
2. **Node ordering within layers**: Minimize edge crossings (barycenter heuristic or simple insertion order for small graphs)
3. **Box rendering**: Draw each state as a Unicode box (`┌─┐│ │└─┘`) sized to fit the state name
4. **Edge routing**: Draw edges between layers with transition labels inline. Forward edges go left-to-right or top-to-bottom. Back-edges route around the main flow (below for LR layout, or along the left margin for TB layout)
5. **Grid composition**: Compose all elements onto a 2D character grid, then join into lines

The existing `_render_fsm_diagram()` in `info.py` already computes BFS ordering, main path, edge classification, and edge labels. The new renderer replaces the text assembly (lines 144-189) while reusing the graph analysis (lines 95-142).

### Layout direction

Left-to-right (LR) keeps the familiar reading direction and matches the current horizontal main path. Top-to-bottom (TB) may work better for tall/narrow graphs. Consider LR as default with TB as future option.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — replace `_render_fsm_diagram()` function

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:cmd_show()` — calls `_render_fsm_diagram()`

### Similar Patterns
- N/A — this is the only graph renderer in the codebase

### Tests
- `scripts/tests/test_ll_loop_display.py` — `TestRenderFsmDiagram` class (lines 583-729)

The 2D renderer changes the output format in three ways that break existing assertions:

1. **State name format changes**: `[state_name]` → `│ state_name │` (name inside a Unicode box). Replace all `"[name]" in result` assertions with `"name" in result`.

2. **Edge label format changes**: `──(label)──▶` → inline label text between boxes (e.g., `  success  `). Replace all `"(label)" in result` assertions with `"label" in result`.

3. **Section headers are eliminated**: "Branches:" and "Back-edges (↺):" text sections are replaced by visual 2D routing. All assertions referencing these strings must be rewritten.

**Per-test update plan** (all 8 tests in `TestRenderFsmDiagram`):

| Test | Change Required | Notes |
|------|----------------|-------|
| `test_single_terminal_state` | Remove `"Branches" not in result` and `"Back-edges" not in result`; replace `"[done]"` with `"done"`; add `"┌" in result` | Sections eliminated |
| `test_linear_flow_shows_labels` | Replace `"[a]"`, `"[b]"`, `"[c]"` with bare names; replace `"(success)"` with `"success"`; remove both section assertions; add box char check | Sections eliminated |
| `test_next_transition_label` | Replace `"(next)"` with `"next"` | Minor — drop parens only |
| `test_branching_fsm_shows_branches_section` | Replace `"[test]"`, `"[done]"`, `"[fix]"` with bare names; replace `"(success)"`, `"(fail)"` with bare labels; **remove `"Branches:" in result`**; assert all three state names appear; add `"▶" in result` | Section eliminated — behavior verified by state name presence |
| `test_cyclic_fsm_shows_back_edges_section` | **Remove `"Back-edges" in result`** and `"↺" in result`; assert both `"evaluate"` and `"fix"` appear; assert back-edge label `"fail"` appears in output | Section eliminated — routing is visual |
| `test_self_loop_annotated` | **Remove `"Back-edges" in result`**; keep a self-loop indicator assertion — implementation decision: `↺` symbol near the box or `"↺" in result` is preferred over `"self-loop"` text | Keep some indicator assertion; exact symbol is an implementation decision |
| `test_route_table_branches` | Replace `"[route_state]"`, `"[done]"` with bare names; **remove `"Branches:" in result`**; assert all route labels (`"pass"`, `"fail"`, `"skip"`) and all target state names appear | Section eliminated |
| `test_main_flow_order` | Change target line from `result.split("\n")[0]` (top border row) to the name row (index 1); replace `"[first]"`, `"[second]"`, `"[third]"` with bare names in `.index()` calls | Box top border is line 0; state names are in line 1 |

### Documentation
- N/A — no docs reference the diagram format directly

### Configuration
- N/A

## Implementation Steps

1. Design the 2D character grid data structure and box-drawing primitives
2. Implement layer assignment using existing BFS depth computation
3. Implement box rendering (state name inside Unicode borders)
4. Implement forward edge routing with inline labels between layers
5. Implement back-edge routing around/below the main flow
6. Compose grid and produce final string output
7. Update tests in `TestRenderFsmDiagram` for new 2D output format

## Scope Boundaries

**Out of scope:**
- Interactive or animated diagrams
- Color/ANSI styling (can be added later)
- Graphviz/Mermaid/SVG export formats
- Automatic terminal width detection and responsive layout
- General-purpose graph rendering — this is purpose-built for small FSM loops (3-15 states)

## Success Metrics

- All existing FSM loop YAML files in `loops/` render as readable 2D diagrams
- Back-edges and branches are visually distinct from the main flow path
- Edge labels (transition names) are visible on every edge
- Output fits within 120 columns for typical loops (up to ~8 states)

## Impact

- **Priority**: P3 - Quality-of-life improvement for the primary loop inspection command
- **Effort**: Medium - Layout algorithm is bounded (~150-200 lines) but requires careful grid math
- **Risk**: Low - Purely visual output change, no behavioral impact on loop execution
- **Breaking Change**: No — only changes the text output format of `ll-loop show`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | FSM design and state/transition model |
| `docs/API.md` | Python module reference for FSM schema |

## Labels

`enhancement`, `cli`, `ll-loop`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-02-19T16:24:00-05:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ea41bd4b-d59d-4dff-8f30-922bc06bbf66.jsonl`

---

## Status

**Open** | Created: 2026-02-19 | Priority: P3
