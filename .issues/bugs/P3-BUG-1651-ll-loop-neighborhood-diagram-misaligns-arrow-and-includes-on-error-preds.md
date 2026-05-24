---
captured_at: '2026-05-23T23:49:04Z'
discovered_date: 2026-05-23
discovered_by: capture-issue
relates_to:
- ENH-1642
---

# BUG-1651: `ll-loop --show-diagrams` neighborhood view misaligns succ arrow, includes on_error preds, and lacks prev-state marker

## Summary

In the pinned-pane neighborhood fallback rendered by `_render_neighborhood_diagram` (`scripts/little_loops/cli/loop/layout.py:1653`), running `ll-loop run rn-refine ... --show-diagrams --clear` with `synthesize` active draws three visible defects:

1. The `synthesize ──▶` arrow points into empty space because the single successor (`score`) is stacked at row 0 instead of next to the active state.
2. `route_files` / `route_web` show up as predecessors of `synthesize` even though they only connect via `on_error` — an off-happy-path edge that the renderer should suppress in `mode="main"`.
3. The predecessor stack on the left does not distinguish *which* predecessor the FSM most recently transitioned from. The state we just came from is visually indistinguishable from the other predecessors, even though the runtime knows it.

## Current Behavior

When `--show-diagrams --clear` activates the pinned-pane neighborhood fallback for a state with fan-in/fan-out asymmetry (here: 4 preds, 1 succ for `synthesize`):

- The single-line `──▶` successor arrow is drawn at the active state's vertical center (row 4), but the lone successor box (`score`) is stacked at row 0. The arrow points into empty space.
- States that only reach the active state via `on_error` edges (`route_files`, `route_web`) are pulled into the predecessor stack even when the caller requested `mode="main"`, because `_render_neighborhood_diagram` does not consult the main-path filter applied by `_render_fsm_diagram`.
- Every predecessor box renders with the same default border. There is no visual marker for the predecessor the FSM just transitioned from, so a user watching the pinned pane cannot tell which incoming edge fired.

The non-pinned `--show-diagrams` path (which calls `_render_fsm_diagram` directly) does not exhibit either defect.

## Expected Behavior

