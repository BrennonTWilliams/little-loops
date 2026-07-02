---
id: ENH-2442
title: Extend windowed rung to the non-TTY streaming FSM diagram path
type: ENH
priority: P3
status: done
captured_at: '2026-07-02T17:05:15Z'
completed_at: 2026-07-02 19:53:49+00:00
discovered_date: 2026-07-02
discovered_by: capture-issue
labels:
- enhancement
- cli
- loop
- diagram
- rendering
- ux
relates_to:
- ENH-2410
- ENH-2411
- BUG-2425
decision_needed: false
confidence_score: 97
outcome_confidence: 91
score_complexity: 23
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 23
---

# ENH-2442: Extend windowed rung to the non-TTY streaming FSM diagram path

## Summary

The "windowed" FSM diagram rung (ENH-2410 — real layered diagram cropped to ±K
layers around the active state with `▲ N above / ▼ M below` overflow banners)
is currently **only reachable from the pinned-pane (TTY) ladder**. The
streaming / non-TTY renderer (`_render_streaming_diagram` in
`scripts/little_loops/cli/loop/_helpers.py`) explicitly skips the `window`
rung — see the `if rung in ("full", "window"): continue` at
`_helpers.py:705-706` — so background runs, `tee`-piped output, log captures,
and any other non-TTY sink degrade straight from the full layered diagram to
the synthetic `preds → [active] → succs` neighborhood view, dropping the
real topology that the pinned-pane path now preserves.

Wire the windowed rung into the streaming path with a per-event row budget
derived from terminal width (e.g. `max(8, cols // 4)`), so that wide
streaming diagrams degrade `full → window → neighborhood → single` rather
than `full → neighborhood → single`.

## Current Behavior

`_render_streaming_diagram` (`scripts/little_loops/cli/loop/_helpers.py:629-712`)
builds the same `_build_fallback_ladder` ladder as the pinned-pane path
(line 703) but then walks it with:

```python
for rung in ladder:
    if rung in ("full", "window"):
        continue   # ← deliberate skip
    variant = _render_rung(rung)
    if variant and _variant_width(variant) <= cols:
        return variant
```

The docstring at lines 650-652 justifies the skip: *"skipping `window` which
needs a row budget the log has none of"*. BUG-2425 (commit `8874406c`) wired
the streaming path to the ENH-2411 ladder for width degradation, but did
not add the window rung — the rationale was sound (the original ENH-2410
window API took a `budget: int` of available rows, and a streaming log has
no scroll-region to size that against).

