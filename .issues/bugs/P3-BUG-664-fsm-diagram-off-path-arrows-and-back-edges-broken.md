---
id: BUG-664
priority: P3
status: active
discovered_date: 2026-03-09
discovered_by: capture-issue
confidence_score: null
outcome_confidence: null
---

# BUG-664: FSM Diagram Off-Path Arrows and Back-Edges Broken

## Summary

`ll-loop info` renders a broken ASCII diagram for `issue-refinement-git.yaml`. The 5-state off-path chain (`format_issues → score_issues → refine_issues → check_commit → commit`) has three distinct rendering bugs: inter-box arrows have no labels or arrowheads, right-going arrows target box centers instead of left edges, and back-edges to main-path states render as misleading inward-pointing left-arrows at the source box.

## Root Cause

**File**: `scripts/little_loops/cli/loop/info.py`, function `_render_2d_diagram`

Three bugs in the off-path rendering logic:

1. **Bug 1 — Hardcoded gap too small (line ~568)**: Off-path box gap is hardcoded to `4`, but labeled arrows need at least `len(label) + 6` characters. Arrows overflow into destination boxes, hiding labels and arrowheads.

2. **Bug 2 — Wrong target column for right-going arrows (line ~935)**: `col_center.get(dst, ...)` is used instead of `col_start.get(dst, ...)`. The arrowhead lands inside the destination box, overwriting its border content.

3. **Bug 3 — Back-edges rendered as inward left-arrows (lines ~947–953)**: Left-going back-edges (`check_commit → evaluate`, `commit → evaluate`) are drawn as `◀──label─` immediately left of the source box wall. This looks like an incoming arrow, multiple back-edges from the same state overlap, and there's no visual connection back to `evaluate`.

## Reproduction

```bash
ll-loop info .loops/issue-refinement-git.yaml
```

Expected: bottom row shows `format_issues ──next──▶ score_issues ──next──▶ ... ──success──▶ commit` with back-edge routes pointing up to `evaluate`.

Actual: bare `────` between boxes, no arrowheads visible, and `◄──error─│ check_commit │` appearing as if arrows point into the box.

## Fix

### Fix 1: Dynamic gap for off-path boxes

In the off-path placement loop (~line 568–588), compute minimum gap per adjacent pair from edge labels:

```python
min_gap_for_label = max(
    (len(lbl) + 6 for s, d, lbl in branches + back_edges
     if s == prev_off and d == off_s),
    default=4
)
gap = max(4, min_gap_for_label)
```

### Fix 2: Use `col_start` as right-going arrow target

Line ~935, change:
```python
target_col = col_center.get(dst, start_col + len(label) + 4)
```
to:
```python
target_col = col_start.get(dst, start_col + len(label) + 4)
```

### Fix 3: Render off-to-main back-edges as U-routes

Add a new bucket `off_to_main_back` during edge classification. When `src in off_path_set and dst in main_path_set`, route to `off_to_main_back` instead of `off_state_edges[src]`. After the off-path grid, render as below-grid U-routes:
- One row with `│` at src column and `▲` at dst column
- One row with `└─ label ─...─┘` horizontal bar

## Affected Files

- `scripts/little_loops/cli/loop/info.py` — Three targeted fixes within `_render_2d_diagram`
- `scripts/tests/test_ll_loop_display.py` — Add regression test for the 7-state issue-refinement-git topology

## Regression Test

Add a test that builds the `issue-refinement-git` topology (evaluate/format_issues/score_issues/refine_issues/check_commit/commit/done) and asserts:
1. All 7 states appear in boxes with `│` borders
2. A `▶` right-arrow appears between each adjacent off-path state pair
3. A `▲` or `↩` back-edge indicator appears for `check_commit → evaluate` and `commit → evaluate`
4. No `◀` left-arrow appears immediately adjacent to `check_commit` or `commit` left walls

## Verification

```bash
# Run existing tests (must stay green)
python -m pytest scripts/tests/test_ll_loop_display.py -v

# Visual spot-check
ll-loop info .loops/issue-refinement-git.yaml
```

## Session Log
- `/ll:capture-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01f82782-0b8c-4ad7-bf21-b0fbd48b9fa2.jsonl`
