---
discovered_date: 2026-04-03
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-935: Recursive Sub-Loop Diagram Display to Depth N

## Summary

When running `ll-loop run ... --show-diagrams`, nested sub-loop diagrams are only shown one level deep (parent + one child). If a sub-loop itself has sub-loops, those deeper levels are not displayed. This should be generalized to depth N, showing each active sub-loop below its parent.

## Context

**Direct mode**: User description: "When we run a loop with ll-loop run ... --show-diagrams and the loop has a sub-loop, we show the sub-loop as a second diagram below the parent diagram. However, sub-loops can also have their sub-loops. We should show each active sub-loop below its parent for not just a depth of 2, but of N"

The current implementation in `scripts/little_loops/cli/loop/_helpers.py` tracks a single `current_child_fsm` at depth 0 (lines 313-315) and renders at most one child diagram when `depth > 0` (lines 364-376). The depth of nesting supported by the executor (`scripts/little_loops/fsm/executor.py`) is already N via `_execute_sub_loop`, but the display layer doesn't follow suit.

## Current Behavior

When running `ll-loop run ... --show-diagrams` with a loop that has nested sub-loops, only the parent and one level of child diagrams are displayed. The display layer in `run_foreground` (`_helpers.py`) tracks a single `current_child_fsm` at depth 0 and renders at most one child diagram. Sub-loops at depth 2+ are silently dropped from the diagram output, even though the executor already supports arbitrary nesting depth via `_execute_sub_loop`.

## Expected Behavior

`--show-diagrams` displays the full active FSM stack for all nesting depths (N levels). Each active sub-loop is shown below its parent diagram with a separator line. When a shallower state is entered, deeper entries are cleared from the display.

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

5. **Tests**: update `scripts/tests/test_ll_loop_display.py` to cover depth ≥ 2 diagram rendering, modeled after `test_sub_loop_child_diagram_rendered_during_sub_loop_execution` (`test_ll_loop_display.py:1787`): add a depth-2 FSM, patch `load_loop` to return per-depth FSMs, emit depth=0 → depth=1 → depth=2 events, and assert 3 render calls (parent + depth-1 child + depth-2 grandchild) with two separator lines.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical implementation nuance — loading sub-FSMs at depth > 0:**

When depth-D state enters, the sub-FSM config (`.loop` field) lives on the state object within the FSM at depth D, not the top-level `fsm`. The FSM at depth D is tracked in the stack as `child_fsm_stack[D - 1]` (for D > 0) or the top-level `fsm` (for D == 0). The generalized load logic is:

```python
parent_at_depth = fsm if depth == 0 else child_fsm_stack.get(depth - 1)
if parent_at_depth and state in parent_at_depth.states:
    fsm_state = parent_at_depth.states[state]
    if fsm_state.loop:
        try:
            child_fsm_stack[depth] = load_loop(fsm_state.loop, executor.loops_dir, Logger())
        except (FileNotFoundError, ValueError):
            pass
    else:
        child_fsm_stack[depth] = None
# Clear stale deeper entries
for k in list(child_fsm_stack.keys()):
    if k > depth:
        del child_fsm_stack[k]
```

**Exact lines of the single-slot trackers to replace (`_helpers.py`):**
- `last_parent_state` declaration: lines 310–312
- `current_child_fsm` declaration: lines 313–315
- `last_parent_state[0] = state` update (inside `if depth == 0:`): line 338
- `current_child_fsm[0] = load_loop(...)`: line 342
- `current_child_fsm[0] = None` (non-loop state): line 348
- `highlight` derivation: line 352
- Child render guard: line 364; child diagram render: lines 365–376

**`_render_fsm_diagram` signature (`layout.py:1434`):**
```python
def _render_fsm_diagram(
    fsm: FSMLoop,
    verbose: bool = False,
    highlight_state: str | None = None,
    highlight_color: str = "32",
    edge_label_colors: dict[str, str] | None = None,
    badges: dict[str, str] | None = None,
) -> str:
```

**`load_loop` signature (`_helpers.py:114`):**
```python
def load_loop(name_or_path: str, loops_dir: Path, logger: Logger) -> FSMLoop:
```
— call site wraps in `try/except (FileNotFoundError, ValueError)` (see `_helpers.py:341–346`).

**`_sub_event_callback` depth-stamping pattern (`executor.py:315–321`):** grandchild events already arrive stamped with their own depth (preserved intact by intermediate closures), so `display_progress` receives the correct depth for every nesting level with no changes needed to the executor.

## API/Interface

No public API changes. The `--show-diagrams` flag behavior is extended, not altered. Internal state tracking in `run_foreground` is refactored.

## Scope Boundaries

