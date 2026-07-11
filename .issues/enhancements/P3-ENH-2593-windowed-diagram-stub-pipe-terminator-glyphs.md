---
id: ENH-2593
title: windowed-diagram stub-pipe terminator glyphs at cut boundaries
type: ENH
priority: P3
status: done
completed_at: 2026-07-10T23:44:35Z
discovered_date: 2026-07-10
discovered_by: user-request
labels:
  - enhancement
  - cli
  - diagram
  - ll-loop
---

# ENH-2593: Windowed-diagram stub-pipe terminator glyphs at cut boundaries

## Summary

When `ll-loop run … --show-diagrams clean` (or any preset resolving to the
`window` rung of the pinned-pane fallback ladder) crops a tall FSM to the
±K layers around the active state, the overflow banners
(`▲ N layers above …` / `▼ M layers below …`) tell the reader what is
hidden — but the **stub pipes that cross the crop boundary** still appear
as bare `│` characters whose only visible end is the in-window side. They
read as ordinary inter-state connectors that abruptly stop, with no
in-band hint that the connection continues off-screen.

Replace those bare `│` stubs at the cut rows with open half-circle arc
terminators:

- **Top cut** (pipe enters the window from above): `◠` — U+25E0
  UPPER HALF CIRCLE. Curve up, flat down (against visible
  content).
- **Bottom cut** (pipe exits the window below): `◡` — U+25E1
  LOWER HALF CIRCLE. Curve down, flat up (against visible
  content).

`cell.replace("│", glyph)` preserves the surrounding SGR color so the
terminator continues the pipe's color in band.

## Motivation

The current behavior requires the reader to mentally cross-check the
overflow banner to understand why a pipe "dies in the middle of nowhere."
With a terminator glyph at the cut row, the "this edge leaves the windowed
view" signal is unambiguous at a glance.

The two glyphs are from the same Geometric Shapes block (`U+25xx`) the
diagram already uses (`▼`, `◀`, `◉`), so they slot in without disturbing
the existing visual vocabulary.

## Current Behavior

`scripts/little_loops/cli/loop/layout.py:_render_layered_diagram` crops
the layered grid at `window_top = _layer_top(lo)` and
`window_bot = _layer_bottom(hi)` and emits the `▲`/`▼` banners. Margin
pipes in `margin_pipe_spans` whose window slice contains **neither**
endpoint (full pass-through) are blanked (Case 3 — ENH-2432). Stub pipes
with one endpoint visible are kept as bare `│` characters whose only
visible end is the in-window side.

## Expected Behavior

After this change:

- Pipes whose top endpoint is above the window (Case 1, top stub):
  the topmost visible cell at `grid[window_top]` becomes `◠` instead
  of `│`.
- Pipes whose bottom endpoint is at or below the window (Case 2,
  bottom stub): the bottommost visible cell at `grid[window_bot - 1]`
  becomes `◡` instead of `│`.
- Full-span pipes (Case 3 — both endpoints cropped) remain blanked.
  They do not terminate; they pass through. Adding terminators there
  would conflict with the existing `test_pass_through_back_edge_pipe_is_blanked`
  invariant.
- Non-`│` cells at the boundary (corners `┐`/`┘`, junctions `┼`,
  horizontal connectors `─`, self-loop markers `◉`) are left as-is —
  the `strip_ansi(...) == "│"` guard prevents over-replacement.

## Proposed Solution

In `_render_layered_diagram` (`layout.py:1899-1915`), after the existing
full-span-blanking loop and before the grid slice
(`grid = grid[window_top:window_bot]`), add two scan-and-replace passes
on the boundary rows of the full grid:

```python
if lo > 0:
    top_row_cells = grid[window_top]
    for c in range(total_width):
        if strip_ansi(top_row_cells[c]) == "│":
            top_row_cells[c] = top_row_cells[c].replace("│", "◠")
if hi < n_layers - 1:
    bot_row_cells = grid[window_bot - 1]
    for c in range(total_width):
        if strip_ansi(bot_row_cells[c]) == "│":
            bot_row_cells[c] = bot_row_cells[c].replace("│", "◡")
```

