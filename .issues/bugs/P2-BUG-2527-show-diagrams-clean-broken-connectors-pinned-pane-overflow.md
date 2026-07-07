---
id: BUG-2527
title: '--show-diagrams clean emits broken connectors (trailing ───── ┘) when the
  pinned pane overflows terminal width'
type: BUG
priority: P2
status: done
discovered_date: 2026-07-07
discovered_by: capture-issue
testable: false
decision_needed: false
confidence_score: 100
outcome_confidence: 95
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
completed_at: 2026-07-07 19:55:00+00:00
---

# BUG-2527: `--show-diagrams clean` emits broken connectors when the pinned pane overflows terminal width

## Summary

When running a back-edge-heavy FSM loop (e.g. `rn-implement`) with
`ll-loop run <loop> --show-diagrams clean` (the default in this project's
`.ll/ll-config.json`), the pinned pane output renders boxes but **connectors
trail off past the visible right edge**, producing a broken-looking diagram
like:

```
                       │   │   └───────────────────│ run_refine │◀─────│ enqueue_children │──────│ size_review_snap │─────────────────────────────── ───────┘
                       │   │                       └────────────┘      └──────────────────┘      └──────────────────┘
                       │   │
```

The user expects a **clean partial diagram** (auto-degraded to the window /
neighborhood / single rung) when the full layered render exceeds terminal width.
Instead they get a clipped/wrapped broken one. The streaming path already
correctly degrades wide diagrams (since BUG-2425); this bug is the **pinned/TTY
path** sibling — the same symptom in `StateFeedRenderer.in_pinned_mode`, which
is the default in this project (`loops.run_defaults.clear: true` + TTY).

## Current Behavior

Pinned/TTY `--show-diagrams clean` on a back-edge-heavy FSM:

1. Resolves `clean` to `DiagramFacets("layered", edge_labels=False,
   state_detail="title", scope="main", source="preset")` at
   `scripts/little_loops/cli/loop/diagram_modes.py:61`.
2. Builds a fallback ladder (BUG-2425 / ENH-2411) ordered `[full, window,
   neighborhood, single]` — the `title_only` / `title_only_nolabels` rungs are
   skipped because `clean` already sets `state_detail="title"` and
   `edge_labels=False` (`_helpers.py:347-353`).
3. `_choose_pinned_layout` (`_helpers.py:259-280`) iterates the ladder and
   picks the first rung whose **height** (line count) fits terminal rows. It
   did not check width — so the `full` layered render was picked whenever its
   line count fit, even if its widest line was wider than `cols`.
4. `_render_layered_diagram` (`layout.py:1181`) computes
   `total_width = max(total_content_w + right_edge_margin + 4, tw)` — this
   allows the grid to **exceed** `tw` when forward-skip-layer edges push the
   content right. (BUG-2425 Part 1 only clamped the back-edge left gutter, not
   the forward skip-layer right gutter.) The final centering at `layout.py:1794`
   uses `max(0, (tw - max_line_len) // 2)` so when `max_line_len > tw` the
   lines are emitted raw and the terminal wraps them.
5. The dry-run path (`run.py:226-248`) and the `info` path
   (`info.py:1214-1228`) call `_render_fsm_diagram` directly with **no width
   guard** at all — same broken-output symptom.

The dry-run path's broken output is what was captured in the autodev run log
that surfaced this bug.

## Expected Behavior

For every `--show-diagrams` mode (`clean` or otherwise), on every render path
(dry-run, streaming, pinned):

- The picked variant's widest line fits within terminal width.
- A too-wide `full` rung falls through to a smaller one (window → neighborhood
  → single) instead of being picked anyway.
- Defense in depth: even if the ladder picker or stream walker both fail to
  filter, no output line ever exceeds terminal columns.

## Steps to Reproduce

1. From repo root, run `python -m ll-loop run rn-implement --show-diagrams
   clean --clear` in a 100–120 column TTY (or invoke
   `StateFeedRenderer._redraw_pinned` directly via `test_run_foreground`).
2. Observe: diagram lines exceed the terminal width; connectors (─, └, ┘) trail
   far past the last visible box; the terminal wraps them.

Same FSM via `ll-loop run rn-implement --show-diagrams clean` (no `--clear`,
non-TTY / log file) does NOT reproduce the broken layout — the streaming path
already works (BUG-2425).

## Root Cause

Two compounding defects:

### Defect 1 — `_choose_pinned_layout` is height-only (`_helpers.py:259-280`)

```python
def _choose_pinned_layout(rows, variants, min_action_rows=MIN_ACTION_ROWS):
    for variant in variants:
        last_h = _count_display_lines(variant)
        if last_h + min_action_rows <= rows:
            return variant, last_h
    return last_text, last_h
```

The pinned/TTY path (gated by `in_pinned_mode = show_diagrams and clear_screen
and sys.stdout.isatty()` in `StateFeedRenderer.__init__`) routes through this
function. It filters by **height only**. A rung can pass the height check while
its widest line is wider than `cols`. The streaming path's
`_render_streaming_diagram` (`_helpers.py:657-755`, fixed in BUG-2425) correctly
measures `_variant_width` post-render and walks down — but the pinned path
never re-checks width after picking.