- **In scope**: Extending the diagram display layer in `run_foreground` (`_helpers.py`) to support arbitrary nesting depth
- **Out of scope**: Changes to the executor's sub-loop nesting logic in `executor.py` — it already supports depth N via `_execute_sub_loop`
- **Out of scope**: Changes to `--show-diagrams` behavior when there are no sub-loops (depth 0/1 cases remain unchanged)
- **Out of scope**: Performance optimization for very deeply nested loops (> 5 levels is an edge case)

## Success Metrics

- `--show-diagrams` displays correct diagram count: parent + N child diagrams for N levels of nesting
- Existing depth-0 and depth-1 behavior unchanged (regression tests pass)
- `test_ll_loop_display.py` passes for depth 1, 2, and 3 nested loop configurations

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — replace `current_child_fsm` tracker with depth-indexed stack; update diagram rendering block; replace `last_parent_state` with `last_state_at_depth`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — triggers display events via `_execute_sub_loop`; no changes needed

### Similar Patterns
- `scripts/little_loops/cli/loop/_helpers.py:313–315` — `current_child_fsm: list[FSMLoop | None] = [None]` declaration (mutable closure cell to replace with `dict[int, FSMLoop | None]`)
- `scripts/little_loops/cli/loop/_helpers.py:310–312` — `last_parent_state: list[str | None] = [None]` declaration (to replace with `dict[int, str]`)
- `scripts/little_loops/cli/loop/_helpers.py:342` — `current_child_fsm[0] = load_loop(fsm_state.loop, executor.loops_dir, Logger())` on depth-0 state enter (the load-loop call pattern to generalize)
- `scripts/little_loops/cli/loop/_helpers.py:348` — `current_child_fsm[0] = None` on non-loop state (clear pattern to generalize for deeper keys)
- `scripts/little_loops/cli/loop/_helpers.py:364` — `if depth > 0 and current_child_fsm[0] is not None:` guard (child render check to generalize to a loop)
- `scripts/little_loops/cli/loop/_helpers.py:352` — `highlight = state if depth == 0 else last_parent_state[0]` (highlight derivation to generalize with `last_state_at_depth`)
- `scripts/little_loops/fsm/executor.py:119` — `self._retry_counts: dict[str, int] = {}` — existing per-key accumulator dict pattern (structural model for `last_state_at_depth: dict[int, str]`)
- `scripts/little_loops/cli/loop/layout.py:214–225` — `_bfs_order` returns `depth: dict[str, int]` — existing int-keyed dict in the layout module

### Tests
- `scripts/tests/test_ll_loop_display.py:1787` — `test_sub_loop_child_diagram_rendered_during_sub_loop_execution` — the key existing test to model after: patches `load_loop` and `_render_fsm_diagram` (with `wraps=`), emits depth=0 then depth=1 events, asserts exact render call sequence and `"sub-loop: child-loop"` separator in stdout
- `scripts/tests/test_ll_loop_display.py:1726` — `test_sub_loop_diagram_keeps_parent_state_highlighted` — depth=1 highlight tracking test; analogous test needed for depth=2

### Documentation
- `docs/guides/LOOPS_GUIDE.md:1214` — **must update**: explicitly states "Sub-loop diagram display is supported for one level of nesting (depth-1 child loops)" — update to describe depth-N support
- `docs/reference/CLI.md:252–253,292–293` — documents `--show-diagrams` flag for `ll-loop run` and `ll-loop foreground`; review for accuracy after change

### Configuration
- N/A

## Impact

- **Priority**: P3 - Enhancement to existing `--show-diagrams` feature; no blocking issues
- **Effort**: Small - Localized change to display layer only; executor already supports N nesting; ~50 LOC
- **Risk**: Low - No public API changes; display-only refactor; existing behavior preserved for depth 0/1
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM loop execution and nesting model |
| guide | docs/guides/LOOPS_GUIDE.md:1214 | Explicitly states depth-1 only limit — **must update** |
| cli-ref | docs/reference/CLI.md:252–253,292–293 | `--show-diagrams` flag documentation |
| history | .issues/completed/P3-ENH-846-show-sub-loop-fsm-diagram-alongside-parent.md | Original depth-1 sub-loop diagram feature this extends |

## Labels

`enhancement`, `loops`, `diagrams`, `captured`

---

## Status

**Open** | Created: 2026-04-03 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-04-03T21:58:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b97f38eb-10b6-49e1-9b95-16bde969e44b.jsonl`
- `/ll:refine-issue` - 2026-04-03T21:55:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b97f38eb-10b6-49e1-9b95-16bde969e44b.jsonl`
- `/ll:confidence-check` - 2026-04-03T22:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f7e84b3-4142-485f-b208-f3c6eab0403e.jsonl`
- `/ll:format-issue` - 2026-04-03T21:51:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7874a99-6dd2-4c37-bbb7-a3cc34468974.jsonl`
- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/225d2a56-bcaa-4bef-9bb5-92a00d3997ee.jsonl`
