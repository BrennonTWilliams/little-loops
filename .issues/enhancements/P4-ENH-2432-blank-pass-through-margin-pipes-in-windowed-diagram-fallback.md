---
id: ENH-2432
title: Blank pass-through back-edge/forward-skip margin pipes in the windowed diagram
  fallback
type: ENH
priority: P4
status: done
captured_at: '2026-07-01T19:52:15Z'
completed_at: 2026-07-01 19:52:15+00:00
discovered_date: 2026-07-01
discovered_by: user
labels:
- loop
- diagram
- rendering
- cli
- layout
relates_to:
- ENH-2410
- ENH-2411
- BUG-2425
decision_needed: false
confidence_score: 100
outcome_confidence: 95
score_complexity: 20
score_test_coverage: 20
score_ambiguity: 15
score_change_surface: 20
---

# ENH-2432: Blank pass-through back-edge/forward-skip margin pipes in the windowed diagram fallback

## Summary

`ll-loop run ... --show-diagrams clean` degrades to the ENH-2410 windowed-crop
fallback on tall/back-edge-heavy FSMs. The crop slices whole grid rows around
the active state, but back-edge (left-margin) and forward-skip-layer
(right-margin) pipes are drawn across the *full* unwindowed grid before the
crop happens. When a pipe's source and destination are both outside the
visible window, the sliced rows show a bare vertical line with no connector,
arrowhead, or label anchor — pure clutter, since the existing `▲`/`▼`
overflow banners already summarize what's cropped above/below.

## Current Behavior

For a back-edge-heavy loop (e.g. `cua-agent-desktop.yaml`, 48 states),
windowing to a narrow active-state pane produced output like:

```
  ▲ 23 layers above  (init → validate_input → check_install → input_missing ◉…)
 │ │ │ │ │ │ │ │ │ │ │ │ │    ┌────────────────────────────────── ❯_ ┐                 │             │   │
 │ │ │ │ │ │ │ │ │ │ │ │ │    │ _retry_action                        │◀────────────────┼─────────────┘   │
 │ │ │ │ │ │ │ │ │ │ │ │ │    │ ABS_DIR="${captured.run_dir.output}" │                 │                 │
 │ │ │ │ │ │ │ │ │ │ │ │ │    └──────────────────────────────────────┘                 │                 │
 ...
  ▼ 20 layers below  (… → _handle_replan → check_enf_limit → _route_act_error3…)
```

13 left-margin `│` columns rake down the entire visible pane with no visible
source, destination, or label — none of them terminate inside the window.

## Expected Behavior

Only margin pipes with at least one endpoint inside the visible window should
render. Pipes whose source *and* destination are both cropped away should be
blanked, since the overflow banners already communicate what's off-screen.
Partial stubs (one endpoint visible) must still render — they show real
connectivity to a state that's actually on screen.

## Root Cause

`_render_layered_diagram` (`scripts/little_loops/cli/loop/layout.py`) draws
back-edge and forward-skip-layer margin pipes (~`:1442-1683`) directly into
the character grid using row/column coordinates from the *full*, unwindowed
layout. The later windowed-crop block (`:1684-1746`, ENH-2410) only slices
grid rows — it has no record of which pipe spans exist or where their
corners are, so it can't distinguish a meaningful truncated stub from a
pure pass-through line.

## Proposed Solution

Track each margin pipe's span as it's drawn, then use that to selectively
blank pass-through segments during the windowed crop:

1. Collect `margin_pipe_spans: list[tuple[col, top_row, bot_row,
   label_row_pos, label_start, label_len]]` in both the back-edge and
   forward-skip-layer drawing loops.
2. In the windowed-crop block, for each span where `top_row < window_top and
   bot_row >= window_bot` (neither corner visible), blank the pipe's `│`
   cells within the window and its label if the label row also falls inside
   the window.
