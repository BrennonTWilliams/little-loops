---
discovered_date: 2026-03-12
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
status: done
completed_at: 2026-03-12T00:00:00Z
priority: P3
---

# BUG-708: Disconnected 90-degree skip-layer edge connectors in FSM diagram

## Summary

Right-margin skip-layer forward edges in the FSM diagram renderer had disconnected horizontal connectors when two skip-layer edges shared a common node. The horizontal connector drawing algorithm used right-to-left iteration that stopped at the first non-empty cell, so when an inner pipe's corner character (`┘`) was encountered, the outer pipe's horizontal line stopped short — producing a visually disconnected `┘─┐` pattern instead of a properly crossed `┴─┐`.

## Location

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Line(s)**: 1088–1105 (right-margin horizontal connectors), 1017–1029 (left-margin horizontal connectors)
- **Anchor**: `in function _render_layered_diagram()`

## Current Behavior

When two forward skip-layer edges shared a node (e.g. `route_format→route_score` and `route_score→refine_issues` in the `issue-refinement-git` loop), the outer pipe's horizontal connector only extended one `─` character at the shared node's row because the right-to-left drawing loop stopped at the inner pipe's `┘` corner. This produced a gap: `│◀─────────┘─┐` where `─┐` appeared visually disconnected from the target box.

## Expected Behavior

The outer pipe's horizontal connector should cross the inner pipe's vertical line with a proper junction character (`┴` or `┼`), producing a continuous connected line from the box edge to the outer pipe's corner.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: `in function _render_layered_diagram()`
- **Cause**: The horizontal connector drawing loops at lines 1088–1105 iterated right-to-left (`range(col - 1, src_right - 1, -1)`) and broke on any non-space character. When an earlier pipe's corner (`┘`, `┐`) or vertical line (`│`) occupied a cell, the loop stopped instead of replacing it with the appropriate crossing junction character.

## Proposed Solution

Replace right-to-left "stop at non-empty" iteration with left-to-right crossing-aware drawing that replaces pipe characters with appropriate junction characters:
- `│` → `┼` (vertical crossed by horizontal)
- `┘` → `┴` (bottom-right corner crossed by horizontal)
- `┐` → `┬` (top-right corner crossed by horizontal)
- `┤` → `┼` (right tee crossed by horizontal)

Apply the same symmetric crossing logic to left-margin back-edge horizontals using left-side corners (`└`→`┴`, `┌`→`┬`, `├`→`┼`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — `_render_layered_diagram()` horizontal connector loops

### Tests
- `scripts/tests/test_ll_loop_display.py` — `test_skip_layer_forward_edges_sharing_node_connected`

## Impact

- **Priority**: P3 — Visual rendering bug affecting diagram readability for complex FSMs with overlapping skip-layer edges
- **Effort**: Small — Replace simple break-on-non-empty loops with crossing-aware character replacement
- **Risk**: Low — Only affects ASCII art rendering; no functional FSM behavior changes
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `diagram`, `layout`, `rendering`

## Resolution

- **Status**: Completed
- **Resolved**: 2026-03-12
- **Fix**: Replaced right-to-left "stop at non-empty" horizontal connector drawing with left-to-right crossing-aware drawing in three locations:
  1. **Right-margin source horizontal** (line ~1088): Left-to-right iteration from box edge to pipe column, replacing `│`→`┼`, `┘`→`┴`, `┐`→`┬`, `┤`→`┼` instead of stopping.
  2. **Right-margin destination horizontal** (line ~1098): Same crossing-aware logic for the destination row.
  3. **Left-margin back-edge horizontals** (line ~1017): Symmetric crossing logic for left-side corners (`└`→`┴`, `┌`→`┬`, `├`→`┼`) to prevent same class of bug on back-edges.
- **Tests added**:
  - `test_ll_loop_display.py`: `TestRenderFsmDiagram.test_skip_layer_forward_edges_sharing_node_connected` — 8-state FSM with two skip-layer forward edges sharing a node; asserts both `◀` arrows render, no disconnected gap pattern, and proper junction characters (`┴`/`┼`) at crossings.
- **Verification**: 87 tests pass in `test_ll_loop_display.py`; `ll-loop s issue-refinement-git` visually confirmed with proper `┴` junction at `route_score` row.

## Session Log
- manual implementation - 2026-03-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/41705aee-6f1d-4d7e-91b5-29119174b2f5.jsonl`

---

**Completed** | Created: 2026-03-12 | Priority: P3
