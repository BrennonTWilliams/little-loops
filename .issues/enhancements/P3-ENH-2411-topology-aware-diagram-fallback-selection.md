---
id: ENH-2411
title: Topology-aware diagram fallback selection (branch on why full doesn't fit,
  not always neighborhood)
type: ENH
priority: P3
status: done
captured_at: '2026-06-30T00:27:20Z'
discovered_date: '2026-06-30'
discovered_by: capture-issue
relates_to:
- ENH-2062
- ENH-2410
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
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
completed_at: '2026-07-01T01:55:17Z'
---

# ENH-2411: Topology-aware diagram fallback selection

## Summary

The pinned-pane fallback ladder is a single fixed sequence
(`full → neighborhood → single`) applied to every loop regardless of shape.
But *why* the full diagram doesn't fit differs by topology: a long linear
chain is too **tall** but narrow; a wide fan-out is too **wide** but short; a
hub-heavy general graph is both. One fallback can't be right for all three.
Branch the fallback on the FSM's classified topology (and on the failing
dimension) so each loop degrades to the view that suits it — keeping the whole
graph visible where possible instead of always collapsing to the 1-hop
neighborhood.

## Current Behavior

`_render_pinned_pane` (`scripts/little_loops/cli/loop/_helpers.py`, ~lines
479-496) builds a fixed ladder based only on the requested `topology` /
`source`:

```python
topo_detail = TOPOLOGY_TO_DETAIL[facets.topology]
raw_variants: list[str | None]
if facets.source == "topology":
    # A "window" topology can fail to fit and return None; fall back to single.
    raw_variants = [v for v in [_build(topo_detail)] if v is not None] or [_build("single")]
elif topo_detail == "full":
    raw_variants = [
        _build("full"),
        _build("window"),
        _build("neighborhood"),
        _build("single"),
    ]
elif topo_detail == "neighborhood":
    raw_variants = [_build("neighborhood"), _build("single")]
else:  # inline / single
    raw_variants = [_build("single")]
```

(The `window` rung between `full` and `neighborhood` landed with ENH-2410,
now `done`; the ladder is still a single fixed sequence applied regardless of
topology — the shape this issue addresses.)

`_choose_pinned_layout` then picks the first that fits by **height only**.
Nothing consults the FSM's shape. Yet `TopologyDetector.classify()`
(`layout.py:373`) already labels every loop `linear` / `tree` / `general`, and
`_render_fsm_diagram` already supports cheaper renderings (`title_only`,
`suppress_labels`) that keep the *entire* graph, just denser. These are never
tried before the jump to the synthetic neighborhood view.

## Expected Behavior

When the full-detail diagram doesn't fit, choose the degraded rung by
topology and by which viewport dimension is exceeded:

- **linear / tree** (too tall, narrow): prefer detail-shedding rungs that keep
  every state — `title-only` → `title-only + suppress-labels` → horizontal /
  column-fold — before neighborhood. The whole chain stays visible.
- **general, too tall (hub-heavy)**: prefer the windowed diagram (ENH-2410) or
  an outline/tree-text view; only then neighborhood.
- **too wide** (fan-out wider than terminal): keep vertical but drop to
  `title-only` (narrower boxes) rather than a horizontal view.
- **both dimensions blown**: outline / neighborhood / single.

Concretely, replace the fixed `variants` list with a topology-driven ladder
builder that consults `TopologyDetector` (or a lightweight width/height probe
of the already-built full variant) and orders the rungs accordingly, still
terminating in `single` as the guaranteed-fit floor.

## Motivation

- The neighborhood view is the wrong degradation for the common case: linear
  and tree loops lose nothing but height, so `title-only`/horizontal keeps the
  full structure readable where neighborhood throws it away.
- The classification is already computed — this is wiring existing signal into
  the fallback decision, not new analysis.
- Turns "one ugly fallback" into "pick the degradation that fits the shape",
  and gives ENH-2410's windowed view and a future outline view a principled
  place in the ladder.

## Design Notes / Open Questions

1. **Signal source.** Use `TopologyDetector.classify()` directly, or infer the
   failing dimension by measuring the built full variant's width vs.
   `terminal_width()` and height vs. `rows`? Likely both: topology for *which*
   rungs, measured dimension for *ordering* them.
2. **Where the branch lives.** Add a `_build_fallback_ladder(facets, fsm,
   rows, cols) -> list[str]` helper feeding `_choose_pinned_layout`, keeping
   `_render_pinned_pane` thin.
3. **Dependency on new renderers.** Full value needs the alternative renderers
   to exist (windowed = ENH-2410; horizontal/column-fold and outline are
   separate). This issue can land first as pure **reordering** of existing
   rungs (`full` / `title-only` / `neighborhood` / `single`) and grow as new
   renderers arrive.