The `cell.replace("│", glyph)` form preserves the surrounding SGR color
codes — `"\x1b[3Xm│\x1b[0m"` becomes `"\x1b[3Xm◠\x1b[0m"` — so the
terminator visually continues the pipe's color. `strip_ansi` is the
same helper the existing blanking block uses
(`layout.py:1909`).

The pass scans the entire boundary row (not just `margin_pipe_spans`
columns) so forward inter-layer pipes with `│` cells at the boundary
also get terminated if they exist. In practice, forward inter-layer
pipes between adjacent layers without self-loops have empty `│` ranges
(the boxes stack directly with only `▼` arrows between them), so the
pass only fires on margin pipes in the common case — which is exactly
where the visual problem manifests.

## Acceptance Criteria

- [x] Stub pipe at the top cut boundary shows `◠` (upper half
      circle) at `grid[window_top]` instead of bare `│`.
- [x] Stub pipe at the bottom cut boundary shows `◡` (lower half
      circle) at `grid[window_bot - 1]` instead of bare `│`.
- [x] Full-span pipes (Case 3) remain blanked — no `◠`, no `◡`, no `│`
      in the middle of the window for a passing-through pipe.
- [x] ANSI color of the stub pipe is preserved on the terminator
      (the surrounding SGR sequence is unchanged; only `│` → glyph).
- [x] Corners (`┐`/`┘`), junctions (`┼`), horizontal connectors
      (`─`), and self-loop markers (`◉`) at the boundary are not
      touched.
- [x] Existing tests pass unchanged:
      `TestWindowedDiagramPassThroughPipes`,
      `TestWindowedDiagram`, `TestWindowedLadderIntegration`,
      `TestWindowTopologyValue`.
- [x] Full test suite green: `python -m pytest scripts/tests/ -n 0`
      exits 0.

## Implementation Steps

1. **Add terminator passes to `_render_layered_diagram`** at
   `scripts/little_loops/cli/loop/layout.py:1917-1934`. Insert two
   scan-and-replace blocks immediately after the existing
   full-span-blanking block at lines 1899-1915, before the grid
   slice at line 1917. No new imports needed (`strip_ansi` already
   in scope; `total_width` already computed earlier in the function).

2. **Tests in `scripts/tests/test_ll_loop_display.py`** — new class
   `TestWindowedDiagramStubTerminators` (after
   `TestWindowedDiagramPassThroughPipes` at line 4628):
   - `test_top_stub_back_edge_gets_dome_terminator` — back-edge from
     s15 (in-window when active=s14) UP to s2 (cropped above).
     Asserts `◠` appears in the row immediately after the
     "layers above" banner.
   - `test_bottom_stub_back_edge_gets_inverted_dome_terminator` —
     back-edge from s15 (cropped below when active=s2) UP to s2
     (in-window). Asserts `◡` appears in the row immediately before
     the "layers below" banner. Also asserts `│` still appears
     (the partial-stub-survives invariant from
     `TestWindowedDiagramPassThroughPipes` still holds — only the
     bottommost cell is replaced).
   - `test_full_span_pipe_still_blanked_no_terminator` — back-edge
     with both endpoints cropped (active=s8). Asserts neither `◠`
     nor `◡` appears in the diagram rows.

## Visual confirmation

Synthetic 12-state chain with two back-edges (s10 → s2, s8 → s3),
active=s8, budget=24:

```
  ▲ 7 layers above  (s0 → s1 → s2 → s3 → s4 → s5 → s6)
                                 ◠      ┌── ❯_ ┐
                                 │      │ s7   │
                                 │      │ step │
                                 │      └──────┘
                                 │          │ yes
                                 │          │
                                 │          ▼
                                 │      ┌── ❯_ ┐
                                 └──────│ s8   │
                                        │ step │
                                        └──────┘
                                            │ yes
                                            │
                                            ▼
                                        ┌── ❯_ ┐
                                        │ s9   │
                                        │ step │
                                        └──────┘
  ▼ 2 layers below  (… → s10 → s11 ◉)
```