3. Only blank cells that are still an untouched `│` (checked via
   `strip_ansi`) — a `┼` junction means a *different* edge's horizontal
   connector crosses here, so leave it alone to avoid corrupting a
   still-visible edge.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — span tracking in the back-edge
  loop (`:1442-1568`) and forward-skip-layer loop (`:1569-1694`); blanking
  logic in the windowed-crop block (`:1695-1780`).

### Tests
- `scripts/tests/test_ll_loop_display.py` — new
  `TestWindowedDiagramPassThroughPipes` class.

## Acceptance Criteria

- [x] A margin pipe whose source and destination are both cropped out of the
      window renders no `│`/junction/label in the visible pane.
- [x] A margin pipe with one endpoint inside the window still renders its
      stub, corner, and arrowhead.
- [x] Full suite green: `python -m pytest scripts/tests/` exits 0.

## Verification

1. **Regression tests** in `test_ll_loop_display.py`:
   `test_pass_through_back_edge_pipe_is_blanked` (asserts the left margin —
   everything before the first state box — is pipe- and label-free when both
   back-edge endpoints are cropped away) and
   `test_partial_stub_pipe_survives` (asserts the pipe still renders when the
   active state is one of the edge's own endpoints). Both use a new
   `_long_back_edge_fsm` fixture (a 20-state chain plus one long back-edge).
2. **Real-loop check:** rendered `cua-agent-desktop.yaml` (48 states) windowed
   around `_retry_action` at `budget=14` before/after (via `git stash`) —
   before: 13 orphan `│` columns; after: only the two pipes with a visible
   endpoint remain, each terminating in a real arrowhead/junction.
3. Full gate: `python -m pytest scripts/tests/` exits 0 (this project's only
   CI gate).

## Scope Boundaries

- In scope: blanking pass-through margin pipes in the ENH-2410 windowed-crop
  path only (`window is not None` branch of `_render_layered_diagram`).
- Out of scope: back-edge gutter width clamping (BUG-2425), non-windowed
  presets (`detailed`, `summary`, `local`), and any change to layout/column
  allocation for margin pipes.

## Impact

- **Priority**: P4 — cosmetic clutter in a fallback rendering path, not a
  correctness or data-loss issue; only visible when `--show-diagrams clean`
  (or other window-topology presets) degrades a large/back-edge-heavy loop.
- **Effort**: Small — span tracking is a natural extension of the existing
  per-edge drawing loops; the blanking logic is a bounded post-pass with no
  change to layout/column allocation.
- **Risk**: Low — only touches the windowed-crop path (`window is not None`);
  non-windowed renders (`detailed`, `summary`, `local` presets) are
  unaffected. The junction-char guard (`strip_ansi(...) == "│"`) prevents
  blanking cells that belong to a different, still-visible edge.

## Resolution

Implemented as designed: `margin_pipe_spans` is populated at the end of both
the back-edge (`layout.py:1562`) and forward-skip-layer (`layout.py:1673`)
drawing loops. The windowed-crop block computes `window_top`/`window_bot`
before slicing and, for each span with both corners outside that range,
blanks its untouched `│` cells and (if the label row also falls inside the
window) its orphaned label text — leaving `┼` junctions belonging to other
edges untouched.

Verified against a synthetic long-back-edge fixture and against
`cua-agent-desktop.yaml` (real 48-state loop) with a before/after comparison
via `git stash`. Full suite: 13304 passed, 23 skipped; the one failure
(`test_all_skills_within_limit` on `skills/manage-issue/SKILL.md` = 523
lines) is a pre-existing repo condition unmodified by this change.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-01T19:52:53 - `0cfc5fbb-0c43-4736-b915-e1a671fe021e.jsonl`
- Ad-hoc conversation - 2026-07-01T19:52:15Z - user reported the pass-through
  margin-pipe clutter in the `clean`-preset windowed fallback and approved
  the fix; implemented directly (no `/ll:manage-issue` pass).

## Status

**Done** | Created: 2026-07-01 | Completed: 2026-07-01 | Priority: P4