4. **Explicit topology override.** `source == "topology"` (user passed an
   explicit topology) must still bypass all auto-degradation — only
   preset/default ladders are reordered.
5. **Interaction with `state_detail`.** Presets already set
   `state_detail="title"`; the ladder must not double-apply or contradict a
   user-chosen detail level.

## Scope Boundaries

**In scope (first cut):**
- Reorder the *existing* rungs (`full` / `window` / `title-only` /
  `neighborhood` / `single`) by classified topology and the failing viewport
  dimension, via a `_build_fallback_ladder` helper feeding
  `_choose_pinned_layout`.
- Wire `TopologyDetector.classify()` (and a lightweight width/height probe of
  the built full variant) into that helper.
- Add `title-only` intermediate rungs through the existing
  `facets.state_detail` / `title_only` path — no new render code.

**Out of scope:**
- New renderers — horizontal / column-fold and outline / tree-text views are
  separate follow-on issues; this lands as pure *reordering* of rungs that
  already exist (the `window` rung already exists via ENH-2410).
- The explicit-topology path (`source == "topology"`) — it must continue to
  bypass all auto-degradation; only preset/default ladders are reordered.
- Layout-engine changes to `_render_fsm_diagram` internals beyond reusing the
  existing `title_only` / `suppress_labels` flags.
- Removing or reordering past `single`: it stays the guaranteed-fit floor and
  always terminates the ladder.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — replace the fixed `raw_variants`
  construction in `_render_pinned_pane` (~479-496) with a topology-aware
  ladder builder; thread `fsm` / `rows` / `cols` into it. Add `title-only`
  intermediate rungs via the existing `facets.state_detail` / `title_only`
  path in `_build_pinned_pane`.
- `scripts/little_loops/cli/loop/layout.py` — expose a cheap topology probe if
  not already convenient (reuse `_collect_edges` + `TopologyDetector`); no
  layout-engine change required for the reordering-only first cut.

### Dependent Files
- `scripts/little_loops/cli/loop/diagram_modes.py` — `DiagramFacets.source`
  gating (`topology` vs `preset`/`default`) already distinguishes explicit vs.
  auto ladders; the builder keys off it.

### Similar Patterns
- The existing `topo_detail`-based branch in `_render_pinned_pane` is the seam
  being generalized.
- `_build_pinned_pane` already accepts `title_only` / `suppress_labels`
  (ENH-1652), so title-only rungs need no new render code.

### Tests
- `scripts/tests/test_ll_loop_display.py` / `test_loop_cli_defaults.py` —
  ladder selection per topology: linear loop → title-only chosen before
  neighborhood; general hub loop → windowed/neighborhood; explicit
  `--show-diagrams neighborhood` still renders once with no degradation;
  `single` remains the floor.

### Documentation
- `docs/reference/CONFIGURATION.md` / `docs/guides/LOOPS_GUIDE.md` — document
  topology-aware fallback behavior.
- `CHANGELOG.md` — "Changed" entry (fallback selection is now shape-aware).

## Impact

- **Priority**: P3 — UX quality on the opt-in pinned-pane display; no
  automation depends on it.
- **Effort**: Small-Medium for the reordering-only first cut (wire existing
  classifier + title-only rungs into the ladder); grows as ENH-2410 and
  outline/horizontal renderers land.
- **Risk**: Low-Medium — changes which fallback users see; guard with tests
  and keep `single` as the guaranteed floor. Explicit-topology path unchanged.
- **Breaking Change**: No (output-only; may change which fallback appears).

## Related Issues

- ENH-2062 — introduced the fixed neighborhood rung this generalizes.
- ENH-2410 — windowed renderer this would select for tall general graphs.
- ENH-1652 / ENH-1702 / ENH-1672 — mode/preset/modifier plumbing supplying the
  title-only and topology primitives.
- FEAT-670 — `TopologyDetector` (linear/tree/general) is the classifier reused
  here.


## Session Log
- `ll-auto` - 2026-07-01T01:55:17 - `e0eeb92d-948c-475f-9b86-eebf3a96d842.jsonl`
- `/ll:ready-issue` - 2026-07-01T01:37:29 - `56c859f4-2c04-4801-8019-0944ad95465a.jsonl`
- `/ll:format-issue` - 2026-07-01T01:27:18 - `d9f2d02c-a767-40d1-86bf-f3379ca2be91.jsonl`
- `/ll:confidence-check` - 2026-07-01T01:34:03 - `88bcf0d6-f741-45ef-8e19-d91f10340cf7.jsonl`


---

## Resolution

- **Action**: improve
- **Completed**: 2026-06-30
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
