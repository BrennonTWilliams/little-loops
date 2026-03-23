---
id: BUG-759
type: BUG
priority: P3
status: active
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 100
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **ANSI injection path**: `_draw_box()` (`layout.py:546`) contains `_bc()` at line 564–565: `return colorize(ch, highlight_color) if is_highlighted else ch`. Every box-drawing character (┌, ─, ┐, │, └, ┘) written into the grid cell becomes an ANSI-colored string (e.g. `\033[32m┌\033[0m`) when `is_highlighted=True`.
- **`_colorize_diagram_labels()` is NOT the source**: It is called at line 1419 — AFTER the centering block at lines 1413–1417 — and operates on the final `"\n".join(lines)` string. Edge label ANSI codes from `_colorize_diagram_labels()` do not affect `max_line_len` measurement. Only `_draw_box()`'s box-character colorization does.
- **`re` is already imported** at `layout.py:12`. No new import needed for the fix.
- **`_wcswidth` is imported** at `layout.py:15` (`from wcwidth import wcswidth as _wcswidth`). No module-level ANSI regex is currently defined in `layout.py`.

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

> **Note**: The original `total_width` substitution was incorrect — see Go/No-Go Findings below. Use ANSI-stripped measurement instead.

Strip ANSI escape codes before measuring line width. `layout.py` already imports `re` (line 12), so no new imports are needed. Add a module-level compiled pattern and replace the two centering lines:

```python
# Add near top of module (after existing imports, before first function)
_ANSI_ESCAPE_RE = re.compile(r"\033\[[0-9;]*m")

# In _render_layered_diagram(), replace lines 1414–1415:
# Before (buggy)
max_line_len = max((len(ln) for ln in lines), default=0)
diagram_indent = max(0, (tw - max_line_len) // 2)

# After (correct)
max_line_len = max((len(_ANSI_ESCAPE_RE.sub("", ln)) for ln in lines), default=0)
diagram_indent = max(0, (tw - max_line_len) // 2)
```

**Why `len()` is sufficient** (not `_wcswidth`): The grid cells contain only ASCII and box-drawing characters (`─ │ ┌ ┐ └ ┘ ▶ ▲`), all of which have wcwidth=1. Using `len()` on ANSI-stripped strings gives the correct visual width.

**Why `total_width` is wrong**: `total_width` is computed as `max(total_content_w + right_edge_margin + 4, tw)`, which clamps to a minimum of `tw`. Substituting it into `max(0, (tw - total_width) // 2)` always produces 0, silently removing all centering.

Note: `_render_horizontal_simple()` is not affected — it uses `(tw - (x + 4)) // 2` where `x` is a raw integer column index, never string length.

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
2. Add `_ANSI_ESCAPE_RE = re.compile(r"\033\[[0-9;]*m")` after the import block — after line 19 (`from little_loops.fsm.schema import FSMLoop, StateConfig`), before the first function definition
3. At line 1414, replace:
   ```python
   max_line_len = max((len(ln) for ln in lines), default=0)
   ```
   with:
   ```python
   max_line_len = max((len(_ANSI_ESCAPE_RE.sub("", ln)) for ln in lines), default=0)
   ```
   Leave `diagram_indent = max(0, (tw - max_line_len) // 2)` at line 1415 unchanged
4. Run `python -m pytest scripts/tests/test_ll_loop_display.py -v` to verify no regressions
5. **Consider adding a centering assertion**: The existing test suite has zero assertions about `diagram_indent` consistency. A regression test rendering the same FSM with and without `highlight_state` and asserting equal left-indent would prevent future regressions (model after existing patterns in `test_ll_loop_display.py`)
6. Manually verify with `ll-loop run loops/issue-refinement.yaml --show-diagrams --clear` — diagram should stay horizontally fixed across all state transitions

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

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-03-23_ — **NO-GO (REFINE)**

**Deciding Factor**: The proposed fix (`diagram_indent = max(0, (tw - total_width) // 2)`) is provably incorrect — `total_width = max(total_content_w + right_edge_margin + 4, tw)` means `total_width >= tw` always, so `diagram_indent` would always be 0, silently disabling centering rather than fixing it. The test suite has zero centering assertions, so this regression would go undetected.

### Key Arguments For
- Bug is confirmed real at lines 1414–1415; ANSI overhead collapses indent by up to 20 columns on every highlighted frame, completely breaking `--show-diagrams --clear`
- All necessary infrastructure is already present in the codebase for a correct fix

### Key Arguments Against
- The proposed `total_width` substitution always produces `diagram_indent = 0`, removing centering entirely for all FSM topologies
- The correct fix should use ANSI-stripped line measurement: `_strip_ansi()` already exists in `show.py:208–212` and `_wcswidth` is already imported in `layout.py:15`; the actual fix is `max_line_len = max((_wcswidth(_strip_ansi(ln)) for ln in lines), default=0)` (or equivalent using `len(_strip_ansi(ln))`)

### Rationale
The bug is real and fixing it is clearly valuable, but the proposed solution is mathematically wrong. The correct fix must use ANSI-aware width measurement rather than `total_width`. The issue should be updated to specify `_strip_ansi()` or `_wcswidth` before implementation.

## Session Log
- `/ll:confidence-check` - 2026-03-23T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c2e0332-088f-4fa7-a7f5-c437b25f8efa.jsonl`
- `/ll:refine-issue` - 2026-03-23T21:35:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e396250c-81bc-42fa-9e39-b83a9269bb20.jsonl`
- `/ll:confidence-check` - 2026-03-23T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/24372921-3a00-4768-88b4-ef90d1d5064f.jsonl`
- `/ll:refine-issue` - 2026-03-23T21:22:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b5430f1-ebbd-470d-a185-8171502097ea.jsonl`
- `/ll:go-no-go` - 2026-03-23T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a533c1a2-57c6-484f-bd02-5153708e92fd.jsonl`
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
