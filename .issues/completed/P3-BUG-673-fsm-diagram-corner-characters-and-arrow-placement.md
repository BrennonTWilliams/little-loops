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
- **Anchor**: `_render_layered_diagram()`, back-edge rendering block (lines 867–925)
- **Cause**: The vertical pipe loop (lines 897–899) draws `│` from `top_row` to `bot_row`. Horizontal connectors (lines 906–917) draw `─` from `col + 1` to the box left edge, but never replace `grid[src_row][col]` or `grid[dst_row][col]` with a corner character. The arrow at line 903 overwrites `grid[top_row][col]` with `▲`, placing it at the top of the pipe column rather than at the destination box connection point (`grid[dst_row][dst_left - 1]`).

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

1. **Corner characters** (layout.py lines 897-910): After the vertical `│` pipe loop (lines 897-899), overwrite `grid[src_row][col]` and `grid[dst_row][col]` with corner chars:
   - Use `└` (`\u2514`) if the row is `bot_row` (pipe ends here)
   - Use `├` (`\u251c`) if the row is above `bot_row` (pipe continues below)
   - Reference box corner pattern at layout.py:556 for consistent Unicode usage
2. **Arrow placement** (layout.py line 903): Remove `grid[top_row][col] = "▲"`. Instead, place `▲` at `grid[dst_row][dst_left - 1]` — the cell immediately before the destination box border. Compute `dst_left` from `col_start.get(dst, col + 1)` (already available at line 914).
3. **Update tests** in `test_ll_loop_display.py`:
   - `test_cyclic_fsm_shows_back_edges_section` (line 710): Assert `└` or `├` present in back-edge rows
   - `test_bidirectional_back_edge_both_pipes_on_label_rows` (line 789): Update `│` count expectations if `├` replaces `│` at turn rows
   - `test_multiple_off_path_states_same_depth` (line 813): Assert `▲` appears adjacent to box, not at pipe top
4. Verify rendering with `ll-loop show issue-refinement-git` and other multi-back-edge diagrams

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` - back-edge rendering in `_render_layered_diagram()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:20,457` — imports and calls `_render_fsm_diagram(fsm, verbose=verbose)`
- `scripts/little_loops/cli/loop/_helpers.py:324-326` — lazy-imports and calls `_render_fsm_diagram()` during loop execution

### Similar Patterns
- Box rendering in same file uses corner characters: `\u250c` (┌) at `layout.py:514`, `\u2510` (┐) at `:519`, `\u2514` (└) at `:556`, `\u2518` (┘) at `:561` — same Unicode approach should apply to back-edge turns
- `├`/`└` decision convention in `scripts/little_loops/cli/sprint/_helpers.py:119`: `└──` for last item (pipe ends), `├──` when pipe continues — exact same logic needed here for `bot_row` vs mid-pipe
- Forward-edge rendering (lines 797–804) draws vertical `│` pipes and `▼` arrows but does NOT need corner chars (straight vertical drop to box)
- `├` (`\u251c`) is NOT currently used anywhere in `layout.py` — will be a new character for this file

### Tests
- `scripts/tests/test_ll_loop_display.py` — existing tests to update:
  - `test_cyclic_fsm_shows_back_edges_section` (line 710) — asserts `▲` or `▼` present; should also assert `└` or `├` corner chars
  - `test_bidirectional_back_edge_both_pipes_on_label_rows` (line 789) — asserts dual `│` pipes; may need updates for `├` replacing `│` at turn rows
  - `test_multiple_off_path_states_same_depth` (line 813) — asserts `▲` in margin; should verify arrow at box connection point
  - `test_issue_refinement_git_topology` (line 903) — most relevant test; already checks `▲` count (line 951) and `└`/`┘` border presence (line 977); needs corner char assertions at back-edge turns

### Reference Rendering
- `fixed-ref-git-fsm-diagram.txt` (uncommitted) — reference diagram showing expected corner characters and arrow placement

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
- `/ll:refine-issue` - 2026-03-11T21:38:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ba84e347-69b4-4da4-a0c7-e4e1aebcdcf4.jsonl`
- `/ll:ready-issue` - 2026-03-11T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f08c54d6-5d2f-49fa-be74-5b3e2575dc08.jsonl`

---

## Resolution

**Fixed** on 2026-03-11.

### Changes Made

1. **`scripts/little_loops/cli/loop/layout.py`** — Back-edge rendering block in `_render_layered_diagram()`:
   - Replaced `│` at pipe-to-horizontal turn points with `└` (pipe ends) or `├` (pipe continues below)
   - Moved `▲` arrow from pipe column top to `dst_left - 1` (end of horizontal connector at target box)

2. **`scripts/tests/test_ll_loop_display.py`** — Updated test assertions:
   - `test_issue_refinement_git_topology`: Updated arrow count assertion (shared target = 1 arrow), added `├`/`└` corner character assertions
   - `test_cyclic_fsm_shows_back_edges_section`: Added corner character assertion

---

## Status

**Completed** | Created: 2026-03-11 | Resolved: 2026-03-11 | Priority: P3
