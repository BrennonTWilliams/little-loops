---
discovered_date: "2026-03-11"
discovered_by: capture-issue
---

# BUG-673: FSM diagram corner characters and arrow placement

## Summary

The FSM diagram renderer has two remaining visual issues after BUG-672 fixes:

1. **Corner characters missing**: Transition lines from back-edge pipes to state boxes use `│─` (vertical pipe followed by horizontal dash) instead of proper Unicode corner characters like `└` or `├`. For example, `check_commit→evaluate` back-edge connector shows `│──────────────│` instead of `└──────────────│` at the turn point.

2. **Arrow placement wrong**: Back-edge arrows (`▲`) point upward at the top of the margin column but are not at the end of the transition where it connects to the target state box. In the `issue-refinement-git` diagram, `▲─▲` appears above the `evaluate` box disconnected from the horizontal connector, rather than the arrows appearing at the point where the connector meets the box.

## Current Behavior

In the `issue-refinement-git` diagram:
```
      ▲─▲──────────────│ → evaluate  [shell]              │
      │ │              │ ...                               │
      ...
      │ │              ┌──────────────────────────────────┐
      │ │──────────────│ check_commit  [shell]            │
      │                │ ...                               │
      │                └──────────────────────────────────┘
      │                                  │ success
      │                                  │
      │                                  ▼
      │                        ┌──────────────────┐
      │────────────────────────│ commit  [prompt] │
                               │ /ll:commit       │
                               └──────────────────┘
```

- Back-edge horizontal connectors use `│──────` at the turn instead of `└──────`
- Arrows `▲─▲` float above the target box instead of appearing where the connector enters the box

## Expected Behavior

1. Where a back-edge pipe turns horizontally toward a box, use `└` (or `├` if the pipe continues) instead of `│` followed by `─`
2. Back-edge arrows should appear at the connection point where the horizontal connector meets the target state box, indicating the direction of the transition

## Steps to Reproduce

1. Run `ll-loop show issue-refinement-git`
2. Observe back-edge connectors from `check_commit` and `commit` to `evaluate`
3. Note `│──────` at turn points instead of `└──────`
4. Note `▲─▲` floating above box rather than at connection point

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: `_render_layered_diagram()`, back-edge rendering block
- **Cause**: The horizontal connector rendering draws `─` characters starting from the pipe column but does not replace the pipe character at the turn point with a corner character (`└`, `├`, `┘`, etc.). Arrow placement is rendered at the top of the vertical pipe run rather than at the box connection point.

## Motivation

FSM diagrams are the primary visual interface for understanding loop configurations. Missing corner characters and misplaced arrows make the diagrams look unpolished and harder to follow visually, especially for complex loops with multiple back-edges.

## Proposed Solution

In `_render_layered_diagram()` in `layout.py`, modify the back-edge rendering block (lines ~893-917):

### 1. Corner characters at pipe-to-horizontal turns

After the vertical `│` pipe loop (lines 893-899), replace the character at each horizontal turn point with the appropriate corner:

- At `grid[src_row][col]`: Use `└` if the pipe ends at `src_row` (i.e., `src_row == bot_row`), or `├` if the pipe continues past this row
- At `grid[dst_row][col]`: Use `└` if the pipe ends at `dst_row` (i.e., `dst_row == bot_row`), or `├` if the pipe continues past this row

The determination is: if the current row is the bottommost extent of the pipe (`bot_row`), use `└` (pipe ends here). If the pipe continues below (row < `bot_row`), use `├` (pipe continues).

### 2. Arrow placement at box connection point

Move the `▲` from `grid[top_row][col]` (line 903) to the end of the destination horizontal connector at `grid[dst_row][dst_left - 1]` — the last cell before the box border. This places the arrow where the connector visually meets the target state box.

Remove the current arrow placement that overwrites the pipe at `top_row`, since the corner character should appear there instead.

### Expected result

```
      │                ┌──────────────────────────────────┐
      ├────────────────▲ evaluate  [shell]                │
      │                │ ...                               │
      ...
      │                ┌──────────────────────────────────┐
      └────────────────│ check_commit  [shell]            │
```

## Implementation Steps

1. In the back-edge rendering block of `_render_layered_diagram()`, after the `│` pipe loop, add corner character logic: determine whether each horizontal turn row is at `bot_row` (use `└`) or mid-pipe (use `├`), and overwrite `grid[row][col]` accordingly
2. Move `▲` placement from `grid[top_row][col]` to `grid[dst_row][dst_left - 1]` (last cell before destination box border)
3. Update existing tests in `test_ll_loop_display.py` to assert corner characters (`└`, `├`) at turn points and `▲` at box connection points
4. Verify rendering with `ll-loop show issue-refinement-git` and other multi-back-edge diagrams

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` - back-edge rendering in `_render_layered_diagram()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` - re-exports and calls `_render_fsm_diagram`
- `scripts/little_loops/cli/loop/_helpers.py` - calls `_render_fsm_diagram()` during loop execution

### Similar Patterns
- Forward-edge rendering in same function likely uses corner characters already - can reference that pattern

### Tests
- `scripts/tests/test_ll_loop_display.py` - existing FSM diagram tests; needs assertions for corner characters and arrow placement

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 - Visual polish issue, diagrams are readable but not visually correct
- **Effort**: Small - Localized to back-edge rendering block in `layout.py`
- **Risk**: Low - Rendering-only changes
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | System design context for CLI loop module |

## Labels

`bug`, `cli`, `fsm-diagram`

## Session Log
- `/ll:capture-issue` - 2026-03-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:format-issue` - 2026-03-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/708fe6d3-a6cb-45dd-9b97-7ef486eedbc5.jsonl`

---

## Status

**Open** | Created: 2026-03-11 | Priority: P3