- The successor arrow aligns with the actual successor box on the same vertical row, regardless of `|preds|` vs `|succs|` asymmetry. Stacks shorter than `n_rows` (the smaller side) are aligned **from the arrow row** — i.e., their first item sits at the same vertical row as the active state — so the arrow always lands on a real box.
- In `mode="main"`, the neighborhood view filters out states connected only via `on_error` edges (consistent with `_render_fsm_diagram`'s main-mode filtering). For `synthesize` in main mode, only `research_files` and `research_web` appear as predecessors.
- `mode="full"` continues to include `on_error` predecessors so users explicitly asking for full topology still see them.
- When the runtime can identify the predecessor we just transitioned from (the "previous FSM state"), that predecessor's box on the left renders with an **orange border** (ANSI 33), visually distinct from the active state's highlight color (default green/32) and from the other plain-border preds. When no previous state is known (first entry, first iteration), no pred is colored.

## Steps to Reproduce

```bash
ll-loop run rn-refine path/to/some-plan.md --show-diagrams --clear
```

The `--clear` flag triggers pinned-pane mode where the full Sugiyama diagram doesn't fit, so `_choose_pinned_layout` falls back to `_render_neighborhood_diagram`. Reproduced byte-for-byte by calling `_render_neighborhood_diagram(fsm, 'synthesize')` directly:

```
┌────────────────┐                            ┌───────┐
│ research_files │                            │ score │
└────────────────┘                            └───────┘
┌────────────────┐       ┌────────────┐
│ research_web   │  ──▶  │ synthesize │  ──▶
└────────────────┘       └────────────┘
┌────────────────┐
│ route_files    │
└────────────────┘
┌────────────────┐
│ route_web      │
└────────────────┘
```

The non-pinned `--show-diagrams` path (which calls `_render_fsm_diagram` directly) is unaffected.

## Root Cause

Three independent defects in `_render_neighborhood_diagram` (`scripts/little_loops/cli/loop/layout.py:1653`):

**RC1 — Smaller stack not aligned to the arrow row.** `n_rows = max(len(preds), len(succs), 1)` (line 1700) is dominated by whichever side has more items. The active state is placed at `center_idx = (n_rows - 1) // 2` (line 1732) so its name row sits at `active_line_offset = center_idx * 3 + 1` (line 1742). But `_build_stack` (lines 1720-1727) fills items top-down (`i in range(n_rows): if i < len(labels): box(i) else: blank`), so when `len(succs) < n_rows` the single succ ends up at index 0. The horizontal `──▶` is drawn once at `active_line_offset` on both sides, pointing into empty space whenever `|preds| ≠ |succs|`. For `synthesize`: 4 preds, 1 succ → `n_rows=4`, `center_idx=1`; active sits at rows 3-5, succ at rows 0-2, arrow at row 4 lands on nothing.

**RC2 — Neighborhood ignores `mode="main"` filter.** `_render_neighborhood_diagram` calls `_collect_edges(fsm)` directly (line 1674) and never consults the main-path filter (`_filter_main_path_graph` at `layout.py:1506`). Its caller `_build_pinned_pane._render_one` (`scripts/little_loops/cli/loop/_helpers.py:277-284`) also doesn't pass a `mode` parameter when the `"neighborhood"` variant is selected — only the `"full"` variant respects `show_diagrams_mode`. This pulls `route_files` and `route_web` into the predecessor stack via their `on_error: synthesize` edges. In main mode they should be filtered out, leaving just `research_files` and `research_web`.

**RC3 — Previous state is not tracked or rendered.** `_render_neighborhood_diagram` only knows the *active* state via the `active_state` parameter; it has no notion of the predecessor the FSM most recently transitioned from. The pinned-pane runtime tracks `last_state_at_depth[depth]` in `_helpers.py:692` but overwrites it on every `state_enter`, so the prior value is lost before the neighborhood renderer is called. `_make_box` (`layout.py:1702`) supports only a binary `highlighted: bool` flag wired to the active state's `highlight_color` — there is no path for a second, differently-colored border.

RC2 alone fixes the visible misalignment for the specific synthesize-in-main-mode case (2 preds + 1 succ has `center_idx=0`, succ at index 0 already matches), but RC1 still bites whenever `|preds| ≠ |succs|`, which is common. RC3 is orthogonal: even after RC1/RC2 land, the user still cannot see *which* pred just ran.

## API/Interface

- `_render_neighborhood_diagram(...)` in `scripts/little_loops/cli/loop/layout.py:1653` gains two new keyword parameters:
  - `mode: str = "full"` — controls main-path filtering. Default preserves existing callers and the test at `scripts/tests/test_ll_loop_display.py:3208`.
  - `prev_state: str | None = None` — name of the predecessor the FSM just transitioned from. When set to a name present in the rendered pred stack, that pred's box is drawn with an orange border (ANSI 33). `None` (default) preserves today's behavior.
- `_make_box` (`layout.py:1702`) is extended to accept an optional border color override so a non-active box can take a distinct color without bolding its label like the active highlight does.
- `_build_pinned_pane` (`scripts/little_loops/cli/loop/_helpers.py:243`) gains a `prev_highlight: str | None` parameter, threaded from the runtime's per-depth previous-state tracker.
- A new `prev_state_at_depth: dict[int, str]` is maintained alongside `last_state_at_depth` in `_helpers.py` (around line 633). On `state_enter`, before overwriting `last_state_at_depth[depth]`, the old value is copied into `prev_state_at_depth[depth]`.
- No CLI-level changes.

## Proposed Solution

**Change 1 — align the smaller stack to the arrow row.** The arrow is drawn at `active_line_offset = center_idx * 3 + 1`, where `center_idx = (n_rows - 1) // 2`. Replace the top-down `_build_stack` (`layout.py:1720-1727`) with a variant that begins filling at `center_idx`, so the first label sits on the same row as the active state and the arrow lands on it. Guard the start so it cannot push items past the bottom row (matters when `|smaller| > n_rows - center_idx`, e.g. 5 preds and 4 succs):

```python
def _build_stack(labels: list[str], box_w: int, *, color_for: dict[str, str] | None = None) -> list[str]:
    rows: list[str] = []
    # Align from the arrow row (the active state's slot). Cap at the
    # bottom so longer-but-still-smaller stacks don't overflow n_rows.
    start = max(0, min(center_idx, n_rows - len(labels)))
    color_for = color_for or {}
    for i in range(n_rows):
        j = i - start
        if 0 <= j < len(labels):
            border = color_for.get(labels[j])  # None or e.g. "33"
            rows.extend(_make_box(labels[j], box_w - 4, False, border_color=border))
        else:
            rows.extend([" " * box_w] * 3)
    return rows
```

Cases:
- Symmetric (`|preds| == |succs|`): `start = 0`, identical to today.
- 4 preds, 1 succ (the synthesize case): `center_idx = 1`, `start = min(1, 3) = 1` → succ at slot 1, on the same row as the active state. Arrow lands. ✓
- 5 preds, 4 succs: `center_idx = 2`, `start = min(2, 1) = 1` → succs at slots 1–4; active at slot 2 still has a succ on its row. ✓

**Change 2 — make neighborhood respect `mode="main"`.** Add `mode: str = "full"` to `_render_neighborhood_diagram` (`layout.py:1653`). When `mode == "main"`, replace the unfiltered `_collect_edges(fsm)` at line 1674 with `_filter_main_path_graph(fsm, _collect_edges(fsm))[0]`. Thread the parameter through `_build_pinned_pane._render_one` in `_helpers.py:277-284`:

```python
if detail == "neighborhood":
    return _render_neighborhood_diagram(
        target,
        highlight or target.initial,
        edge_label_colors=edge_label_colors,
        badges=badges,
        highlight_color=highlight_color,
        mode=show_diagrams_mode,
        prev_state=prev_highlight,
    )
```

**Change 3 — orange border on the previous state.** Extend `_make_box` (`layout.py:1702`) so a non-highlighted box can take an optional border color without the active state's bold label treatment:

```python
def _make_box(label: str, inner_w: int, highlighted: bool, *, border_color: str | None = None) -> list[str]:
    top = "┌" + "─" * (inner_w + 2) + "┐"
    bot = "└" + "─" * (inner_w + 2) + "┘"
    padded = label.ljust(inner_w)
    if highlighted:
        top = colorize(top, highlight_color)
        bot = colorize(bot, highlight_color)
        mid = (colorize("│", highlight_color) + " "
               + colorize(padded, f"{highlight_color};1") + " "
               + colorize("│", highlight_color))
    elif border_color is not None:
        top = colorize(top, border_color)
        bot = colorize(bot, border_color)
        mid = (colorize("│", border_color) + " "
               + colorize(padded, "1") + " "
               + colorize("│", border_color))
    else:
        mid = "│ " + colorize(padded, "1") + " │"
    return [top, mid, bot]
```

In `_render_neighborhood_diagram`, build a `pred_color_for` map and pass it to the pred `_build_stack` call only:

```python
PREV_STATE_COLOR = "33"  # orange / yellow (ANSI 33)
pred_color_for: dict[str, str] = {}
if prev_state is not None and prev_state in preds:
    pred_color_for[_label(prev_state)] = PREV_STATE_COLOR
pred_col = _build_stack(pred_labels, box_w_pred, color_for=pred_color_for) if pred_labels else None
succ_col = _build_stack(succ_labels, box_w_succ) if succ_labels else None
```

If `prev_state` is missing from `preds` (e.g., filtered out by `mode="main"` because the transition was an `on_error` edge, or the runtime had no prior state), the orange border is silently skipped — no error, no fallback marker. This is intentional: the case is rare and the active-state highlight already conveys "where we are now."

**Change 4 — runtime threads previous state into the pinned pane.** In `_helpers.py` (around line 633), add `prev_state_at_depth: dict[int, str] = {}` next to `last_state_at_depth`. On every `state_enter` (line 684+), before `last_state_at_depth[depth] = state`, copy the old value:

```python
old = last_state_at_depth.get(depth)
if old is not None and old != state:
    prev_state_at_depth[depth] = old
last_state_at_depth[depth] = state
for k in [k for k in last_state_at_depth if k > depth]:
    del last_state_at_depth[k]
    prev_state_at_depth.pop(k, None)
```

Pass `prev_highlight=prev_state_at_depth.get(0)` into `_build_pinned_pane`, and inside `_build_pinned_pane._render_one` forward it as `prev_state` to `_render_neighborhood_diagram` (see Change 2 snippet above). For child FSMs in the stack, use `prev_state_at_depth.get(d + 1)`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — edit `_render_neighborhood_diagram` (signature at line 1653, the `_build_stack` closure at 1720-1727, the `edges = _collect_edges(fsm)` call at line 1674, and the `_make_box` helper at 1702 to accept `border_color`). Reuse existing `_filter_main_path_graph` helper at line 1506. Add a module-level `_PREV_STATE_COLOR = "33"` constant or inline it in the renderer.
- `scripts/little_loops/cli/loop/_helpers.py` —
  - In the streaming loop body (around line 633), introduce `prev_state_at_depth: dict[int, str] = {}` and update it on `state_enter` (line 684+) before overwriting `last_state_at_depth[depth]`. Also prune stale deeper entries alongside `last_state_at_depth`.
  - In `_build_pinned_pane` (line 243), add a `prev_highlight: str | None` parameter and a `child_prev_at_depth: dict[int, str]` parameter for the child stack (or pass the whole `prev_state_at_depth` dict).
  - In `_build_pinned_pane._render_one` (line 277-284), pass `mode=show_diagrams_mode` and `prev_state=prev_highlight` to the neighborhood call.
  - Update every `_build_pinned_pane(...)` call site (e.g. line 351-356) to forward the new prev-state arguments.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py:351` — `_render_pinned_pane`'s inner `_build(detail)` closure is the **only** external call site of `_build_pinned_pane`; it must be updated to forward `prev_highlight` and `mode` (already listed as `_helpers.py` in Files to Modify, but the specific call site is here)

### Tests
- `scripts/tests/test_ll_loop_display.py` — add four tests to `TestRenderNeighborhoodDiagram` (around line 3231, next to existing test at line 3208):
  - `test_single_succ_aligns_with_arrow_row_when_multiple_preds` — build a fan-in FSM (3+ preds, 1 succ); call `_render_neighborhood_diagram`; parse output and assert the single succ label appears on the same row as the active state label (the arrow row).
  - `test_main_mode_filters_on_error_preds` — small FSM where state `X` has `on_error: target`; render with `mode="main"` and assert `X` is NOT in output; contrast with `mode="full"` which should include it.
  - `test_prev_state_pred_gets_orange_border` — render with `prev_state="research_files"` and assert the row containing `research_files` is wrapped in `\033[33m` border escapes while sibling preds use the default plain border.
  - `test_prev_state_silently_skipped_when_not_in_preds` — pass `prev_state="some_state_not_in_preds"` and assert no orange ANSI escapes appear in the output (no crash, no fallback marker).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_display.py:TestDisplayProgressEvents.test_tall_fsm_falls_back_to_neighborhood` (line 2169) — exercises the full `run_foreground → _render_pinned_pane → _build_pinned_pane → _render_neighborhood_diagram` path; uses first-iteration events so `prev_state_at_depth.get(0)` will be `None` — should remain green but must be verified after `_build_pinned_pane` signature change
- `scripts/tests/test_ll_loop_display.py:TestDisplayProgressEvents.test_extreme_short_terminal_falls_back_to_single_line` (line 2206) — exercises the same pinned-pane path at extreme terminal height; same `prev_state=None` first-iteration reasoning; must be verified after Change 4

### Documentation
- N/A — internal renderer behavior change; no user-visible flag changes. The orange-border convention is self-explanatory in the rendered output.

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current source:_

- **All line numbers in this issue verified accurate** against `layout.py` and `_helpers.py` as of refinement, with one minor drift: `TestRenderNeighborhoodDiagram` actually begins at `scripts/tests/test_ll_loop_display.py:3205` (issue said 3208/3231), and `_render_pinned_pane`'s neighborhood call sites are at `_helpers.py:350-363` (issue said 351-356). The new tests should be added inside the existing class which already contains `test_renders_preds_active_succs` and `test_unknown_active_returns_empty` — both use plain substring checks (`assert "a" in out`) rather than row parsing, so the alignment and ANSI tests will be the first in the class to inspect structural output.

- **Precedent for Change 3's `border_color` parameter**: `_draw_box` at `layout.py:574` already establishes the "conditionally-colorize-every-border-character" pattern via a local `_bc(ch)` closure. The proposed `_make_box` extension can mirror that closure shape (`_bc = lambda ch: colorize(ch, border_color) if border_color else ch`) for consistency with the rest of the rendering layer.

- **Model for Change 2's main-mode dispatch**: `_helpers.py:286-299` (the existing `_render_one` "full" branch) is a cleaner template than the `layout.py:1564-1566` site because it adds a reachability fallback:
  ```python
  if mode == "main" and highlight is not None:
      _filtered_edges, reachable = _filter_main_path_graph(target, _collect_edges(target))
      if highlight not in reachable:
          mode = "full"
  ```
  Consider applying the same `highlight not in reachable → mode = "full"` fallback to the neighborhood call. Without it, requesting `mode="main"` for an active state that is only reachable via `on_error` would render an empty neighborhood (active state filtered out of `reachable`), which is worse than today's behavior. This was not explicitly called out in the original Change 2 proposal.

- **`prev_state_at_depth` convention**: `_helpers.py:633-634` already declares two `dict[int, X]` per-depth state dicts side-by-side (`last_state_at_depth` and `child_fsm_stack`). Adding `prev_state_at_depth: dict[int, str] = {}` next to them, and pruning it in lockstep with `last_state_at_depth` at line 693-694, matches the established convention exactly.

## Implementation Steps

1. Add `mode: str = "full"` and `prev_state: str | None = None` parameters to `_render_neighborhood_diagram` signature.
2. When `mode == "main"`, replace `_collect_edges(fsm)` at line 1674 with `_filter_main_path_graph(fsm, _collect_edges(fsm))[0]`.
3. Extend `_make_box` (line 1702) with a keyword-only `border_color: str | None = None` that colorizes the border (top/mid/bot pipes) without bolding the label like the active highlight does.
4. Rewrite the `_build_stack` closure (lines 1720-1727) to align the smaller stack to the arrow row via `start = max(0, min(center_idx, n_rows - len(labels)))`, and accept an optional `color_for: dict[str, str]` map for per-label border colors.
5. Build `pred_color_for` from `prev_state` (mapped through `_label(...)` so it matches the label used in the stack) and pass it only to the pred-side `_build_stack` call. Succ side gets no color map.
6. In `_helpers.py`, introduce `prev_state_at_depth` next to `last_state_at_depth`; copy the old value on `state_enter` before overwriting; prune deeper entries in lockstep.
7. Add `prev_highlight: str | None` (and child-depth prev mapping) to `_build_pinned_pane`; forward `prev_state` and `mode` to the neighborhood call in `_render_one`.
8. Update every `_build_pinned_pane(...)` call site (line 351-356 and any others) to pass `prev_highlight=prev_state_at_depth.get(0)`.
9. Add the four regression tests to `TestRenderNeighborhoodDiagram` in `test_ll_loop_display.py`.
10. Run `python -m pytest scripts/tests/test_ll_loop_display.py -v` and `python -m mypy scripts/little_loops/cli/loop/` to verify.

## Verification

1. Direct repro before/after fix:
   ```bash
   python -c "from pathlib import Path; import sys; sys.path.insert(0, 'scripts'); \
     from little_loops.fsm.validation import load_and_validate; \
     from little_loops.cli.loop.layout import _render_neighborhood_diagram; \
     fsm, _ = load_and_validate(Path('scripts/little_loops/loops/rn-refine.yaml')); \
     print(_render_neighborhood_diagram(fsm, 'synthesize', mode='main', prev_state='research_files'))"
   ```
   After the fix:
   - `score` is aligned with `synthesize` on the same row (the arrow row).
   - No `route_files`/`route_web` as preds.
   - `research_files` renders with orange (ANSI 33) border characters; `research_web` renders with the default plain border.

2. Same call with `mode="full"` should still include `route_files`/`route_web` (preserves existing detail when the user explicitly asks for full mode). The orange border still applies to whichever pred matches `prev_state`.

3. `prev_state=None` (or omitted) preserves today's behavior exactly — no pred is colored, byte-identical to pre-fix output apart from the alignment change.

4. End-to-end, with at least one completed transition so the runtime has a prev_state to surface:
   ```bash
   ll-loop run rn-refine path/to/some-plan.md --show-diagrams --clear
   ```
   After `research_files → synthesize`, the pinned pane shows `research_files` with an orange border, `synthesize` highlighted green, and `score` aligned with `synthesize` on the arrow row.

## Scope Boundaries

- Does **not** rewrite `_render_neighborhood_diagram` to draw per-pred branching arrows. The single-arrow visualization is a documented compact summary; only the alignment defect is in scope.
- Does **not** change `_render_fsm_diagram` or `_render_layered_diagram` — they render correctly already, and the previous-state marker is not added there in this issue (`_render_fsm_diagram` already conveys path via edge highlighting). A future enhancement can extend the orange-border convention to the full diagram if useful.
- Does **not** change the variant-selection logic (`_choose_pinned_layout`) — picking neighborhood over full when the full diagram doesn't fit is the intended fallback.
- Does **not** add a configuration knob for the prev-state color. The choice of ANSI 33 (orange/yellow) is fixed in this issue; if a knob is needed later it becomes a separate enhancement.
- Does **not** mark the previous state when it has been filtered out by `mode="main"` (e.g., reached via `on_error`). The orange border is silently omitted in that case rather than re-inserting the pred just to color it.

## Impact

- **Priority**: P3 — visible rendering defect in the pinned-pane fallback, but only affects the neighborhood view for loops with fan-in/fan-out asymmetry under `--show-diagrams --clear`. Diagram still conveys topology, just with a misleading arrow, off-path predecessors, and no marker for which pred just fired.
- **Effort**: Small-to-medium — three localized edits in `layout.py` (`_render_neighborhood_diagram` signature, `_build_stack`, `_make_box`), one new piece of runtime state plus parameter thread-through in `_helpers.py`, four regression tests.
- **Risk**: Low — `mode` defaults to `"full"` and `prev_state` defaults to `None` so existing callers/tests are unaffected; arrow-row-aligned `_build_stack` is byte-identical to today when `|preds| == |succs|`; the orange border is purely additive.
- **Breaking Change**: No

## Related Key Documentation

| Document | Description | Relevance |
|----------|-------------|-----------|
| [.issues/enhancements/P3-ENH-1642-handle-viewport-overflow-in-ll-loop-show-diagrams-clear.md](../enhancements/P3-ENH-1642-handle-viewport-overflow-in-ll-loop-show-diagrams-clear.md) | Parent enhancement that introduced `_render_neighborhood_diagram` and the pinned-pane fallback ladder | High |
| [docs/reference/CLI.md](../../docs/reference/CLI.md) | `--show-diagrams` / `--clear` flag reference | Medium |

## Labels

`bug`, `ll-loop`, `tui`, `rendering`, `captured`

## Status

**Open** | Created: 2026-05-23 | Priority: P3

## Session Log
- `/ll:wire-issue` - 2026-05-24T00:21:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f27164c8-4912-4ca8-a0c5-2f5e2455ff40.jsonl`
- `/ll:refine-issue` - 2026-05-24T00:15:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/39fbfb52-75b3-4f11-80a3-7cf258630615.jsonl`
- `/ll:format-issue` - 2026-05-23T23:56:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d1880bf-1a07-4c5c-960e-3a80cb77af53.jsonl`
- `/ll:capture-issue` - 2026-05-23T23:49:04Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/787b8c29-7b75-4828-8410-238863693d02.jsonl`
