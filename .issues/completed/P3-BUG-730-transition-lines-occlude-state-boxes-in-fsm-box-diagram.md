---
id: BUG-730
title: Transition lines occlude state boxes in FSM box diagram
priority: P3
status: completed
type: BUG
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# BUG-730: Transition lines occlude state boxes in FSM box diagram

## Summary

In the FSM Box Diagram Generator, horizontal transition lines are drawn across the canvas in a way that can visually overlap and occlude state boxes. When a transition spans multiple columns, the connector line passes through the area occupied by intermediate state boxes, making the diagram hard to read.

Example (from reported output):
```
 │ │              ┌──────────────────────────────────────────┐          ┌──────────────────────────────────────────┐      ┌──────────────────────────────────────────┐
 │ └──────────────│ check_commit  [shell]                    │─────────────────────────────────────────────────────next──▶│ refine_issues  [prompt]                  │
 │                │ FILE="/tmp/issue-refinement-commit-coun… │          │ Run this command for issue ${captured.i… │      │ Run these commands in order for issue $… │
 │                └──────────────────────────────────────────┘          └──────────────────────────────────────────┘      └──────────────────────────────────────────┘
```

The `next` transition label and arrow are drawn through the middle box rather than routed around it.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Functions**: `_render_layered_diagram` (line 569), horizontal connector rendering logic (~lines 928–1214)
- **Explanation**: Horizontal connectors are drawn as straight lines at the vertical midpoint of source/target boxes without checking whether intermediate boxes occupy that row. The rendering logic writes characters directly to a 2D canvas; transitions that skip layers write through intervening box cells.

## Steps to Reproduce

1. Create or run a loop YAML with a transition that skips one or more intermediate states (e.g., a `next` transition from state A to state C where state B sits between them horizontally).
2. Run `ll-loop show-diagrams` (or equivalent).
3. Observe that the horizontal connector line passes through the middle state box.

## Expected Behavior

Transition lines should route around (above or below) any state boxes they would otherwise cross. Alternatively, lines passing behind boxes should be clipped so that box borders take visual precedence.

## Current Behavior

Transition lines are drawn over state box contents, occluding labels and making affected states difficult to read.

## Implementation Steps

1. Identify the canvas rows occupied by each box (top row, bottom row, content rows).
2. Before writing a horizontal connector character at a given `(row, col)`, check whether that cell is already claimed by a box border or interior.
3. If a conflict exists, either:
   - Route the connector above/below the conflicting box (preferred), or
   - Skip writing the connector character and let the box border win (simpler fallback).
4. Add a regression test using a loop YAML that produces a skip-layer transition.

## Acceptance Criteria

- [x] Horizontal transition lines do not visually cross through state boxes.
- [x] Box borders and labels remain fully visible when a transition spans multiple columns.
- [x] Existing diagram snapshot tests continue to pass.

## Verification Notes

- **Verified**: 2026-03-13 — VALID
- `scripts/little_loops/cli/loop/layout.py` exists (1438 lines)
- `_render_layered_diagram` confirmed at line 569
- Horizontal connector rendering logic confirmed at ~lines 928–1214; unconditional `grid[conn_row][c] = "─"` writes without checking for box characters (confirmed bug)
- `scripts/tests/test_ll_loop_display.py` exists
- `scripts/tests/test_ll_loop_commands.py` exists
- Related completed issue BUG-708 (disconnected connectors at shared nodes) is distinct — different rendering path and failure mode

## Related Files

- `scripts/little_loops/cli/loop/layout.py` — rendering engine
- `scripts/tests/test_ll_loop_display.py` — display tests
- `scripts/tests/test_ll_loop_commands.py` — integration tests

## Impact

- **Priority**: P3 - Visual-only defect; diagrams remain functional but are harder to read when transitions span multiple columns
- **Effort**: Small - Fix is scoped to the horizontal connector rendering logic in `layout.py`; no protocol or data changes
- **Risk**: Low - Affects only diagram rendering output; does not touch loop execution, state machine logic, or file I/O
- **Breaking Change**: No

## Labels

`bug`, `diagram`, `fsm`, `rendering`, `captured`

---

**Completed** | Created: 2026-03-13 | Resolved: 2026-03-13 | Priority: P3

## Resolution

Precomputed a `_box_occ` dict (row → set of occupied columns) after the box-drawing phase in `_render_layered_diagram`. Same-layer edge connectors and skip-forward-edge horizontal connectors now skip any cell that belongs to a box, so intermediate state boxes retain their borders and content. Added regression test `test_same_layer_edge_does_not_occlude_intermediate_box`; all 91 tests pass.

---

## Session Log
- `/ll:capture-issue` - 2026-03-13T21:34:30Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b17321b-fc43-48b2-a2d7-478ef2d7ba48.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b17321b-fc43-48b2-a2d7-478ef2d7ba48.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b17321b-fc43-48b2-a2d7-478ef2d7ba48.jsonl`
- `/ll:ready-issue` - 2026-03-13T19:53:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6cecfa03-19f5-4d9a-8854-ee9e4fc68966.jsonl`
- `/ll:manage-issue` - 2026-03-13T19:53:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6cecfa03-19f5-4d9a-8854-ee9e4fc68966.jsonl`