### Defect 2 — `_render_layered_diagram` builds a grid wider than `tw`
(`layout.py:1181`)

```python
total_width = max(total_content_w + right_edge_margin + 4, tw)
```

`total_width` is allowed to **exceed** `tw` when forward-skip-layer edges push
content right. The grid is then built at `total_width` columns
(`layout.py:1203`) and connectors are bounded only by `total_width`, never by
`tw`. The forward skip-layer right gutter at `layout.py:1582`
(`rightmost_fwd_pipe_col = total_content_w + 2 + (len(sorted_fwd_skip) - 1) * 2`)
has no clamp — BUG-2425 Part 1 only added the symmetric clamp on the back-edge
left side.

The dry-run path (`run.py:226-248`) and `info` path (`info.py:1214-1228`) call
`_render_fsm_diagram` directly with no width guard or fallback ladder — so even
the BUG-2425 streaming fallback does not save them.

## Proposed Solution

Two surgical layers of defense (one picker change, one render clamp):

### Part 1 — make `_choose_pinned_layout` width-aware (`_helpers.py:259-296`)

Add an optional `cols` keyword and a `_variant_width` pre-filter. Pinned-path
now degrades wide diagrams the same way the streaming path already does
(BUG-2425). Update the call site at `_helpers.py:638` to pass `cols=cols`.

```python
def _choose_pinned_layout(rows, variants, min_action_rows=MIN_ACTION_ROWS, *, cols=None):
    for variant in variants:
        last_h = _count_display_lines(variant)
        if cols is not None and _variant_width(variant) > cols:
            continue  # too wide; ladder has smaller rungs to try
        if last_h + min_action_rows <= rows:
            return variant, last_h
    return last_text, last_h
```

### Part 2 — hard-clamp output to `tw` in `_render_layered_diagram`
(`layout.py:1785-1803`)

Defense in depth: clamp every output line to `tw` display columns with a
trailing `…` marker, using the existing `_display_width`/`_truncate_to_width`/
`strip_ansi` helpers (already used by the box content writer, so the visual
style is consistent). This guards all three render paths (dry-run, streaming,
pinned) at the renderer level.

```python
if tw > 1:
    clamped: list[str] = []
    for ln in lines:
        if _display_width(strip_ansi(ln)) > tw:
            ln = _truncate_to_width(strip_ansi(ln), tw - 1) + "…"
        clamped.append(ln)
    lines = clamped
```

The clamp is only supposed to fire on overflow — diagrams that already fit
within `tw` are emitted unchanged. Verified by
`test_render_layered_diagram_output_clamped_to_tw` (no `…` marker on a
`tw=200` render of the same FSM).

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `_choose_pinned_layout` (lines 259-296); call site at line 638
  passes `cols`.
- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Anchor**: `_render_layered_diagram` final assembly (lines 1785-1803).

## Integration Map

### Files Modified

- `scripts/little_loops/cli/loop/_helpers.py` — `_choose_pinned_layout`
  signature extended with `cols=None`; width filter added before height check;
  call site at line 638 passes `cols=cols`.
- `scripts/little_loops/cli/loop/layout.py` — final assembly in
  `_render_layered_diagram` clamps every line to `tw` display columns with a
  trailing `…` marker (defense in depth).

### Tests Added (`scripts/tests/test_loop_layout_alignment.py`)

- `test_pinned_layout_skips_too_wide_variants` — Fix A direct: synthesize a
  200-col-wide variant and a 50-col-wide variant, pass both to
  `_choose_pinned_layout` with `cols=100`, assert the 50-col-wide one wins.
  Also asserts the legacy `cols=None` height-only behavior is preserved
  (backwards compatibility for any external caller).
- `test_pinned_pane_clean_preset_no_overflow` — Fix A + Fix B end-to-end on a
  12-state back-edge-heavy FSM at `tw=100`: every output line fits within
  `tw`, and `_assert_boxes_rectangular` confirms the clamp didn't mangle box
  borders.
- `test_render_layered_diagram_output_clamped_to_tw` — Fix B direct: 12-state
  back-edge-heavy FSM at `tw=60` overflows naturally; every line fits ≤ 60.
  Plus a "no false-positive" check: same FSM at `tw=200` does NOT have a `…`
  marker (the clamp only fires on overflow).

### Reuse, Not Reinvent

- `_display_width`, `_truncate_to_width`, `strip_ansi` — already in
  `layout.py` and used by the box content writer.
- `_variant_width` — already in `_helpers.py:306-318` (uses `_display_width`).
- Existing test helpers `_clean_facets()`, `_make_back_edge_heavy_fsm(n)`,
  `_max_line_display_width()` already in
  `scripts/tests/test_loop_layout_alignment.py:169-191`.

## Acceptance Criteria

