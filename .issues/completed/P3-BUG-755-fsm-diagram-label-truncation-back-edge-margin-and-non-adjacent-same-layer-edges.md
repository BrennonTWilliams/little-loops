---
id: BUG-755
priority: P3
type: BUG
status: completed
title: "FSM diagram label truncation: back-edge margin and non-adjacent same-layer edges"
discovered_date: 2026-03-15
discovered_by: capture-issue
completed_date: 2026-03-15
---

# BUG-755: FSM diagram label truncation: back-edge margin and non-adjacent same-layer edges

## Summary

`ll-loop s issue-refinement` rendered several transition labels truncated: `"erro"` (should be `"error"`), `"no/e"` (should be `"no/error"`), and `"ext"` (should be `"next"`). Two independent bugs in `scripts/little_loops/cli/loop/layout.py` caused this.

## Root Cause

### Bug 1 — Back-edge margin too narrow for 5+ pipes ("erro", "no/e")

`back_edge_margin = max_label_len + 6` assumed at most 3 back-edge pipes. With `n` back edges, pipes occupy columns `1, 3, 5, …, 2n−1`, so:

```
label_start     = rightmost_pipe_col + 2 = 2n + 1
available chars = content_left − 1 − label_start = back_edge_margin − 2n
```

The issue-refinement loop has **5 back edges** (all pointing to `evaluate`): `parse_id→evaluate`, `route_format→evaluate`, `route_score→evaluate`, `check_commit→evaluate`, `commit→evaluate`. With `max_label_len = 8` ("no/error") and `n = 5`:

- `back_edge_margin = 14`, `content_left = 16`
- `available = 14 − 10 = 4` chars

"error" (5) → "erro"; "no/error" (8) → "no/e".

**File/Function**: `layout.py::_compute_sugiyama_layout` — initial estimate (~line 686) and post-reclassification recalc (~line 826).

### Bug 2 — Non-adjacent same-layer edge label obscured by intermediate box ("ext")

`score_issues`, `refine_issues`, and `check_commit` end up in the same layer (layer 5). `score_issues → check_commit` and `refine_issues → check_commit` are classified as same-layer right-to-left edges. The renderer right-justifies edge_text `"─next──▶"` across the **full span** (from `check_commit` right to `refine_issues` left), but `score_issues` sits in the middle. With the default `gap_between = 6` between `score_issues` and `refine_issues`:

- `left_dashes = W_score + 8` — chars `"─n"` land on the protected `score_issues` box cells and are silently dropped
- Only `"ext──▶"` appears in the 6-char gap, looking like a truncated label

**File/Function**: `layout.py::_compute_sugiyama_layout` — same-layer gap recalculation loop (~line 803).

## Fix

**Bug 1** — Scale margin with pipe count (two locations):

```python
# was: back_edge_margin = max_label_len + 6
n_back_initial = len(non_self_back_initial)
back_edge_margin = max_label_len + max(6, 2 * n_back_initial + 2)
```

**Bug 2** — Before the adjacent-pair gap loop, collect `extra_gap_req` from non-adjacent same-layer edges. For a right-to-left spanning edge (`si > di + 1`), the label needs to fit in the gap immediately left of the source (`layer[si−1], src`). For left-to-right (`di > si + 1`), it needs to fit in the gap to the right of the source:

```python
extra_gap_req: dict[tuple[str, str], int] = {}
for src, dst, lbl in same_layer_edges:
    ...
    if abs(si - di) <= 1:
        continue  # adjacent — already handled
    key = (layer[si - 1], src) if si > di else (src, layer[si + 1])
    extra_gap_req[key] = max(extra_gap_req.get(key, 0), len(lbl))

# In the gap calculation loop:
max_label = max(len(label_fwd), len(label_rev), extra_gap_req.get((sname, next_s), 0))
```

This widens the gap between `score_issues` and `refine_issues` to `max(6, 4+6) = 10`, ensuring `"─next──▶"` lands entirely in open space.

## Files Changed

- `scripts/little_loops/cli/loop/layout.py`
  - Lines 686–689: `back_edge_margin` initial estimate uses `max(6, 2 * n_back_initial + 2)`
  - Lines 824–828: `back_edge_margin` post-reclassification recalc uses same formula
  - Lines 795–828: Added `extra_gap_req` dict and incorporated into gap calculation

## Verification

All 3521 tests pass. `ll-loop s issue-refinement` now shows full labels:
- `error` (back-edge pipes, 5 edges)
- `no/error` (merged back-edge label)
- `next` (non-adjacent same-layer edge, via wider gap)

## Session Log
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