The `◠` at the top of the left-margin pipe (s10 → s2 with destination
cropped above) terminates the stub that enters from above.

Active=s3, budget=14 (bottom-stub variant):

```
  ▲ 3 layers above  (s0 → s1 → s2)
                                        ┌── ❯_ ┐
                                 ┌─────▶│ s3   │
                                 │      │ step │
                                 │      └──────┘
                                 │          │ yes
                                 │          │
                                 │          ▼
                                 │      ┌── ❯_ ┐
                                 │      │ s4   │
                                 │      │ step │
                                 ◡      └──────┘
  ▼ 7 layers below  (… → s5 → s6 → s7 → s8 → s9 → s10 → s11 ◉)
```

The `◡` at the bottom-left terminates the s8 → s3 back-edge whose
source (s8) is cropped below. The full-span s10 → s2 pipe is
correctly blanked in the middle of the window.

## Impact

- **Priority**: P3.
- **Effort**: Small. ~20 lines of new code in one function plus three
  tests.
- **Risk**: Low. The new passes only modify cells where
  `strip_ansi(...) == "│"` at the boundary rows. The SGR color is
  preserved via `cell.replace("│", glyph)`. Corners, junctions, and
  horizontal connectors are guarded out. Full-span blanking
  (Case 3) is unchanged.
- **Breaking Change**: No. The output format gains two new glyphs at
  the cut rows; everything else is identical. The behavior change is
  strictly additive and only visible when a windowed diagram actually
  crops layers above or below.

## Verification

1. New tests:
   `python -m pytest scripts/tests/test_ll_loop_display.py::TestWindowedDiagramStubTerminators -n 0 -v`
2. Windowed-diagram test classes:
   `python -m pytest scripts/tests/test_ll_loop_display.py::TestWindowedDiagram scripts/tests/test_ll_loop_display.py::TestWindowedDiagramPassThroughPipes scripts/tests/test_ll_loop_display.py::TestWindowedDiagramStubTerminators scripts/tests/test_ll_loop_display.py::TestWindowedLadderIntegration scripts/tests/test_ll_loop_display.py::TestWindowTopologyValue -n 0`
3. Full test suite: `python -m pytest scripts/tests/ -n 0 --timeout=120`
   — the project's CI gate (no hosted CI exists per `.claude/CLAUDE.md`).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/cli/loop/layout.py:1841-1961` | The windowing pass this issue modifies |
| `scripts/little_loops/cli/loop/layout.py:1899-1915` | The existing full-span-blanking block this issue extends |
| `scripts/little_loops/cli/loop/layout.py:2128-2162` | `_overflow_banner` (the "▲ N layers above" / "▼ N layers below" builder) |
| `.issues/enhancements/P3-ENH-2410-windowed-scroll-to-active-fsm-diagram-fallback.md` | The base windowed-diagram feature this issue builds on |
| `.issues/enhancements/P4-ENH-2432-blank-pass-through-margin-pipes-in-windowed-diagram-fallback.md` | The Case-3 blanking behavior that this issue leaves untouched |

## Sources

- `~/.claude/plans/currently-in-our-ll-loop-cheerful-fog.md` — the
  approved plan for this change
- `scripts/little_loops/cli/loop/layout.py:986-1961` — the
  `_render_layered_diagram` function being modified
- `scripts/tests/test_ll_loop_display.py:4628-4662` — the existing
  `TestWindowedDiagramPassThroughPipes` class the new tests sit
  alongside

## Status

**Done** | Completed: 2026-07-10 | Priority: P3

Implemented and verified in this session. Full test suite:
14533 passed, 28 skipped, exit 0.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-10T23:45:10 - `64b5d1d5-70bc-4a50-95c9-3be4cee4d186.jsonl`
