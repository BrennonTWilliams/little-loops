---
discovered_date: 2026-02-19
discovered_by: capture-issue
---

# ENH-443: Enhance `ll-loop show` output with a proper FSM graph diagram

## Summary

The current `ll-loop show` diagram section renders only a flat linear main-flow and a list of remaining edges. Improve it to produce a proper 2D text/ASCII graph that visually communicates the FSM structure — nodes, transitions, and branching — so users can understand loop flow at a glance.

## Current Behavior

`ll-loop show <loop>` prints a "Diagram:" section (implemented in `scripts/little_loops/cli/loop/info.py:150-205`) that outputs:
1. A single linear chain of the "happy path" states: `[state_a] ──→ [state_b] ──→ [state_c]`
2. Remaining edges listed individually: `[state_a] ──(fail)──→ [state_b]`

For loops with branching, back-edges, or non-linear topologies this output is hard to read and doesn't convey the real graph shape.

## Expected Behavior

`ll-loop show` should render a text diagram that clearly shows:
- All states as labeled boxes/nodes
- Directed transitions with labels (success, fail, error, next, route verdicts)
- Branching and merging flows visible at a glance
- Back-edges / loops indicated (e.g., with an upward arrow or `↺` annotation)

Example target output for a simple 3-state loop:

```
┌──────────┐  success  ┌──────────┐  success  ┌──────────┐
│  analyze │ ─────────▶│  apply   │ ─────────▶│  verify  │
└──────────┘           └──────────┘           └──────────┘
                           │ fail                  │ fail
                           ▼                       │
                       ┌──────────┐ ◀──────────────┘
                       │  report  │
                       └──────────┘
```

For loops with back-edges a compact notation is acceptable:
```
[analyze] ──(success)──▶ [apply] ──(success)──▶ [verify]
                             │ fail                  │ fail
                             └──────────▶ [report] ◀─┘
[apply] ◀──(retry)── [verify]   ↺ back-edge
```

## Motivation

Users running `ll-loop show` to understand a loop before executing it currently get very little spatial intuition about the FSM topology. A proper diagram reduces cognitive load and makes it easier to spot incorrect loop configurations before running them.

## Implementation Steps

1. **Assess existing diagram code** (`info.py:150-205`) — understand current edge collection and main-path tracing.
2. **Choose rendering approach**:
   - Option A: Simple column layout — place states in topological order left-to-right/top-to-bottom; draw transitions as arrows with labels.
   - Option B: Layered grid — assign states to rows by BFS depth, render grid with Unicode box characters.
   - Start with Option A (simpler, sufficient for most loop shapes).
3. **Implement `render_fsm_diagram(fsm) -> str`** in `info.py` (or extract to a helper in `scripts/little_loops/fsm/`).
4. **Handle special cases**: cycles/back-edges, self-loops, disconnected states.
5. **Replace** the current diagram block with the new renderer.
6. **Add tests** in `scripts/tests/` to cover: linear, branching, cyclic FSMs.

## Scope Boundaries

- **In scope**: Improve ASCII/Unicode text diagram in `ll-loop show` for linear, branching, and cyclic FSM topologies.
- **Out of scope**: Interactive TUI/curses display; third-party rendering dependencies (graphviz, etc.); changes to `ll-loop run` behavior; changes to the YAML loop config format.

## Impact

- **Priority**: P3 - Nice-to-have UX improvement; does not block any current workflows.
- **Effort**: Medium - Requires new layout algorithm for FSM graph; no external deps needed.
- **Risk**: Low - Purely a display change; no behavioral or config format changes.
- **Breaking Change**: No

## Labels

`enhancement`, `ll-loop`, `ux`, `cli`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM module structure |
| `docs/API.md` | FSM public API |

## Resolution

**Implemented** `_render_fsm_diagram(fsm: FSMLoop) -> str` in `scripts/little_loops/cli/loop/info.py`.

### Changes Made

- **`scripts/little_loops/cli/loop/info.py`**: Extracted inline diagram code into `_render_fsm_diagram()`. New renderer uses BFS depth to classify edges into three sections:
  - **Main flow**: happy-path traversal with transition labels (`──(success)──▶`)
  - **Branches**: alternate forward transitions (fail, error, alternate routes)
  - **Back-edges (↺)**: transitions to earlier BFS-depth states (cycles), with self-loop annotation
- **`scripts/tests/test_ll_loop_display.py`**: Added `TestRenderFsmDiagram` class with 8 tests covering linear, single-state, next-transition, branching, cyclic, self-loop, route-table, and ordering topologies.

### Approach Used
Option A (linear main path + classified sections). No external dependencies added.

## Session Log
- `/ll:capture-issue` - 2026-02-19T00:00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f90fd0e4-81c6-4f00-b358-60f545b5395e.jsonl`
- `/ll:manage-issue` - 2026-02-19T00:00:00 - implemented

---

## Status

**Completed** | Created: 2026-02-19 | Resolved: 2026-02-19 | Priority: P3
