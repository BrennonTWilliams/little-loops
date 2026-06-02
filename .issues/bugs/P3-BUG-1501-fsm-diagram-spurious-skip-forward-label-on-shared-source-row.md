---
id: BUG-1501
type: BUG
priority: P3
status: done
captured_at: '2026-05-16T14:12:59Z'
discovered_date: '2026-05-16'
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — sole renderer file; two-line change:
  1. Move `used_label_rows: set[int] = set()` (currently line 1231) to before the adjacent inter-layer loop at line 1040
  2. Inside the label-write block at lines 1115–1124, add `used_label_rows.add(label_row)` after `label_row = arrow_start_row` so each adjacent-layer label row is recorded before the skip-forward nudge pass runs

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:16–22` — imports `_render_fsm_diagram` for `ll-loop show`
- `scripts/little_loops/cli/loop/_helpers.py:408–410, 427` — calls `_render_fsm_diagram()` during `ll-loop run --show-diagrams`
- No caller-side changes needed; fix is internal to `_render_layered_diagram()`

### Similar Patterns
- `layout.py:1330–1345` — back-edge nudge block (BUG-1499 fix): verbatim template for the populate-then-check pattern; `used_label_rows` is read and written here
- `layout.py:1450–1465` — skip-forward nudge block: identical pattern; already reads `used_label_rows` — no change required, will benefit automatically once the set is pre-populated

### Tests
- `scripts/tests/test_ll_loop_display.py:1350–1375` — `TestRenderFsmDiagram.test_back_edge_labels_no_collision_on_shared_midpoint()`: exact template for the new regression test (fixture with arithmetic midpoint collision, assertions using `any(label in ln)` + `not any(both in same ln)`)
- New test belongs in the `TestRenderFsmDiagram` class, after line 1375

### Documentation
- No documentation changes required

---

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Move `used_label_rows` declaration** in `_render_layered_diagram()` (`layout.py:1231`): relocate `used_label_rows: set[int] = set()` to before the `for li in range(len(layers) - 1):` loop at line 1040. The comment at lines 1229–1231 moves with it.

2. **Populate `used_label_rows` in the adjacent inter-layer loop** (`layout.py:1115–1124`): after `label_row = arrow_start_row` (line 1115) and inside `if label_row < total_height:`, add `used_label_rows.add(label_row)`. This records each adjacent-layer label row before the skip-forward nudge pass runs.

3. **No changes needed in back-edge or skip-forward passes**: the nudge blocks at lines 1330–1345 and 1450–1465 already read and write `used_label_rows`. Pre-populating it is sufficient.

4. **Add regression test** in `TestRenderFsmDiagram` (`test_ll_loop_display.py` after line 1375`): 3-state FSM where layer-0 state `S` has both `S → layer1` (adjacent, label `"yes"`) and `S → layer2` (skip-forward, label `"error"`). Verify the row containing `"yes"` does not also contain `"error"`. Follow fixture and assertion structure from `test_back_edge_labels_no_collision_on_shared_midpoint` (lines 1350–1375).

5. **Verify**: `python -m pytest scripts/tests/test_ll_loop_display.py -v -k "collision or skip"`.

---

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
- `/ll:ready-issue` - 2026-05-17T14:03:00 - `84c55d0d-16b1-4406-9ef7-cff79317a1c0.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `08a32b43-a82c-44ca-870c-a3ed903e4428.jsonl`
- `/ll:wire-issue` - 2026-05-17T13:59:42 - `6bd8d2eb-0ceb-4004-9285-6618c0bf77a5.jsonl`
- `/ll:refine-issue` - 2026-05-17T13:55:31 - `5965c677-65b9-41f7-b51f-cbb05e9da3ac.jsonl`
- `/ll:capture-issue` - 2026-05-16T14:12:59Z - `f204025d-307a-4f4d-80b2-206dfd3b1de1.jsonl`
