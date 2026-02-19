# ENH-444: Build 2D ASCII Renderer for FSM Loop Diagrams

## Plan

### Phase 1: Replace text assembly in `_render_fsm_diagram()`

**File**: `scripts/little_loops/cli/loop/info.py`

Keep lines 87-171 (graph analysis: edge collection, BFS ordering, main path, edge classification).
Replace lines 144-189 (text assembly) with a 2D renderer that:

1. **Grid data structure**: `list[list[str]]` character grid
2. **Box rendering**: Each state → Unicode box (`┌─┐│ │└─┘`) sized to state name
3. **Main path layout**: States placed left-to-right with edge labels between boxes
4. **Branch edges**: Forward non-main edges drawn below main flow
5. **Back-edges**: Routed below the entire diagram with labeled arrows
6. **Self-loops**: `↺` marker next to the box

### Layout Algorithm (Sugiyama-lite)

- Main path states placed in a row, 2 spaces gap + label + arrow between boxes
- Each box is 3 rows tall: top border, name row, bottom border
- Forward branch edges drawn on rows below with `│` verticals and `─` horizontals
- Back-edges drawn at the bottom with `└─...─┘` routing and label

### Phase 2: Update tests

Update all 8 tests in `TestRenderFsmDiagram` per the issue's test update plan.

### Phase 3: Verify

- `python -m pytest scripts/tests/test_ll_loop_display.py -v`
- `ruff check scripts/little_loops/cli/loop/info.py`
- `python -m mypy scripts/little_loops/cli/loop/info.py`

### Success Criteria

- [ ] States rendered as Unicode boxes
- [ ] Edge labels visible on all edges
- [ ] Back-edges routed visually below main flow
- [ ] Self-loops indicated with ↺
- [ ] All 8 tests pass
- [ ] Lint and type checks pass
- [ ] Output fits within 120 columns for typical loops
