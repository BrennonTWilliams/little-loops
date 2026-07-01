---
id: ENH-2410
title: Windowed / scroll-to-active FSM diagram fallback for the pinned-pane ladder
type: ENH
priority: P3
status: open
captured_at: '2026-06-30T00:27:20Z'
discovered_date: '2026-06-30'
discovered_by: capture-issue
relates_to:
- ENH-2062
- ENH-2411
- ENH-1652
- ENH-1702
- ENH-1672
- FEAT-670
labels:
- enhancement
- cli
- loop
- ux
- diagram
confidence_score: 90
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2410: Windowed / scroll-to-active FSM diagram fallback

## Summary

When the full layered (Sugiyama) diagram is too tall for the terminal, the
pinned-pane ladder degrades to `_render_neighborhood_diagram`, a synthetic
1-hop `preds → [active] → succs` view that (a) discards all global topology
and (b) renders predecessors as an **unbounded single vertical column** — so
on hub states it is often *taller* and uglier than the full diagram it was
meant to replace. Add a new fallback renderer that keeps the **real** layered
diagram but crops it to a vertical window of ±K layers around the active
state, with overflow indicators (`▲ N layers above …` / `▼ M layers below …`).
This preserves true layout, real edges/arrows, and the active state's actual
context, while bounding height to the viewport.

## Current Behavior

The preset/default layered ladder in `_render_pinned_pane`
(`scripts/little_loops/cli/loop/_helpers.py`, ~lines 429-437) is:

```python
elif topo_detail == "full":
    variants = [_build("full"), _build("neighborhood"), _build("single")]
```

`_choose_pinned_layout` (`_helpers.py:231-252`) picks the first variant whose
height + `effective_min_action_rows` fits in `rows`. For large loops the full
diagram never fits, so the neighborhood view is selected. Measured on
`general-task` (20 states) with `diagnose` active (11 predecessors):

- full layered diagram: **89 rows**
- neighborhood diagram: **33 rows** — a lopsided single-column tower of 11
  predecessor boxes with the active box floating mid-stack.

The neighborhood view is fine for low-degree mid-graph states but degrades
badly on the fan-in/fan-out **hub** states that most loops contain
(`dequeue_next`, `diagnose`, `route_*`), which routinely have 10-14
predecessors.

## Expected Behavior

A new `"window"` detail variant for `_build_pinned_pane` / a
`_render_windowed_diagram` helper that:

- Runs the normal layered pipeline (`LayerAssigner` → `CrossingMinimizer` →
  `_render_layered_diagram`) so layout, arrows, labels, badges and
  active-state highlight are the genuine ones — not a re-synthesized subgraph.
- Determines the active state's layer, then crops rendered rows to the layers
  within ±K of it (K chosen to fill the available `rows` budget), rather than
  rendering all layers.
- Emits compact overflow affordances above/below the window, e.g.
  `▲ 3 layers above (init → plan → select_step)` and
  `▼ 6 layers below (… → failed ◉)`, so the user retains a sense of position
  in the whole graph.
- Keeps back-edge margin arrows that cross the window visible (at minimum as a
  truncated stub with the label) so cycles through the active state aren't
  silently dropped.
- Falls back gracefully when the active state is unknown/`None` (window the
  top of the graph) or when even a 1-layer window doesn't fit (defer to
  `single`).

## Motivation

- The middle rung of the ladder is the one users actually see on real loops,
  and it is the weakest. Cropping the real diagram is strictly more
  informative than a synthetic neighborhood: same visual language as the full
  view, real edges, real layout, plus "where am I in the graph".
- Height is bounded by construction (window is sized to the viewport), so it
  never blows up on high-degree hub states the way the current neighborhood
  column does.
- Reuses the entire existing render pipeline; the new logic is layer selection
  + row cropping + overflow banners, not a second layout engine.

## Use Case

```bash
ll-loop run big-loop.yaml --show-diagrams clean --clear
# terminal too short for the full diagram:
#   ▲ 3 layers above  (init → plan → select_step)
#         ┌──────────────┐
#         │ verify_step  │──no──┐
#         └──────────────┘      ▼
#                         ┏━━━━━━━━━━━━┓
#                         ┃  diagnose  ┃ ◀ active
#                         ┗━━━━━━━━━━━━┛
#   ▼ 6 layers below  (… → failed ◉)
```

## Design Notes / Open Questions

1. **Row-crop vs. re-layout.** Cheapest implementation renders the full grid
   once and slices rows by the active state's `row_start` ± budget. This keeps
   column positions/arrows intact but may cut a box mid-height at the window
   edge — need a clean cut at box boundaries and a partial-box policy.
2. **Window sizing.** K should be derived from the `rows` budget passed through
   `_choose_pinned_layout`, not a constant. The variant builder currently
   returns a finished string; windowing needs the height budget at build time,
   so `_build_pinned_pane` / `_render_pinned_pane` must thread `rows` (or a
   target height) into the windowed builder.
3. **Ladder placement.** Insert as `[full, window, neighborhood, single]` or
   have it *replace* neighborhood in the default layered ladder? Recommend
   inserting above neighborhood so the richest fitting view still wins;
   ENH-2411 can later choose between window/neighborhood by topology.
4. **Explicit topology.** `--show-diagrams window` (a new topology value in
   `TOPOLOGY_VALUES` / `TOPOLOGY_TO_DETAIL`) so power users can force it, or
   keep it fallback-only? Recommend adding the explicit value for testability.
5. **Off-path active state.** The existing `main`-scope fallback to `full`
   (when the active state is off the happy path) must still apply before
   windowing.

