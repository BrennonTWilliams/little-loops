---
discovered_date: 2026-03-12
discovered_by: capture-issue
confidence_score: 83
outcome_confidence: 75
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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — Add right-margin forward-skip renderer (~line 976), extend margin width calculation (~line 659)

### Key Code Locations
- `layout.py:816-852` — Inter-layer forward edge renderer (consecutive-only, the gap)
- `layout.py:907-976` — Left-margin back-edge renderer (pattern to mirror)
- `layout.py:637-661` — Margin width pre-computation (extend for right margin)
- `layout.py:605-624` — `forward_edge_labels` population
- `layout.py:732-748` — Edge reclassification after layer assignment (BUG-679 addition)

### Dependent Files
- `scripts/little_loops/cli/loop/info.py` — Calls `_render_fsm_diagram()`, no changes needed
- `scripts/little_loops/fsm/schema.py:239-263` — `StateConfig.from_dict` parses `on_failure`/`on_error`

### Similar Patterns (BUG-679 Fix)
- `layout.py:637-655` — Pre-compute back-edge labels for margin width estimation
- `layout.py:907-976` — Full left-margin rendering loop (sort by span, claim columns, draw pipes/connectors/corners/arrows/labels)
- Commit `564df03` — BUG-679 fix for backward skip-layer edges

### Tests
- `scripts/tests/test_ll_loop_display.py:1001-1033` — BUG-679 regression test (pattern to follow)
- `scripts/tests/test_ll_loop_display.py:634` — `TestRenderFsmDiagram` class
- `scripts/tests/test_ll_loop_display.py:47-95` — `make_test_state`/`make_test_fsm` helpers

### Configuration
- `loops/issue-discovery-triage.yaml:76-77` — Production loop triggering this bug (`count_new.on_failure: done`, `count_new.on_error: done`)

### Related Issues
- `P3-BUG-679` (completed) — Symmetric sibling: main-path cycle edges not rendered (backward skip-layer)
- `P3-FEAT-670` (completed) — FSM diagram adaptive layout engine (introduced the layered renderer)
- `P2-BUG-672` (completed) — Back-edge rendering bugs

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: `_render_layered_diagram()`, inter-layer edge rendering loop at lines 816-852
- **Cause**: Forward skip-layer edges fall through all 3 rendering paths without being drawn.

### Detailed Analysis

The rendering pipeline has 3 edge-drawing paths, none of which handles forward edges spanning non-consecutive layers:

1. **Inter-layer forward renderer** (`layout.py:827-831`) — only pairs `layers[li]` × `layers[li+1]` (consecutive layers). If `count_new` is at layer N and `done` is at layer N+2, the edge `(count_new, done)` is in `forward_edge_labels` but never matched.

2. **Same-layer renderer** — only handles `dst_layer == src_layer`. Not applicable.

3. **Left-margin back-edge renderer** (`layout.py:907-976`) — only handles `dst_layer < src_layer`. Not applicable for forward edges.

The edge data flow confirms the edge is correctly tracked but never rendered:
- `_collect_edges()` (line 140-143) produces `("count_new", "done", "fail")` and `("count_new", "done", "error")`
- `_classify_edges()` (line 198) places both in `branches` (since `done` is later in BFS order)
- `forward_edge_labels` (line 611) correctly stores `("count_new", "done"): "fail/error"`
- Reclassification (line 735) keeps it in `forward_edge_labels` (since `dst_layer > src_layer`)
- Inter-layer loop (line 827) never finds it because `src` and `dst` are in non-adjacent layers

## Proposed Solution

Add a **right-margin forward-skip renderer**, symmetric to the left-margin back-edge renderer at `layout.py:907-976`.

### Approach

After the inter-layer rendering loop (line 852), collect any `forward_edge_labels` entries that were not consumed by the consecutive-layer loop (i.e., edges where `dst_layer > src_layer + 1`). Render these as right-margin vertical pipes with horizontal connectors:

