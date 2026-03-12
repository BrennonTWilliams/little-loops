---
discovered_date: 2026-03-12
discovered_by: capture-issue
confidence_score: 95
---

# BUG-678: FSM diagram branch edges to terminal states not rendered

## Summary

In the FSM diagram renderer, branch edges (e.g. `on_failure`, `on_error`) that target terminal states are not rendered as visual arrows. The terminal state (`done`) appears as a disconnected orphan box at the bottom of the diagram with no incoming arrow, even though `count_new → done` transitions exist via `on_failure` and `on_error`.

## Steps to Reproduce

1. Define a loop with branch edges to a terminal state (e.g. `issue-discovery-triage.yaml` where `count_new` has `on_failure: done` and `on_error: done`)
2. Run `ll-loop s issue-discovery-triage`
3. Observe: `done` state renders as a disconnected box with no incoming arrows

## Current Behavior

The `done` terminal state appears as an isolated box at the bottom of the diagram:

```
                                         ┌────────┐
                                         │ done ◉ │
                                         └────────┘
```

No arrow from `count_new → done` is rendered, making the diagram misleading about how the FSM terminates.

## Expected Behavior

The `done` state should have visible incoming arrows from `count_new` with labels like `fail` or `fail/error`, rendered either as:
- A right-side branch arrow (since `count_new` and `done` could be on the same layer or adjacent layers)
- Or a forward edge with label connecting the two boxes

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: in `_render_layered_diagram()`, inter-layer edge rendering loop
- **Cause**: The inter-layer rendering (around line 785-812) only draws edges between **consecutive** layers. If `count_new` and `done` end up in non-adjacent layers (or if `done` is placed in its own layer at the bottom as an orphan), the branch edge is skipped. Additionally, branch edges classified as `forward_edge_labels` may not match any rendering path when the target is a terminal state placed outside the main flow.

## Proposed Solution

TBD - requires investigation. Potential approaches:
1. Ensure terminal states with incoming branch edges are placed in the layer immediately following their source state
2. Extend the inter-layer renderer to handle non-consecutive forward edges (similar to back-edge left-margin rendering but on the right margin)
3. Render orphan terminal states inline with their source layer as a side branch

## Implementation Steps

1. Trace how `done` gets its layer assignment — determine why it ends up disconnected
2. Fix layer assignment or rendering to ensure branch edges to terminal states are drawn
3. Add test case with branch-to-terminal topology
4. Verify with `issue-discovery-triage` and other loops that have terminal branch edges

## Impact

- **Priority**: P3 - Diagram is misleading but the state table below correctly shows all transitions
- **Effort**: Medium - Requires understanding the layered layout algorithm's edge routing
- **Risk**: Medium - Layout changes can affect rendering of all diagrams
- **Breaking Change**: No

## Labels

`diagram`, `rendering`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4cb1a514-1752-4f1f-9c34-c6be12fca682.jsonl`

---

## Status

**Open** | Created: 2026-03-12 | Priority: P3