Concretely: running `ll-loop run deep-research "$(cat res-prompt.txt)" --source_filter "site:github.com"`
with `show_diagrams: "clean"` (the user's local config) renders the
synthetic 1-hop neighborhood view in the captured run log, while the same
loop viewed in the pinned pane would show the windowed ±K-layer crop of the
real layered diagram.

## Expected Behavior

A wide/overflowing FSM on the streaming path should degrade through the same
windowed rung as the pinned pane, preserving true layout, real arrows, and
the active state's actual neighborhood before falling back to the synthetic
`preds → [active] → succs` view. The streaming ladder should mirror the
pinned-pane ladder for the `full → window → neighborhood → single`
progression; only the row-budget source differs (pinned pane uses terminal
`rows - min_action_rows`; streaming uses a per-event budget derived from
`cols`).

`title_only` and `title_only_nolabels` rungs (ENH-2411) should remain
eligible in the streaming ladder as well — they degrade width cheaply and
need no row budget, so the existing skip already affects only `window`.

## Motivation

The windowed view is the **only** degraded rung that preserves real FSM
topology — the neighborhood view discards layout entirely and renders
predecessors as an unbounded single vertical column, which on hub states is
often taller and uglier than the full diagram it was meant to replace
(ENH-2410's own rationale). Making it pinned-pane-only creates a UX split
where the same loop looks meaningfully different depending on whether it is
viewed in a TTY or captured to a log:

- Background / `nohup` / `tmux send-keys` runs (used by `ll-auto`,
  `ll-parallel`, `ll-sprint`, the scratch-pad redirect hook, and the
  `auto_handoff_threshold` continuation prompt) all see the worse view.
- The progress events that loop operators copy into issue threads or
  hand-off prompts come from the streaming path, so the diagrams that
  appear in `.ll/decisions.yaml` evidence blocks and in PR-review
  screenshots are systematically less informative than what the operator
  saw live.
- It bakes in a regression risk: any future change to the pinned-pane
  ladder (ordering, rung additions, banners) will diverge silently from
  the streaming ladder, because the two paths build the same ladder
  but consume it differently.

Bringing the streaming ladder into parity with the pinned-pane ladder —
modulo the row-budget source — removes the UX split and the divergence
risk.

## Proposed Solution

Thread the streaming path through the windowed rung with a per-event budget
derived from terminal width. Sketch:

1. In `_render_streaming_diagram` (`_helpers.py:629`), import
   `_render_windowed_diagram` from `scripts/little_loops/cli/loop/layout.py`
   and add a `_render_rung("window")` branch that calls it with
   `budget = max(8, cols // 4)` (≥8 rows so a single active layer + 2 banners
   can always fit; `cols // 4` scales with width so wider logs get taller
   windows). Thread the existing `facets` through as `mode=scope`,
   `suppress_labels=not facets.edge_labels`,
   `title_only=facets.state_detail == "title"` to match the
   `_build_pinned_pane` window call at `_helpers.py:431-442`.
2. Remove the `if rung in ("full", "window"): continue` guard at
   `_helpers.py:705-706`, so the ladder walk includes the windowed rung in
   its natural position (after `full`, before `neighborhood`).
3. Add a width check (`_variant_width(variant) <= cols`) to keep the
   existing streaming-path width-fallback invariant from BUG-2425.
4. Update the docstring (lines 640-655) to drop the "skipping `window`"
   sentence and note that window's row budget is now per-event.
5. Add regression tests mirroring the pinned-pane tests for windowed
   fallback: a fixture with a 20-state linear FSM, a tight `cols`, and
   assertions that the streaming output contains the `▲` / `▼` banners
   (proving the windowed rung was hit) rather than the `fsm: … → … → …`
   single-line neighborhood marker.

Reuse the existing `_render_windowed_diagram` API — no layout-side changes
needed. The `budget` parameter already returns `""` when no window fits
(layout.py:1736-1739), so the existing `if variant and …` filter handles
the degenerate case (very narrow terminal width where even one layer won't
fit) by skipping straight to `neighborhood`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — `_render_streaming_diagram`
  (~lines 629-712): import windowed renderer, add `_render_rung("window")`
  branch, remove the skip guard at line 705, update docstring at lines 640-655.
- `scripts/tests/test_*.py` — add a streaming-path regression test for the
  windowed rung (mirror the existing pinned-pane windowed-fallback tests).

### Dependent Files (Callers/Importers)
- `_render_streaming_diagram` is invoked from
  `StateFeedRenderer._render_diagram_event` (search for `_render_streaming_diagram`
  callers). No public API change; internal renderer only.
- _Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py:640` (lazy import) and
  `lifecycle.py:645-647` (instantiation) — `cmd_monitor` constructs
  `StateFeedRenderer` here, so the monitor / `ll-loop monitor` /
  `auto_handoff_threshold` continuation flow all exercise the streaming
  path with the new windowed rung. No code change required at this site;
  listed so the implementer can verify the monitor flow visually post-change
  (Implementation Step 6 already covers this).
- _Wiring pass added by `/ll:wire-issue` (transitively covered, not
  affected):_
- `scripts/tests/test_state_feed_renderer.py` — ~30+ `StateFeedRenderer`
  instantiations (`TestStateFeedRendererHandleEvent`) transitively call
  `handle_event` → `_render_streaming_diagram`. Verified by Agent 3 to use
  a 2-state FSM and assert on event-level strings only; none reference
  `▲`, `▼`, `layers above`, `layers below`, or `fsm:`. **Not affected.**
- `scripts/tests/test_cli_loop_lifecycle.py:2681, 2717, 2745` —
  `TestMonitorCmd` patches `StateFeedRenderer` at module-of-origin with
  `in_pinned_mode = False` (no diagram rendered). **Not affected.**
  Note: the patch path `little_loops.cli.loop._helpers.StateFeedRenderer`
  is the canonical patching site (per comment at
  `lifecycle.py:636-637`); no test-side changes needed for this issue.

### Similar Patterns
- `_build_pinned_pane` (`_helpers.py:361-524`) is the canonical example for
  how to thread `facets` and `scope` through the windowed rung — match its
  argument wiring at `_helpers.py:423-442` (the `detail == "window"` branch
  of its inner `_render_one`).

### Tests
- Existing pinned-pane windowed tests in
  `scripts/tests/test_fsm_diagram_window.py` (search for `window`) cover
  the layout-side window slicing. Add a streaming-side equivalent in the
  same module or `scripts/tests/test_loop_rendering.py` that mocks a wide
  FSM and asserts the streaming output contains the `▲` / `▼` banners.
- > ⚠ Stale anchor: `scripts/tests/test_fsm_diagram_window.py` and `scripts/tests/test_loop_rendering.py` do not exist on disk. Verified replacements — see `## Codebase Research Findings` below. The "search for `window`" hedge was correct that the author didn't have the exact path.

#### Additional tests to add (wiring pass)

_Wiring pass added by `/ll:wire-issue`:_

- **Negative-path test for degenerate `_render_windowed_diagram` returns**
  — no current test pins that when `_render_windowed_diagram` returns `""`
  (because `budget <= 0` per `layout.py:2032-2033`, `len(all_states) <= 1`
  per `layout.py:2051-2052`, or the layered crop guard fires at
  `layout.py:1735-1739`), the streaming walk transparently falls through
  to `neighborhood`. The `if variant` filter at `_helpers.py:708` handles
  it, but a regression test would lock the degenerate-bounds contract.
  Add to `scripts/tests/test_loop_layout_alignment.py` near the existing
  `test_streaming_diagram_degrades_when_too_wide`; use a 1-state FSM
  fixture + `cols=10` to force the empty return, then assert the
  rendered output is the single-line `fsm: … → …` neighborhood marker.
- **Streaming-ladder-walk pin test** — no test currently asserts that
  `_render_streaming_diagram`'s walk now includes `window` in its natural
  position. Add a focused test that monkeypatches the dispatcher
  (`_render_rung` at `_helpers.py:664-697`) to record which rungs were
  called, then asserts the sequence includes `"window"` after `"full"`
  and before `"neighborhood"`. This is the lock-in test that catches any
  future regression that re-introduces the skip guard.
- **Optional integration test using the actual `deep-research` loop** —
  `scripts/tests/test_deep_research.py:197-199` and
  `scripts/tests/test_deep_research_arxiv.py` already load the
  `deep-research` and `deep-research-arxiv` loops via
  `resolve_loop_path("deep-research", get_builtin_loops_dir())`. An
  end-to-end test that passes the real loop's FSM through
  `_render_streaming_diagram` with `cols=60` and `facets=_clean_facets()`
  would catch the actual user scenario (20+ states with multiple
  back-edges) at integration level. Optional — the synthetic 20-state
  `_make_back_edge_heavy_fsm(n=20)` test from the issue's Implementation
  Step 4 covers the unit case.

#### Tests that DO NOT need updating (verified by Agent 3)

_Wiring pass added by `/ll:wire-issue`:_

- `test_streaming_diagram_fits_width` (`test_loop_layout_alignment.py:208`)
  — width-invariant test; `_variant_width(variant) <= cols` guard stays.
- `test_streaming_diagram_degrades_when_too_wide`
  (`test_loop_layout_alignment.py:233`) — asserts rendered width is
  strictly less than full; windowed render is also strictly less.
- `TestTopologyAwareLadder.test_clean_preset_omits_redundant_title_only`
  (`test_ll_loop_display.py:4832-4839`) — pins the
  `["full", "window", "neighborhood", "single"]` ladder, but only
  against `_build_fallback_ladder` directly; `_build_fallback_ladder` is
  not modified by this change.
- `TestWindowedDiagram` (`test_ll_loop_display.py:4508-4646`) — directly
  tests `_render_windowed_diagram`; the function is reused unchanged.
- `TestStateFeedRendererHandleEvent` (`test_state_feed_renderer.py:74+`)
  — uses a 2-state FSM that never overflows; no diagram-content
  assertions.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` § show_diagrams may need a note
  that streaming and pinned-pane outputs now share the same ladder.
- `CHANGELOG.md` (via `manage-release`) for the next minor version.
- _Wiring pass added by `/ll:wire-issue` (parity-note candidates — FYI, optional):_
- `docs/reference/CLI.md:531` — `--show-diagrams[=MODE]` row describes
  the auto-degrade ladder generically; one-line note that the streaming
  path is now in parity would match the new behavior. Not a contradiction
  to the current text.
- `docs/guides/LOOPS_GUIDE.md:532` — `loops.run_defaults.show_diagrams`
  field description; same pattern as CLI.md.
- `docs/reference/OUTPUT_STYLING.md:25-28` — references the pinned-pane
  fallback ladder implicitly; optional one-line note on streaming parity.
- _Wiring pass added by `/ll:wire-issue` (CHANGELOG — DO NOT edit
  `[Unreleased]`):_
- Per project memory `feedback_changelog_no_unreleased.md`: do NOT add
  this change to `CHANGELOG.md` `[Unreleased]`. The entry should be
  promoted to a concrete `## [X.Y.Z] - DATE` section at release-prep
  time via `manage-release`. The issue's original "via `manage-release`
  for the next minor version" line is correct in intent; the
  `[Unreleased]` skip is implicit.

### Configuration
- N/A — no new config keys. The `loops.run_defaults.show_diagrams` knob
  already governs both paths.

## Implementation Steps

1. Import `_render_windowed_diagram` in `_render_streaming_diagram` and
   add the `_render_rung("window")` branch with `budget=max(8, cols // 4)`.
2. Drop the `if rung in ("full", "window"): continue` filter so the natural
   ladder order applies; add the existing `if variant and _variant_width(variant) <= cols`
   guard for the window rung (cheap, already computed per rung).
3. Update the docstring (lines 640-655) to reflect the new rung inclusion
   and the per-event budget semantics.
4. Add a regression test under `scripts/tests/` that renders a 20-state
   linear FSM in the streaming path with `cols=60` and asserts the output
   contains windowed-rung signatures (`▲ N layers above`, `▼ M layers
   below`) and does **not** contain the single-line neighborhood marker.
5. Run the full suite (`python -m pytest scripts/tests/`) and confirm no
   pinned-pane tests regress (the pinned-pane ladder is unchanged).
6. Optional: run `ll-loop run <some-loop> 2>&1 | tee /tmp/run.log` on a
   wide loop and visually confirm the log shows the windowed banner rather
   than the neighborhood view.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Add the negative-path degenerate-budget regression test described
   under `### Tests → Additional tests to add` in
   `scripts/tests/test_loop_layout_alignment.py` (1-state FSM + `cols=10`,
   assert single-line `fsm: … → …` neighborhood marker is returned).
8. Add the streaming-ladder-walk pin test that monkeypatches
   `_render_rung` to record the called-rung sequence and asserts
   `["full", "window", "neighborhood", "single"]` ordering (or the
   hub-heavy variant) is observed. Place in
   `scripts/tests/test_loop_layout_alignment.py` next to the existing
   streaming tests.
9. (Optional) Add an integration test that loads the actual
   `deep-research` loop via `resolve_loop_path("deep-research",
   get_builtin_loops_dir())` (see `scripts/tests/test_deep_research.py:197-199`)
   and passes its FSM through `_render_streaming_diagram` with `cols=60`
   to mirror the user's exact repro scenario.
10. (Optional, parity-note docs) Add a one-line note to
    `docs/reference/CLI.md:531`, `docs/guides/LOOPS_GUIDE.md:532`, and
    `docs/reference/OUTPUT_STYLING.md:25-28` clarifying that the
    streaming path now shares the pinned-pane ladder. Skip if not
    desired — no doc currently contradicts the new behavior.
11. Do NOT add a `CHANGELOG.md` `[Unreleased]` entry per project memory
    `feedback_changelog_no_unreleased.md`; defer to `manage-release` for
    the next minor version's concrete release section.

## Impact

Priority: **P3** (UX consistency, not blocking). Justification: the
streaming path already degrades via the neighborhood view today, so this
is an upgrade, not a fix; no user is blocked, but every background run
quietly produces a worse diagram than its foreground twin.

Complexity: low. Single renderer function, one branch added, one guard
removed. Reuses the existing `_render_windowed_diagram` API surface — no
layout-side changes.

Risk: low. The change is additive in the streaming path; the pinned-pane
ladder and its tests are untouched. Worst-case failure mode is the
windowed rung returning `""` for a very narrow `cols`, in which case the
existing `if variant` filter skips it and the streaming output falls back
to `neighborhood` — identical to today's behavior. BUG-2425 regression
tests for width degradation stay green because `_variant_width(variant) <= cols`
remains the width-fallback invariant.

Backwards compatibility: full. The streaming output gains a better rung
where one was skipped; no caller-visible signature change.

## Success Metrics

- Before/after: capture the run-log of a known-wide loop (e.g.
  `general-task`, 20 states) under `cols=80` with `show_diagrams: "clean"`
  in both code states. Before: output contains `fsm: … → [<active>] → …`
  (single-line neighborhood) once the full diagram exceeds `cols`. After:
  output contains `▲ N layers above` / `▼ M layers below` banners instead,
  proving the windowed rung was hit.
- Test coverage: add ≥1 streaming-path regression test asserting the
  banner presence; existing pinned-pane windowed tests stay green
  (≥10 tests, currently passing).
- Width invariant: existing BUG-2425 width-bound tests still pass (no
  regression in the no-overflow case).

## Scope Boundaries

- **In scope**: extending the windowed rung to `_render_streaming_diagram`
  in `_helpers.py`, plus a regression test.
- **Out of scope**: changing the pinned-pane ladder (already correct per
  ENH-2410/2411); changing the windowed renderer's budget semantics or
  banner format (ENH-2410 settled those); changing the streaming path's
  width-degradation logic beyond removing the window-skip guard; adding a
  new rung (e.g. windowed + title-only combo) — the existing
  `title_only` rungs already sit in the ladder and will be tried naturally.
- **Out of scope**: fixing the `effective_min_action_rows` heuristic in
  `_render_pinned_pane` (already handled for `state_detail == "title"` at
  `_helpers.py:560`); not a streaming-path concern.

## API/Interface

Internal renderer change only. No public API surface affected. The change is
confined to `_render_streaming_diagram` in
`scripts/little_loops/cli/loop/_helpers.py`. External callers (the
`StateFeedRenderer` and the streaming event sink) see the same string
return shape — just better content on the wide-diagram path.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — loop-fallback ladder
  semantics; this issue extends them to the streaming path.
- `docs/reference/HOST_COMPATIBILITY.md` § show_diagrams — may need a
  one-line note that streaming and pinned-pane ladders are now in parity.
- `docs/reference/API.md#little_loopscli_loop` — `_render_streaming_diagram`
  docstring will reflect the change.

## Codebase Research Findings

_Added by `/ll:refine-issue --auto` — based on codebase analysis (locator + analyzer + pattern-finder agents). Existing sections preserved verbatim; this is additive only._

### Verified file locations and line numbers

- `_render_streaming_diagram` lives in `scripts/little_loops/cli/loop/_helpers.py:629-712`. The skip-guard `if rung in ("full", "window"): continue` is at lines 705-706. The docstring justifying the skip is at lines 640-655 (the "skipping `window` which needs a row budget the log has none of" sentence).
- `_render_windowed_diagram` is defined at `scripts/little_loops/cli/loop/layout.py:2006`. Its `window` parameter is `tuple[str | None, int] | None = None` (active state, row budget) and it returns `""` when `budget <= 0`, `len(all_states) <= 1`, or even the active layer plus banners doesn't fit the budget.
- The canonical window-rung call to mirror is at `_helpers.py:423-442` in `_build_pinned_pane._render_one`, including the off-happy-path `scope = "full"` fallback when the highlight state was filtered out of the main-scope graph.
- The streaming `_render_rung` dispatch is an `if/elif` chain (not a dict) at `_helpers.py:664-697`. The new `window` branch slots in before the `if detail == "title_only":` group.
- `_render_windowed_diagram` is also the layer-7+ signature (the full one — see `layout.py:2006-2018`): `(fsm, active_state, *, budget, verbose=False, highlight_color="32", edge_label_colors=None, badges=None, mode="full", suppress_labels=False, title_only=False) -> str`. Reuse as-is.

### Sole caller (verified)

- The only caller of `_render_streaming_diagram` is `StateFeedRenderer.handle_event` in `_helpers.py:786-887`. The diagram dispatch is at `_helpers.py:875-887` and passes:
  ```python
  diagram = _render_streaming_diagram(
      active_fsm_diag,
      active_highlight,
      facets=self.facets,
      highlight_color=self.highlight_color,
      edge_label_colors=self.edge_label_colors,
      badges=self.badges,
      scope=active_scope,   # ← already-resolved (off-path fallback at lines 863-874)
      cols=tw,              # ← terminal_width() value (line 798)
  )
  ```
  `active_scope` is already `'main'` or `'full'` (off-happy-path fallback has already run before `_render_streaming_diagram` is called), so the new streaming `_render_rung("window")` branch should pass `scope` straight through without the pinned-pane's `_filter_main_path_graph` guard.

### Test-file location correction (stale references)

The Integration Map → Tests subsection names two files that do **not** exist on disk. Verified replacements:

- **Pinned-pane window tests**: `scripts/tests/test_ll_loop_display.py` (the actual test module, ~5000 lines).
  - `TestWindowedDiagram` class at line 4508 — unit tests for `_render_windowed_diagram`
  - `TestWindowedDiagramPassThroughPipes` at line 4614
  - `TestWindowedLadderIntegration` at line 4650 — pinned-pane ladder selection (mirrors `assert "layers above" in pane or "layers below" in pane` style)
  - `TestTopologyAwareLadder` at line 4734 — covers `_build_fallback_ladder` ordering across chain/tree/hub FSMs
- **Streaming-path tests** (where the new regression test belongs): `scripts/tests/test_loop_layout_alignment.py` (already exercises `_render_streaming_diagram`):
  - `test_streaming_diagram_fits_width` at line 208 — width-invariant test
  - `test_streaming_diagram_degrades_when_too_wide` at line 233 — ladder-walk test (canonical template for the new test; uses `monkeypatch.setattr("little_loops.cli.loop.layout.terminal_width", lambda **_kw: tw)` + `cols=40` + a back-edge-heavy FSM fixture at line 169-178 `_make_back_edge_heavy_fsm(n=8)`)

### Test patterns to mirror in the new regression test

1. **Direct-call fixture pattern** from `test_loop_layout_alignment.py:233-262`:
   ```python
   from little_loops.cli.loop._helpers import _render_streaming_diagram

   tw = 80
   monkeypatch.setattr("little_loops.cli.loop.layout.terminal_width", lambda **_kw: tw)
   fsm = _make_back_edge_heavy_fsm(n=8)
   full = _render_fsm_diagram(fsm, title_only=True, mode="full")
   cols = 40
   assert _max_line_display_width(full) > cols  # precondition: forces degradation

   rendered = _render_streaming_diagram(
       fsm, "s0",
       facets=_clean_facets(),   # DiagramFacets("layered", False, "title", "main", "preset")
       highlight_color="32",
       edge_label_colors=None, badges=None,
       scope="full", cols=cols,
   )
   ```
2. **Banner-assertion pattern** from `test_ll_loop_display.py:4508-4539`:
   - `assert "▲" in out` is safe (▲ is banner-only).
   - `▼` is unreliable — it's also the diagram's own arrow tip. Use `assert "layers above" in out and "layers below" in out` instead.
   - Banner-count regex: `assert re.search(r"▲ \d+ layers above", above_line)` and `re.search(r"▼ \d+ layers below", below_line)`.
   - Active-box-presence: `assert any("s10" in ln for ln in lines if not any(t in ln for t in ("layers above", "layers below")))` — the active state must appear in a non-banner line.
3. **FSM fixture**: use `_make_back_edge_heavy_fsm(n=20)` (a private helper in `test_loop_layout_alignment.py:169-178`) instead of duplicating `_chain_fsm` from `test_ll_loop_display.py` (which is private to that module and not re-exported).

### Refinement to Implementation Step 1 (scope guard)

The Proposed Solution step 1 includes a copy of the pinned-pane off-happy-path guard:
```python
if scope == "main" and highlight is not None:
    _fe, reachable = _filter_main_path_graph(target, _collect_edges(target))
    if highlight not in reachable:
        scope = "full"
```
This guard is **not needed** in the streaming branch — `StateFeedRenderer.handle_event` already runs the same `_filter_main_path_graph` off-path fallback at `_helpers.py:863-874` and passes the resolved scope as `active_scope`. The streaming `_render_rung("window")` should just pass `scope` through directly, mirroring how `_render_rung("neighborhood")` (line 668-676) does not re-run the guard.

### Configuration knob (verified)

- The user-cited config key is `loops.run_defaults.show_diagrams`. Verified at `.ll/ll-config.json:94` with value `"clean"`.
- The `show_diagrams` enum in `config-schema.json:927` includes: `layered`, `neighborhood`, `inline`, `detailed`, `summary`, `clean`, `local`, `slim`, `oneline`, `default`, `null`. The `"clean"` preset maps to `DiagramFacets("layered", False, "title", "main", "preset")` (verified via `_clean_facets` in `test_loop_layout_alignment.py:188-191`).
- No new config keys are needed for this change.

### Ladder ordering after the skip-guard removal

`_build_fallback_ladder` at `_helpers.py:293-344` returns either of:
- `["full", *keep_all, "window", "neighborhood", "single"]` (for `linear`/`tree` topology or `too_wide`)
- `["full", "window", *keep_all, "neighborhood", "single"]` (for hub-heavy general graphs)

Once the `if rung in ("full", "window"): continue` filter is removed from the streaming path, `window` will be reached in its natural position for both topologies. `title_only` and `title_only_nolabels` (the `*keep_all` slots) are already in the ladder and are NOT skipped by the current guard, so they remain eligible.

### Risk / "what if window returns `""`"

`_render_windowed_diagram` returns `""` in three cases (verified from the layout.py docstring at lines 2019-2030, with three concrete return sites):
1. `budget <= 0` — `layout.py:2032-2033`
2. `len(all_states) <= 1` — `layout.py:2051-2052`
3. Even the active layer plus its banners doesn't fit `budget` — `_render_layered_diagram` windowed-crop guard at `layout.py:1735-1739` (`_pane_height(lo, hi) > win_budget`)

The streaming ladder's existing `if variant and _variant_width(variant) <= cols` filter at `_helpers.py:708` handles all three cases transparently — `variant` is empty/falsy, the filter is skipped, and the walk continues to `neighborhood`. **No additional defensive code is needed in the new branch.**

### Additional corroboration on the scope-guard refinement

The streaming `_render_rung` does NOT re-run the `_filter_main_path_graph` off-happy-path guard for **any** of its existing branches — even the `neighborhood` branch (lines 668-676) passes `mode=scope` straight through, exactly as the new `window` branch should. The guard is only run in `_build_pinned_pane._render_one` (lines 426-430), which is the pinned-pane path. The streaming path's `scope` resolution is the sole responsibility of `StateFeedRenderer.handle_event` at `_helpers.py:863-874`.

## Resolution

Implemented per the Proposed Solution: `_render_streaming_diagram`
(`scripts/little_loops/cli/loop/_helpers.py`) now imports
`_render_windowed_diagram` and adds a `"window"` branch to its `_render_rung`
dispatcher, passing `budget=max(8, cols // 4)` and the same `facets`/`scope`
wiring the pinned-pane path uses. The `if rung in ("full", "window"): continue`
skip guard was narrowed to `if rung == "full": continue`, so the ladder walk
now reaches `window` in its natural position (after `full`, before
`neighborhood`). The docstring was updated to drop the "skipping `window`"
note and describe the per-event row budget.

Four regression tests were added to `scripts/tests/test_loop_layout_alignment.py`:
mocked-primitive tests proving the window rung is selected (with the correct
budget) when the full render is too wide, that an empty window return falls
through transparently to neighborhood, and a call-order pin test asserting
the streaming walk tries `window` immediately after `full`; plus a real
(unmocked) single-state degenerate-case test locking in the documented
`_render_windowed_diagram` empty-return contract. Real-FSM width probing was
not used for the positive-path tests because `_render_windowed_diagram`'s
overflow-banner and back-edge-margin sizing couples to the live
`terminal_width()` rather than the caller's `cols` — a pre-existing,
out-of-scope characteristic that made real-geometry tests fragile; mocking
the render primitives isolates the ladder-walk plumbing this issue actually
changes.

Full suite: `python -m pytest scripts/tests/` — 13,466 passed, 23 skipped, 2
pre-existing failures in `test_cli_ctx_stats.py::TestLearningTestsSection`
(unrelated to this change; reproduced on a clean `main` checkout before this
fix). `ruff check` and `mypy` both pass clean on the touched files.

## Status

open

## Session Log
- `/ll:manage-issue` - 2026-07-02T19:53:49 - `d0f5485a-435a-42ed-b105-a5d0614d9f7c.jsonl`
- `/ll:ready-issue` - 2026-07-02T18:45:51 - `52421ecf-5582-4fa9-b2bd-5613da136f07.jsonl`
- `/ll:confidence-check` - 2026-07-02T17:55:00 - `136de175-2f3f-4324-8158-7bd96f3eca35.jsonl`
- `/ll:wire-issue` - 2026-07-02T17:37:29 - `1007c946-2aa1-49f1-8044-27c09628764d.jsonl`
- `/ll:refine-issue` - 2026-07-02T17:20:51 - `91a2eb95-9a6a-479d-9595-dfaee9d027a0.jsonl`
- `/ll:refine-issue` - 2026-07-02T17:18:50 - `91a2eb95-9a6a-479d-9595-dfaee9d027a0.jsonl`
