---
id: BUG-2425
title: FSM diagrams overflow terminal width in the non-TTY streaming render path (unbounded
  back-edge gutter + no width fallback)
type: BUG
priority: P2
status: done
captured_at: '2026-07-01T17:32:46Z'
completed_at: 2026-07-01 18:36:44+00:00
discovered_date: 2026-07-01
discovered_by: capture-issue
labels:
- bug
- loop
- diagram
- rendering
- cli
- layout
relates_to:
- ENH-2410
- ENH-2411
decision_needed: false
confidence_score: 100
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2425: FSM diagrams overflow terminal width in the non-TTY streaming render path

## Summary

When a back-edge-heavy FSM loop (e.g. `rn-implement`) runs in a **background /
non-TTY** context, the state diagrams printed to the run log are far wider than
the terminal, wrap, and render as a broken, misaligned stream of "multiple" loop
diagrams. Two compounding defects cause this:

1. The layered layout's **back-edge left gutter grows unbounded** (~2 columns per
   back-edge) with no clamp against terminal width.
2. The **non-TTY streaming render path has no width-fallback guard** — the ENH-2411
   `_build_fallback_ladder` degradation only runs in the pinned/TTY path, so
   background runs render the full diagram at whatever width the layout computes.

Observed while running `rn-implement` in a separate project (`MC-vault`,
little-loops v1.136.0 editable, `show_diagrams: "clean"`).

## Current Behavior

The captured log for run `rn-implement-20260701T121630`
(`.loops/.running/<id>.log`) contains diagram lines **108–111 characters wide**,
with a **~52-column left gutter** of back-edge channels before any state box:

```
                                    │ │ │ │ │ │ │ │   │   │ │ │ │          ┌───────── ❯_ ┐      ┌────── ❯_ ┐
                                    │ │ │ │ │ │ │ │   │   │ │ │ │          │ select_next │      │ fifo_pop │
                                    │ │ │ │ │ │ │ │   │   │ │ │ │          └─────────────┘      └──────────┘
```

At the 80-column non-TTY default this wraps, so each `state_enter` prints a
fresh, mangled full diagram — the log fills with many broken diagrams.

## Steps to Reproduce

1. Run a back-edge-heavy loop (many `on_failure`/remediation/decomposition cycles,
   e.g. `rn-implement`, ~49 states / ~20 back-edges) in **background** mode
   (`ll-loop run rn-implement --background`, or any path where stdout is a file
   rather than a TTY), with `show_diagrams` enabled (`"clean"` or `"verbose"`).
2. Tail the run log at `.loops/.running/<instance-id>.log`.
3. **Observe:** diagram lines exceed the terminal width (108–111 cols vs an
   80-col default), the left back-edge gutter alone consumes ~50+ cols, and lines
   wrap into a broken/misaligned stream.

## Expected Behavior

Every rendered diagram line should fit within the effective terminal width (the
80-col non-TTY default, or the real width when a `COLUMNS`/TTY is available). When
a diagram is too wide, the streaming path should degrade it (title-only / windowed
/ neighborhood / single) exactly like the pinned/TTY path already does, and the
back-edge gutter must never consume the whole line.

## Root Cause

Two compounding defects, confirmed by reading the code and the captured log.

### Defect 1 — unbounded back-edge gutter (`layout.py`)
`_render_layered_diagram` (`scripts/little_loops/cli/loop/layout.py:988-994`):

```python
back_edge_margin = 0
if non_self_back_initial:
    max_label_len = max(len(lbl) for _, _, lbl in non_self_back_initial)
    n_back_initial = len(non_self_back_initial)
    back_edge_margin = max_label_len + max(6, 2 * n_back_initial + 2)
content_left = 2 + back_edge_margin
```

`back_edge_margin` grows ~2 columns per back-edge with **no clamp against
`terminal_width()`**. With ~20 back-edges the left gutter alone is ~52 cols,
pushing state boxes out to 108–111 cols. The later recompute at
`layout.py:1150-1153` (`actual_margin`) has the same lack of clamp. Nothing bounds
`content_left`/box placement to the terminal width.

### Defect 2 — streaming (non-TTY) path skips the width fallback (`_helpers.py`)
There are two render paths in `StateFeedRenderer.handle_event`:

- **Pinned/TTY:** `in_pinned_mode = show_diagrams and clear_screen and sys.stdout.isatty()`
  (`_helpers.py:654`) → `_render_pinned_pane` → **ENH-2411 `_build_fallback_ladder`**
  with a `too_wide` probe that sheds detail when the diagram won't fit.
- **Streaming:** the `elif self.show_diagrams:` branch (`_helpers.py:749-791`) calls
  `_render_fsm_diagram` **directly — no width budget, no fallback ladder.**

A background run's stdout is a log file, **not a TTY** (`_helpers.py:1266-1273`
spawns the child with `stdout=log_fh`; alt-screen/pinned mode is gated on
`sys.stdout.isatty()` at `_helpers.py:1419`), so `in_pinned_mode` is False and the
streaming branch runs. The ENH-2411 horizontal fallback therefore never fires for
background/log runs.

### Secondary (latent correctness) — `_variant_width` mismeasures wide glyphs
`_variant_width()` (`_helpers.py:278-282`) measures with `len(strip_ansi(ln))`
(character count) instead of the `wcwidth`-based `_display_width()` used throughout
`layout.py`. The ENH-2411 `too_wide = _variant_width(...) > cols` probe therefore
under-counts any wide glyph (emoji badges, CJK, some arrows). Not the cause of this
overflow (the offending content is width-1 box-drawing + `❯`), but it makes even the
pinned-path probe unreliable and should be fixed alongside.

## Proposed Solution

Fix all three in one change (chosen as a single "Both" fix — the first two compound
to produce the single symptom):

### Part 1 — clamp the back-edge gutter to terminal width (`layout.py`)
In `_render_layered_diagram` (`layout.py:988-994`, and the recompute at
`:1150-1153`), bound `back_edge_margin`/`content_left` so the gutter can never
consume the whole line. Cap the back-edge channel allocation to a fraction of
`terminal_width()` (e.g. `back_edge_margin = min(back_edge_margin, max(0, tw // 3))`;
`tw` is already fetched at ~`:880`/`:1857`) and collapse/merge overflow back-edge
channels into a shared track when the cap is hit, rather than adding one `│ ` column
per edge. Preserve the existing alignment math (`common_center`, `col_start`) — they
key off `content_left`, so clamping it flows through.

### Part 2 — apply the width-fallback ladder in the streaming path (`_helpers.py`)
Route the `elif self.show_diagrams:` branch (`_helpers.py:749-791`) through the same
ENH-2411 degradation the pinned path uses: reuse `_build_fallback_ladder` +
`_classify_fsm_topology` and pick the first rung whose
`_variant_width(...) <= terminal_width()`, falling back
`full → title_only → window → neighborhood → single`. Background/log runs then get a
readable degraded diagram instead of an overflowing one.

### Part 3 — correct `_variant_width` to display width (`_helpers.py:278-282`)
Replace `len(strip_ansi(ln))` with the `wcwidth`-based `_display_width()` from
`layout.py` so the Part-2 probe (and the existing pinned-path probe) size wide glyphs
correctly.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — `_render_layered_diagram` gutter clamp
  (`:988-994`, `:1150-1153`).
- `scripts/little_loops/cli/loop/_helpers.py` — streaming-path fallback wiring
  (`:749-791`) and `_variant_width` display-width fix (`:278-282`).

### Similar Patterns / Reuse
- `_build_fallback_ladder`, `_classify_fsm_topology`, `_variant_width` (`_helpers.py`)
  — the ENH-2411 degradation machinery to reuse in the streaming path.
- `_display_width()` (`layout.py`) — the canonical `wcwidth`-based width measurement.

### Tests
- `scripts/tests/test_loop_layout_alignment.py` — add a regression test (below).

## Acceptance Criteria

- [ ] Rendering a back-edge-heavy FSM at a forced 80-col width produces **no line**
      whose display width (`wcwidth`) exceeds 80 (fails today, passes after Part 1+2).
- [ ] The back-edge left gutter is bounded to a fraction of terminal width; overflow
      back-edges share a collapsed track instead of one `│ ` column each (Part 1).
- [ ] The non-TTY streaming `show_diagrams` path degrades wide diagrams via the
      ENH-2411 fallback ladder (title-only / window / neighborhood / single), not a raw
      full render (Part 2).