- [x] `_choose_pinned_layout` filters variants by `_variant_width <= cols`
      before considering height (when `cols` is provided).
- [x] `_render_pinned_pane` passes `cols` to `_choose_pinned_layout`.
- [x] `_render_layered_diagram` final assembly clamps every output line to
      `tw` display columns with a `…` marker when overflow would otherwise
      occur.
- [x] Three regression tests added to `test_loop_layout_alignment.py`,
      reusing existing helpers.
- [x] All existing tests still pass (no regressions). Full suite:
      `14152 passed, 27 skipped` (same skips as before, no new skips).
- [x] Snapshot tests in `test_snapshot_loop_layout.py` unchanged (the clamp
      only fires on overflow; existing `tw=80` fixtures fit).

## Verification

1. **Regression tests** in `scripts/tests/test_loop_layout_alignment.py`:
   - `test_pinned_layout_skips_too_wide_variants` — direct Fix A test.
   - `test_pinned_pane_clean_preset_no_overflow` — Fix A + Fix B end-to-end.
   - `test_render_layered_diagram_output_clamped_to_tw` — Fix B direct.
   - Run: `python -m pytest scripts/tests/test_loop_layout_alignment.py -v`
     (16 tests, all pass).

2. **Full suite green**: `python -m pytest scripts/tests/` exits 0
   (14152 passed, 27 skipped, ~87s).

3. **End-to-end manual**: run `ll-loop run rn-implement --show-diagrams clean`
   in a 120-col TTY and confirm:
   - Every line fits ≤ 120 cols.
   - The active state is highlighted with its 1-hop neighborhood visible
     (the `neighborhood` rung, picked via the new width filter).
   - Tailing the run log (non-TTY path) shows the same clean degraded diagram.

## Impact

- **Priority**: P2 — corrupts the primary progress display for the default
  `clean` preset on any back-edge-heavy loop. The autodev run log was
  particularly affected because it captures every state transition's pinned
  pane as a non-TTY stream when the parent process is piped.
- **Effort**: Small — two surgical edits across two files; three regression
  tests reusing existing helpers; no new abstractions.
- **Risk**: Low — Fix A only changes which rung is selected (always picks a
  fitting one or smaller); Fix B only changes output when overflow happens
  (which is already a broken state). Both are backwards compatible (Fix A
  preserves the legacy `cols=None` height-only path for external callers).
- **Regression note**: not a BUG-2425 regression — the streaming path has
  been width-aware since BUG-2425 Parts 1-3. BUG-2425 Part 1's back-edge
  gutter clamp is what limited the original symptom to the pinned-path
  picker gap. The fix here mirrors that streaming pattern in the pinned
  picker and adds a final-output clamp at the renderer level so all three
  paths (dry-run, streaming, pinned) are protected.

## Related Key Documentation

- `docs/ARCHITECTURE.md` — FSM diagram renderer section
- `docs/reference/API.md` — `_render_fsm_diagram` / `_choose_pinned_layout`
- `docs/development/TROUBLESHOOTING.md` — diagram overflow troubleshooting

## Related Issues

- `BUG-2425` — FSM diagrams overflow terminal width in the non-TTY streaming
  render path (done 2026-07-01). Fixed the streaming path; left the pinned
  path's picker and the dry-run/info paths unfixed — which is what this bug
  addresses.
- `ENH-2410` — windowed-scroll to active FSM diagram fallback (ladder rung).
- `ENH-2411` — topology-aware diagram fallback selection (the ladder shape).
- `ENH-2442` — extended windowed rung to streaming path.

## Status

done

## Resolution

Applied Fix A (width-aware `_choose_pinned_layout`) and Fix B (output clamp in
`_render_layered_diagram`). Added three regression tests in
`scripts/tests/test_loop_layout_alignment.py` reusing the existing
`_clean_facets()`, `_make_back_edge_heavy_fsm(n)`, and `_max_line_display_width()`
helpers. Full suite: 14152 passed, 27 skipped (the 27 skips pre-date this
change). No snapshot regeneration needed (clamp only fires on overflow; existing
`tw=80` fixtures fit).

Behavior change visible to users: `ll-loop run <loop> --show-diagrams clean` on
a back-edge-heavy FSM now shows a clean `neighborhood` view (active state +
1-hop predecessors/successors) instead of a broken full render, on both the
pinned/TTY and streaming paths. The dry-run path (`ll-loop run <loop>
--dry-run --show-diagrams clean`) now produces a clamped output with `…`
markers on overflow lines instead of wrapped broken connectors.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-07T19:10:42 - `b535cf57-5cc7-43ff-ad64-164b9939b6e0.jsonl`

- `/ll:capture-issue` - 2026-07-07T19:30:00Z - investigation of
  `rn-implement` diagram overflow in autodev run log
- `/ll:refine-issue` - 2026-07-07T19:35:00Z - codebase research for Fix A/B
  integration points
- `/ll:manage-issue` - 2026-07-07T19:55:00Z - implemented Fix A + Fix B +
  regression tests