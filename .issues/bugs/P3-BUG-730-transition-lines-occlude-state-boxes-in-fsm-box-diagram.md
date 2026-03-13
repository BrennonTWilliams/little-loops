---
id: BUG-730
title: Transition lines occlude state boxes in FSM box diagram
priority: P3
status: open
type: BUG
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# BUG-730: Transition lines occlude state boxes in FSM box diagram

## Description

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

## Actual Behavior

Transition lines are drawn over state box contents, occluding labels and making affected states difficult to read.

## Implementation Steps

1. Identify the canvas rows occupied by each box (top row, bottom row, content rows).
2. Before writing a horizontal connector character at a given `(row, col)`, check whether that cell is already claimed by a box border or interior.
3. If a conflict exists, either:
   - Route the connector above/below the conflicting box (preferred), or
   - Skip writing the connector character and let the box border win (simpler fallback).
4. Add a regression test using a loop YAML that produces a skip-layer transition.

## Acceptance Criteria

- [ ] Horizontal transition lines do not visually cross through state boxes.
- [ ] Box borders and labels remain fully visible when a transition spans multiple columns.
- [ ] Existing diagram snapshot tests continue to pass.

## Related Files

- `scripts/little_loops/cli/loop/layout.py` — rendering engine
- `scripts/tests/test_ll_loop_display.py` — display tests
- `scripts/tests/test_ll_loop_commands.py` — integration tests

---

## Session Log
- `/ll:capture-issue` - 2026-03-13T21:34:30Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
