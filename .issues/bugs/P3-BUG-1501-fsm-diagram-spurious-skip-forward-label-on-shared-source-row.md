---
id: BUG-1501
type: BUG
priority: P3
status: open
captured_at: "2026-05-16T14:12:59Z"
discovered_date: "2026-05-16"
discovered_by: capture-issue
---

# BUG-1501: FSM diagram spurious skip-forward label appears on shared source row

## Summary

When a state is the source of both an adjacent-layer edge and a skip-forward edge, the skip-forward label can land on the same row as the adjacent edge's inter-layer label, producing a spurious-looking label in the route. Observed on `resolve_input` in the `eval-specfile-gold` loop: line 33 reads `│─yes──…──┐ error` — the `error` belongs to `resolve_input.on_error → failed` (a skip-forward) but appears mid-route on the `yes` channel.

## Current Behavior

Line 33 of the rendered diagram shows an `error` label written near the `resolve_input → run_specfile (yes)` arrow row, suggesting the `yes` edge has an `error` annotation. It does not — `error` is the label of a separate skip-forward edge from the same source.

## Expected Behavior

Each label should occupy a row uniquely associated with its own edge. Skip-forward labels should not coincide with adjacent-layer label rows on a shared source.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: skip-forward label placement at `layout.py:1420-1426`, interacting with the adjacent inter-layer label written at `layout.py:1110-1116`.
- **Cause**: Forward skip-layer label placement reuses `(top_row + bot_row) // 2` with no awareness of rows already used by adjacent-layer labels. When the skip edge and the adjacent edge share a source, their computed rows coincide.

## Proposed Solution

Same shape as BUG-1499:

1. During forward-edge rendering, populate a `used_label_rows: set[int]` keyed by margin/column band.
2. Pass it into the skip-forward pass; when the computed `label_row_pos` is in the set, nudge ±1 row to find a free row within the edge's vertical span.
3. Consider sharing one `used_label_rows` structure across back-edge, forward, and skip-forward passes so labels never collide regardless of edge class.

## Steps to Reproduce

1. `cd /Users/brennon/AIProjects/ai-workspaces/blender-agents`
2. `ll-loop show eval-specfile-gold`
3. Inspect line 33 — observe `error` rendered on the `resolve_input` `yes` row.

## Impact

- **Severity**: Medium (semantically misleading — readers misattribute labels to wrong edges).
- **Affects**: Loops where a state has both adjacent and skip-forward edges.
- **Workaround**: None; readers must cross-reference the YAML.

## Test Plan

Add a case in `scripts/tests/test_ll_loop_display.py`:

- Fixture: 3-layer FSM where layer-0 state `S` has both `S → layer1` and `S → layer2` (skip-forward).
- Assert the rendered row containing the `S → layer1` label does not contain the skip-forward label text.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/cli/loop/layout.py` | Renderer under repair |
| `~/.claude/plans/investigate-the-fsm-loop-twinkly-bear.md` | Source investigation plan (Bug D) |

Closely related: BUG-1499 (shares the `used_label_rows` fix mechanism).

## Labels

- area:fsm-diagram
- area:renderer

## Status

- **Discovered**: 2026-05-16 via investigation plan against `eval-specfile-gold`
- **Captured by**: `/ll:capture-issue`

## Session Log
- `/ll:capture-issue` - 2026-05-16T14:12:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f204025d-307a-4f4d-80b2-206dfd3b1de1.jsonl`
