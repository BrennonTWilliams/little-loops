---
discovered_commit: aada94a41fd0595c3d4fbf63a9e0637c443383b9
discovered_branch: main
discovered_date: 2026-03-04T00:00:00Z
discovered_by: capture-issue
---

# BUG-574: FSM diagram drops multi-label edges — only first label rendered

## Summary

When multiple FSM transitions share the same `(src → dst)` pair (e.g. `on_failure`, `on_partial`, and `on_error` all routing to the same state), `_render_2d_diagram` collects all labels into `down_labels` but only renders `down_labels[0]`. The remaining labels are silently dropped, producing a diagram that misrepresents the loop's actual transition conditions.

## Location

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Line(s)**: 430, 436
- **Anchor**: `in function _render_2d_diagram`
- **Code**:
```python
# Line 430 — only first down label rendered
dlabel = down_labels[0]
# ...
# Line 436 — only first up label rendered
ulabel = up_labels[0]
```

## Current Behavior

For the `issue-refinement` loop, `evaluate` has three transitions to `fix` (`on_failure`, `on_partial`, `on_error`). The diagram only labels the `evaluate → fix` edge as **"fail"**, silently dropping "error" and "partial":

```
┌──────────┐             ┌──────┐
│ evaluate │───success──▶│ done │
└──────────┘             └──────┘
     │ ▲
fail │ │ next
     ▼ │
   ┌─────┐
   │ fix │
   └─────┘
```

## Expected Behavior

All transition labels for a given `(src → dst)` pair are shown, joined with `/`:

```
┌──────────┐             ┌──────┐
│ evaluate │───success──▶│ done │
└──────────┘             └──────┘
     │ ▲
fail/error/partial │ │ next
     ▼ │
   ┌─────┐
   │ fix │
   └─────┘
```

## Steps to Reproduce

1. Create or use any FSM loop where multiple `on_*` transitions from one state all target the same destination state (e.g. `on_failure: fix`, `on_partial: fix`, `on_error: fix`).
2. Run `ll-loop show <loop-name> --verbose`.
3. Observe the diagram only shows the first label (e.g. "fail"), not "fail/error/partial".

## Root Cause

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Lines**: 430, 436
- **Explanation**: `down_labels` and `up_labels` are lists that can contain multiple entries when several transitions share the same destination. The rendering code only indexes `[0]` rather than joining all entries.

## Motivation

Users running `ll-loop show` rely on the diagram to understand a loop's transition logic. When multiple conditions (e.g. `on_failure`, `on_partial`, `on_error`) all route to the same destination state, only one label appears — silently hiding the others. This makes it impossible to reason about loop behavior from the diagram alone, especially for loops with complex multi-condition routing.

## Proposed Solution

Replace index-based label access with a join across all labels in `_render_2d_diagram`:

```python
# In function _render_2d_diagram (loop/info.py)
dlabel = "/".join(down_labels)   # was: down_labels[0]
ulabel = "/".join(up_labels)     # was: up_labels[0]
```

## Impact

- **Priority**: P3 — Misleading diagram output affects loop comprehension but no runtime impact
- **Effort**: Small — Two-line change within a single function (`_render_2d_diagram`)
- **Risk**: Low — Display-only change; no effect on FSM execution or loop logic
- **Breaking Change**: No

## Labels

`bug`, `loop/show`, `fsm-diagram`, `display`

## Status

**Open** | Created: 2026-03-04 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ec4504aa-1767-4a8b-b2f5-3a9c180ea452.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a6371ba-ae5d-4081-b3ab-d18f243784b9.jsonl`
