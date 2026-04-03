---
discovered_date: 2026-04-03
discovered_by: capture-issue
---

# ENH-935: Recursive Sub-Loop Diagram Display to Depth N

## Summary

When running `ll-loop run ... --show-diagrams`, nested sub-loop diagrams are only shown one level deep (parent + one child). If a sub-loop itself has sub-loops, those deeper levels are not displayed. This should be generalized to depth N, showing each active sub-loop below its parent.

## Context

**Direct mode**: User description: "When we run a loop with ll-loop run ... --show-diagrams and the loop has a sub-loop, we show the sub-loop as a second diagram below the parent diagram. However, sub-loops can also have their sub-loops. We should show each active sub-loop below its parent for not just a depth of 2, but of N"

The current implementation in `scripts/little_loops/cli/loop/_helpers.py` tracks a single `current_child_fsm` at depth 0 (lines 313-315) and renders at most one child diagram when `depth > 0` (lines 364-376). The depth of nesting supported by the executor (`scripts/little_loops/fsm/executor.py`) is already N via `_execute_sub_loop`, but the display layer doesn't follow suit.

## Motivation

Users running deeply nested loop configurations (e.g., an outer orchestration loop → domain loop → action loop) can't see the full active FSM stack in the terminal. At depth 2+, the diagram display silently drops inner sub-loops, making it harder to monitor progress and debug state transitions.

## Proposed Solution

Replace the single `current_child_fsm` tracker with a stack (list) indexed by depth. On each `state_enter` event, update the stack entry for the current depth and clear any deeper entries (since entering a shallower state invalidates deeper nesting). When rendering diagrams, iterate through the stack from depth 0 to the max occupied depth, printing each FSM diagram with a separator line.

## Implementation Steps

1. **Replace `current_child_fsm` with a depth-indexed stack** in `run_foreground` (`_helpers.py`):
   - Change `current_child_fsm: list[FSMLoop | None] = [None]` to `child_fsm_stack: dict[int, FSMLoop | None] = {}`
   - On `state_enter` at depth `d`: load child FSM for the current state (if any) into `child_fsm_stack[d]`, and delete all entries with key > d to clear stale deeper levels.

2. **Update the diagram rendering block** (currently `_helpers.py:349-376`):
   - After printing the parent diagram, iterate `depth in range(1, max_depth + 1)` using the stack.
   - For each depth, print a separator (`── sub-loop: {name} ────...`) and the diagram with the active state highlighted.
   - The `state` from the event is only the active state at the current event depth; for ancestor diagrams, highlight the last known state at that depth.

3. **Track last-known state per depth** (similar to how `last_parent_state` works today):
   - Replace `last_parent_state: list[str | None] = [None]` with `last_state_at_depth: dict[int, str] = {}`.
   - Update on every `state_enter` event for depth `d`.

4. **Guard for terminal width**: existing centering and truncation logic should apply to sub-loop diagrams the same way.

5. **Tests**: update `scripts/tests/test_ll_loop_display.py` to cover depth ≥ 2 diagram rendering.

## API/Interface

No public API changes. The `--show-diagrams` flag behavior is extended, not altered. Internal state tracking in `run_foreground` is refactored.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM loop execution and nesting model |

## Labels

`enhancement`, `loops`, `diagrams`, `captured`

---

## Status

**Open** | Created: 2026-04-03 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/225d2a56-bcaa-4bef-9bb5-92a00d3997ee.jsonl`