## Scope Boundaries

- **In scope**: A new `"window"` layered variant that crops the real Sugiyama
  render to ±K layers around the active state; overflow banners
  (`▲ N layers above …` / `▼ M layers below …`); truncated stubs for back-edges
  that cross the window; threading a height budget from `_choose_pinned_layout`
  into the windowed builder; inserting the variant into the default layered
  ladder above `neighborhood`; and (recommended) an explicit `window` topology
  value in `TOPOLOGY_VALUES` / `TOPOLOGY_TO_DETAIL` for forced, testable use.
- **Out of scope**: Topology-aware selection between `window` / `neighborhood` /
  outline based on FSM shape — that is ENH-2411, which this feeds. Also out of
  scope: replacing or removing the existing `full` / `neighborhood` / `single`
  rungs (the ladder inserts, it does not replace); horizontal / column cropping
  (windowing is vertical-only); and interactive scrolling of the pinned pane.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — add `_render_windowed_diagram`
  (or a `window=(active, budget)` path in `_render_fsm_diagram` /
  `_render_layered_diagram`); reuse `LayerAssigner`, `CrossingMinimizer`,
  `_render_layered_diagram`, `layer_of` / `row_start` maps.
- `scripts/little_loops/cli/loop/_helpers.py` — add a `"window"` branch in
  `_build_pinned_pane._render_one` (~lines 304-333), insert into the ladder in
  `_render_pinned_pane` (~lines 429-437), and thread the height budget from
  `_choose_pinned_layout` into the windowed build.
- `scripts/little_loops/cli/loop/diagram_modes.py` — (optional) add `"window"`
  to `TOPOLOGY_VALUES` and `TOPOLOGY_TO_DETAIL`, plus a preset if desired.

### Dependent Files
- `scripts/little_loops/cli/loop/__init__.py` — argparse `--show-diagrams`
  validator (`_parse_show_diagrams`) if a `window` topology value is added.
- `run_background` in `_helpers.py` forwards the raw `--show-diagrams` string
  verbatim, so background runs need no extra wiring beyond the new value.

### Similar Patterns
- `_render_neighborhood_diagram` (`layout.py:1849`) — the fallback being
  augmented; its bounded-height contract (`max(preds,succs,1)*3`) is the model
  for "fit the viewport", done here by layer windowing instead.
- `mode`/`title_only`/`suppress_labels` plumbing from ENH-1652 shows how to
  thread a new render parameter cleanly through `_compute_box_sizes`.

### Tests
- `scripts/tests/test_ll_loop_display.py` — new class (e.g.
  `TestWindowedDiagram`): active-state-centered window, overflow banner
  presence, height ≤ budget, active box always inside the window, off-path
  handling, `None` active state.
- `scripts/tests/test_loop_cli_defaults.py` / `test_ll_loop_display.py` —
  ladder selection: assert `window` is chosen over `neighborhood` when it fits.

### Documentation
- `docs/reference/CLI.md`, `docs/guides/LOOPS_GUIDE.md` — `--show-diagrams`
  values / fallback behavior.
- `CHANGELOG.md` — "Added" entry.

## Implementation Steps

1. Add a windowed render path in `layout.py` (`_render_windowed_diagram`, or a
   `window=(active, budget)` branch in `_render_layered_diagram`) that reuses
   `LayerAssigner` / `CrossingMinimizer` and crops rendered rows to ±K layers
   around the active state's layer, cutting cleanly at box boundaries.
2. Emit overflow affordances above/below the window and keep truncated stubs for
   back-edges that cross it, so global position and cycles aren't silently lost.
3. Thread the height budget from `_choose_pinned_layout` through
   `_build_pinned_pane` / `_render_pinned_pane` into the windowed builder so K is
   sized to the viewport; add the `"window"` branch and insert it into the
   layered ladder above `neighborhood`.
4. (Optional) Add `"window"` to `TOPOLOGY_VALUES` / `TOPOLOGY_TO_DETAIL` and the
   `_parse_show_diagrams` validator so power users can force it explicitly.
5. Handle edge cases: `None`/unknown active state (window the graph top),
   off-path active state (defer to the existing `main`-scope `full` fallback),
   and a 1-layer window that still doesn't fit (defer to `single`).
6. Add `TestWindowedDiagram` coverage plus a ladder-selection test, and update
   `docs/reference/CLI.md`, `docs/guides/LOOPS_GUIDE.md`, and `CHANGELOG.md`.

## Impact

- **Priority**: P3 — UX quality on the most-seen fallback rung; opt-in display
  path, no automation depends on it.
- **Effort**: Medium — reuses the layout pipeline; new work is layer-window
  selection, clean row cropping at box boundaries, overflow banners, and
  threading the height budget into the builder.
- **Risk**: Low — additive display path; full/neighborhood/single rungs
  unchanged if the ladder inserts rather than replaces.
- **Breaking Change**: No.

## Related Issues

- ENH-2062 — added the neighborhood rung this improves on.
- ENH-2411 — topology-aware fallback selection; would pick window vs.
  neighborhood vs. outline based on FSM shape.
- ENH-1652 / ENH-1702 / ENH-1672 — `--show-diagrams` mode/preset/modifier
  plumbing this extends.
- FEAT-670 — the adaptive layout engine being windowed.

## Status

**Open** | Created: 2026-06-30 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-07-01T00:35:22 - `20066cd1-3a9b-408d-8c8e-0304c9a4fe9d.jsonl`
- `/ll:confidence-check` - 2026-07-01T00:40:00 - `aeea8dae-2fb9-4090-9cbd-6df3709031d2.jsonl`