- [ ] `_variant_width()` measures display columns via `wcwidth`, not `len()` (Part 3).
- [ ] A regression test in `test_loop_layout_alignment.py` locks in the width bound.
- [ ] Full suite green: `python -m pytest scripts/tests/` exits 0.

## Verification

1. **Regression test** in `scripts/tests/test_loop_layout_alignment.py`: render a
   synthetic FSM with many back-edges (or load `rn-implement`) with
   `terminal_width`/`shutil.get_terminal_size` monkeypatched to 80, and assert every
   output line's `wcwidth` display width is `<= 80`. Run:
   `python -m pytest scripts/tests/test_loop_layout_alignment.py`.
2. **End-to-end:** re-run `rn-implement` in a background/non-TTY context and confirm
   `.loops/.running/<id>.log` diagrams no longer exceed terminal width or show the
   runaway `│ │ │ …` gutter; compare against the captured
   `rn-implement-20260701T121630` log.
3. Full gate: `python -m pytest scripts/tests/` exits 0 (this project's only CI gate).

## Impact

- **Priority**: P2 — corrupts the primary progress display for any wide/back-edge-heavy
  loop in every background/log run; `rn-implement` (a core recursive loop) is affected.
- **Effort**: Small–medium — one clamp in `layout.py`, reuse of existing ENH-2411
  machinery in the streaming branch of `_helpers.py`, one `_variant_width` fix, plus a
  regression test.
- **Risk**: Low–medium — changes diagram layout/width behavior; the regression test
  locks in the `<= width` invariant.
- **Regression note**: not a direct ENH-2410/ENH-2411 regression — Defect 1 (unbounded
  gutter) predates them; ENH-2411's fallback was simply never wired into the streaming
  path (Defect 2).

## Resolution

Fixed all three parts in one change:

- **Part 1 — gutter clamp** (`layout.py`): clamped `back_edge_margin` to
  `min(margin, max(6, tw // 3))` at both computation sites (initial estimate and
  post-crossing recompute). `content_left` flows uniformly into
  `common_center`/`col_start` (`x = max(content_left, x)`), and the back-edge
  channel draw loop already drops overflow channels via `if col >= content_left - 1:
  continue` and bounds labels to `content_left - 1` — so the clamp collapses
  overflow channels into the bounded gutter with no new merge code.
- **Part 2 — streaming fallback ladder** (`_helpers.py`): new
  `_render_streaming_diagram()` renders `full`, and if it overflows `cols`, walks
  the ENH-2411 `_build_fallback_ladder` (title-only → neighborhood → single,
  skipping `window` which needs a row budget) returning the first rung whose
  `_variant_width` fits. `_render_single_line_status` is the guaranteed floor. The
  `elif self.show_diagrams:` streaming branch now routes through it (was calling
  `_render_fsm_diagram` directly with no width budget).
- **Part 3 — `_variant_width`** (`_helpers.py`): measures display columns via
  `_display_width` (wcwidth) instead of `len()`, so wide glyphs size the probe
  correctly.

**Tests** (`test_loop_layout_alignment.py`): `test_back_edge_gutter_clamped_to_width`
(Part 1), `test_streaming_diagram_fits_width` + `test_streaming_diagram_degrades_when_too_wide`
(Part 2), `test_variant_width_counts_display_columns` (Part 3). Updated 5
mock-forwarding assertions in `test_ll_loop_display.py` for the new explicit
`verbose=` kwarg. Full suite: 13304 passed (the one failure,
`test_all_skills_within_limit` on `skills/manage-issue/SKILL.md` = 523 lines, is a
pre-existing repo condition unmodified by this change).

## Session Log
- `/ll:manage-issue` - 2026-07-01T18:36:44Z - `9f1c67b2-4389-4a41-9eca-2017def791ef.jsonl` - implemented Parts 1-3 + regression tests
- `/ll:ready-issue` - 2026-07-01T17:50:51 - `851b115b-1ef5-42c4-9280-6c673030fd28.jsonl`
- `/ll:format-issue` - 2026-07-01T17:43:29 - `f8600cad-5561-4445-afec-1f6ac182a6e0.jsonl`
- `/ll:capture-issue` - 2026-07-01T17:32:46Z - investigation of rn-implement diagram overflow in MC-vault

## Status

**Done** | Created: 2026-07-01 | Completed: 2026-07-01 | Priority: P2
