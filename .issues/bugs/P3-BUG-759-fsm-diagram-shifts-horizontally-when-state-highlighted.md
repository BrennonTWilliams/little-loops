---
id: BUG-759
type: BUG
priority: P3
status: active
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# BUG-759: FSM Diagram Shifts Horizontally When State Is Highlighted

## Summary

When running `ll-loop run ... --show-diagrams --clear`, the FSM diagram is redrawn in-place on each state transition. For states that have highlighted boxes, the entire diagram shifts horizontally — breaking the animation effect. The root cause is that `_render_layered_diagram()` measures line width using `len()` on strings that already contain embedded ANSI escape codes, inflating the measured width and causing an incorrect (variable) horizontal indent.

## Current Behavior

Running `ll-loop run <loop.yaml> --show-diagrams --clear` shows the FSM diagram jumping left/right as different states become active. The indent changes frame-to-frame because ANSI color codes inflate `len(line)`, causing `(tw - max_line_len)` to shrink (or go negative, floored to 0) only on frames where the highlighted state's box appears.

## Expected Behavior

The diagram stays horizontally fixed at a consistent indent across all state transitions. Only the highlighted box styling should change between frames.

## Motivation

The horizontal jitter makes the `--show-diagrams --clear` animation visually broken and hard to follow. This is the primary use case for `--show-diagrams` — real-time loop monitoring. The fix is a one-line change using an already-computed variable.

## Steps to Reproduce

1. Run `ll-loop run loops/issue-refinement.yaml --show-diagrams --clear`
2. Watch the diagram as the loop transitions through states
3. Observe: diagram shifts left/right depending on which state is highlighted

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: `in _render_layered_diagram()` (lines 1414–1415 current; was 1308–1309 at scan commit)
- **Cause**: After assembling the grid into string lines (`lines = ["".join(row).rstrip() for row in grid]`), the centering logic computes `max_line_len = max((len(ln) for ln in lines), default=0)`. When `_draw_box()` writes ANSI-colored strings into grid cells for the highlighted state (e.g., `┌` → `\033[32m┌\033[0m`), `"".join(row)` contains multi-byte escape sequences that inflate `len(ln)` far beyond the visual width. This makes `(tw - max_line_len)` smaller (or negative, clamped to 0) on highlighted frames, reducing the indent and causing the leftward shift.

## Location

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Line(s)**: 1414–1415 (at scan commit: b8dad90; shifted since original scan)
- **Anchor**: `in _render_layered_diagram()`
- **Code**:
```python
max_line_len = max((len(ln) for ln in lines), default=0)
diagram_indent = max(0, (tw - max_line_len) // 2)
```

## Proposed Solution

Replace the flawed `max_line_len` computation with `total_width`, which is already computed earlier in `_render_layered_diagram()` (line 871) as the true visual column-count of the grid:

```python
# Before
max_line_len = max((len(ln) for ln in lines), default=0)
diagram_indent = max(0, (tw - max_line_len) // 2)

# After
diagram_indent = max(0, (tw - total_width) // 2)
```

`total_width` is computed as `max(total_content_w + right_edge_margin + 4, tw)` — the intended visual width independent of ANSI coloring. This makes `diagram_indent` a stable constant for a given FSM topology.

Note: `_render_horizontal_simple()` is not affected — it uses `(tw - (x + 4)) // 2` where `x` is a raw integer column index.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — lines 1308–1309 (the only change needed)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/layout.py` — `_render_layered_diagram()` is called from `render_fsm_diagram()`
- `scripts/little_loops/cli/loop/runner.py` — calls `render_fsm_diagram()` for `--show-diagrams`

### Similar Patterns
- `_render_horizontal_simple()` (`layout.py:1503`) — uses integer column `x` directly, not string length; already correct

### Tests
- `scripts/tests/test_ll_loop_display.py` — existing display tests; run to verify no regressions

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/cli/loop/layout.py`
2. At lines 1308–1309, delete the `max_line_len = ...` line and replace `max_line_len` in the `diagram_indent` expression with `total_width`
3. Run `python -m pytest scripts/tests/test_ll_loop_display.py -v` to verify no regressions
4. Manually verify with `ll-loop run loops/issue-refinement.yaml --show-diagrams --clear` — diagram should stay horizontally fixed across all state transitions

## Impact

- **Priority**: P3 - Visual rendering bug; breaks the animation effect of `--show-diagrams --clear` but no functional impact
- **Effort**: Small - One line change, `total_width` already in scope
- **Risk**: Low - Purely cosmetic fix; `total_width` is the semantically correct variable
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `fsm-diagram`, `ansi`, `rendering`, `captured`

## Verification Notes

- **Date**: 2026-03-21
- **Verdict**: NEEDS_UPDATE → VALID (line numbers corrected)
- `max_line_len` / `diagram_indent` bug confirmed present at lines **1414–1415** in current codebase (shifted from 1308–1309 at original scan commit b8dad90). Bug still exists; fix not yet applied.

## Session Log
- `/ll:verify-issues` - 2026-03-22T02:49:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca8bfb19-1675-49ac-9d46-6c3933a7cb31.jsonl`
- `/ll:verify-issues` - 2026-03-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/45cffc78-99fd-4e36-9bcb-32d53f60d9c2.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:verify-issues` - 2026-03-16T19:47:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:verify-issues` - 2026-03-16T19:47:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:format-issue` - 2026-03-16T19:45:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`

- `/ll:capture-issue` - 2026-03-15T22:49:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Status

**Open** | Created: 2026-03-15 | Priority: P3