- Vertical `│` pipe in the right margin from source row down to destination row
- Horizontal `─` connectors from source box's right side to the pipe, and from the pipe to destination box's right side
- Corner glyphs (`┐`/`┬` at top, `┘`/`┴` at bottom)
- `◀` arrow tip at the destination box's right side
- `▼` could also work — use `◀` for visual distinction from consecutive-layer `▼` arrows
- Label placed left of the pipe, mirroring the back-edge label placement

### Why Right-Margin

This mirrors the BUG-679 fix pattern (`layout.py:907-976`) which renders backward skip-layer edges on the left margin. Forward skip-layer edges on the right margin creates a clear visual convention: left = backward, right = forward-skip. The existing consecutive-layer renderer continues to handle adjacent-layer forward edges with centered `▼` arrows.

### Margin Width

Extend the margin calculation at `layout.py:659-661` to account for right-margin pipes, similar to how `all_back_labels` pre-computation at lines 637-655 estimates left-margin width.

## Implementation Steps

1. **Identify unconsumed forward edges** — After the inter-layer loop (`layout.py:852`), iterate `forward_edge_labels` to find entries where `layer_of[dst] > layer_of[src] + 1`. Collect these as `skip_forward_edges`.

2. **Pre-compute right margin width** — Mirror the left-margin calculation at `layout.py:637-661`. Count skip-forward edges and their label lengths to determine `right_margin_width`. Add this to `total_width` at grid allocation.

3. **Render right-margin pipes** — Add a new block after the back-edge renderer (~line 976), following the same structure as `layout.py:907-976`:
   - Sort by span length (longest first) for column allocation
   - Claim right-margin columns (spaced 2 apart, starting from rightmost content + 2)
   - Draw vertical `│` from `src_row` to `dst_row`
   - Draw horizontal `─` connectors from box right edges to margin pipe
   - Place corner glyphs (`┐`/`┘`) and arrow tip (`◀`) at destination
   - Place label left of all pipes, centered vertically

4. **Add regression test** — In `test_ll_loop_display.py`, add a test following the BUG-679 pattern at line 1001-1033:
   ```python
   def test_branch_to_terminal_skip_layer_renders_edge(self):
       # FSM where terminal state is 2+ layers from branch source
       # Assert: ◀ or right-margin connector present
       # Assert: done state has incoming visual connection
   ```

5. **Verify with production loops** — Run `ll-loop s issue-discovery-triage` and confirm `done` has a visible incoming arrow from `count_new` with `fail/error` label

## Impact

- **Priority**: P3 - Diagram is misleading but the state table below correctly shows all transitions
- **Effort**: Medium - Requires understanding the layered layout algorithm's edge routing
- **Risk**: Medium - Layout changes can affect rendering of all diagrams
- **Breaking Change**: No

## Labels

`diagram`, `rendering`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4cb1a514-1752-4f1f-9c34-c6be12fca682.jsonl`
- `/ll:ready-issue` - 2026-03-12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/99054310-66fb-46ec-8958-729542a8612a.jsonl`
- `/ll:confidence-check` - 2026-03-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad46fd10-a28c-45a0-b135-7e8eb5e6691b.jsonl`
- `/ll:refine-issue` - 2026-03-12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c12ab473-91e6-418f-9bc2-afa5200c5133.jsonl`
- `/ll:ready-issue` - 2026-03-12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ce22b31f-c86d-405e-81b7-51f36fa9812d.jsonl`

## Resolution

**Fixed** — Added right-margin forward-skip edge renderer in `layout.py`, symmetric to the existing left-margin back-edge renderer. Forward edges spanning 2+ layers are now rendered with right-margin vertical pipes, horizontal connectors, corner glyphs, `◀` arrowheads, and labels.

### Changes
- `scripts/little_loops/cli/loop/layout.py` — Added skip-forward edge identification, right margin width pre-computation, and right-margin rendering block (~60 lines)
- `scripts/tests/test_ll_loop_display.py` — Added regression test `test_branch_to_terminal_skip_layer_renders_edge`

---

## Status

**Resolved** | Created: 2026-03-12 | Resolved: 2026-03-12 | Priority: P3
