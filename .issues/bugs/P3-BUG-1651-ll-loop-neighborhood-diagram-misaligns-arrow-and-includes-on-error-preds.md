---
captured_at: '2026-05-23T23:49:04Z'
discovered_date: 2026-05-23
discovered_by: capture-issue
relates_to:
- ENH-1642
---

# BUG-1651: `ll-loop --show-diagrams` neighborhood view misaligns succ arrow and includes on_error preds

## Summary

In the pinned-pane neighborhood fallback rendered by `_render_neighborhood_diagram` (`scripts/little_loops/cli/loop/layout.py:1653`), running `ll-loop run rn-refine ... --show-diagrams --clear` with `synthesize` active draws two visible defects: the `synthesize ──▶` arrow points into empty space because the single successor (`score`) is stacked at row 0 instead of next to the active state, and `route_files` / `route_web` show up as predecessors of `synthesize` even though they only connect via `on_error` — an off-happy-path edge that the renderer should suppress in `mode="main"`.

## Reproduction

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

Two independent defects in `_render_neighborhood_diagram` (`scripts/little_loops/cli/loop/layout.py:1653`):

**RC1 — Successor stack not vertically centered.** `n_rows = max(len(preds), len(succs), 1)` (line 1700) is dominated by whichever side has more items. The active state is placed at `center_idx = (n_rows - 1) // 2` (line 1732) so its name row sits at `active_line_offset = center_idx * 3 + 1` (line 1742). But `_build_stack` (lines 1720-1727) fills items top-down (`i in range(n_rows): if i < len(labels): box(i) else: blank`), so when `len(succs) < n_rows` the single succ ends up at index 0. The horizontal `──▶` is drawn once at `active_line_offset` on both sides, pointing into empty space whenever `|preds| ≠ |succs|`. For `synthesize`: 4 preds, 1 succ → `n_rows=4`, `center_idx=1`; active sits at rows 3-5, succ at rows 0-2, arrow at row 4 lands on nothing.

**RC2 — Neighborhood ignores `mode="main"` filter.** `_render_neighborhood_diagram` calls `_collect_edges(fsm)` directly (line 1674) and never consults the main-path filter (`_filter_main_path_graph` at `layout.py:1506`). Its caller `_build_pinned_pane._render_one` (`scripts/little_loops/cli/loop/_helpers.py:277-284`) also doesn't pass a `mode` parameter when the `"neighborhood"` variant is selected — only the `"full"` variant respects `show_diagrams_mode`. This pulls `route_files` and `route_web` into the predecessor stack via their `on_error: synthesize` edges. In main mode they should be filtered out, leaving just `research_files` and `research_web`.

RC2 alone fixes the visible bug for this specific case (2 preds + 1 succ has `center_idx=0`, succ at index 0 already matches), but RC1 still bites whenever `|preds| ≠ |succs|`, which is common.

## API/Interface

- `_render_neighborhood_diagram(...)` in `scripts/little_loops/cli/loop/layout.py:1653` gains a new keyword parameter `mode: str = "full"`. Default preserves existing callers and the test at `scripts/tests/test_ll_loop_display.py:3208`.
- No CLI-level changes.

## Fix

**Change 1 — center the smaller stack.** In `_render_neighborhood_diagram` (`scripts/little_loops/cli/loop/layout.py:1720-1727`), replace the top-down `_build_stack` with a centered variant:

```python
def _build_stack(labels: list[str], box_w: int) -> list[str]:
    rows: list[str] = []
    start = (n_rows - len(labels)) // 2  # center items in the n_rows slots
    for i in range(n_rows):
        j = i - start
        if 0 <= j < len(labels):
            rows.extend(_make_box(labels[j], box_w - 4, False))
        else:
            rows.extend([" " * box_w] * 3)
    return rows
```

For 1 succ in a 4-row layout: `start = (4-1)//2 = 1` → succ box renders at slot index 1 (rows 3-5), matching the active state at `center_idx = 1`. For symmetric cases (`start = 0`), behavior is identical to today.

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
    )
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — edit `_render_neighborhood_diagram` (signature at line 1653, the `_build_stack` closure at 1720-1727, and `edges = _collect_edges(fsm)` at line 1674). Reuse existing `_filter_main_path_graph` helper at line 1506
- `scripts/little_loops/cli/loop/_helpers.py:277-284` — pass `mode=show_diagrams_mode` in the `"neighborhood"` branch

### Tests
- `scripts/tests/test_ll_loop_display.py` — add two tests to `TestRenderNeighborhoodDiagram` (around line 3231, next to existing test at line 3208):
  - `test_single_succ_aligns_with_active_when_multiple_preds` — build a fan-in FSM (3+ preds, 1 succ); call `_render_neighborhood_diagram`; parse output and assert the single succ label appears on the same row as the active state label
  - `test_main_mode_filters_on_error_preds` — small FSM where state `X` has `on_error: target`; render with `mode="main"` and assert `X` is NOT in output; contrast with `mode="full"` which should include it

### Documentation
- N/A — internal renderer behavior change; no user-visible flag changes

## Implementation Steps

1. Add `mode: str = "full"` parameter to `_render_neighborhood_diagram` signature
2. Replace `_collect_edges(fsm)` at line 1674 with `_filter_main_path_graph(fsm, _collect_edges(fsm))[0]` when `mode == "main"`
3. Rewrite the `_build_stack` closure (lines 1720-1727) to center the smaller stack via `start = (n_rows - len(labels)) // 2`
4. In `_build_pinned_pane._render_one` (`_helpers.py:277-284`), pass `mode=show_diagrams_mode` to the neighborhood call
5. Add the two regression tests to `TestRenderNeighborhoodDiagram` in `test_ll_loop_display.py`
6. Run `python -m pytest scripts/tests/test_ll_loop_display.py -v` to verify

## Verification

1. Direct repro before/after fix:
   ```bash
   python -c "from pathlib import Path; import sys; sys.path.insert(0, 'scripts'); \
     from little_loops.fsm.validation import load_and_validate; \
     from little_loops.cli.loop.layout import _render_neighborhood_diagram; \
     fsm, _ = load_and_validate(Path('scripts/little_loops/loops/rn-refine.yaml')); \
     print(_render_neighborhood_diagram(fsm, 'synthesize', mode='main'))"
   ```
   After the fix: `score` aligned with `synthesize` on the same row, no `route_files`/`route_web` as preds.

2. Same call with `mode="full"` should still include `route_files`/`route_web` (preserves existing detail when the user explicitly asks for full mode).

3. End-to-end:
   ```bash
   ll-loop run rn-refine path/to/some-plan.md --show-diagrams --clear
   ```

## Scope Boundaries

- Does **not** rewrite `_render_neighborhood_diagram` to draw per-pred branching arrows. The single-arrow visualization is a documented compact summary; only the alignment defect is in scope.
- Does **not** change `_render_fsm_diagram` or `_render_layered_diagram` — they render correctly already.
- Does **not** change the variant-selection logic (`_choose_pinned_layout`) — picking neighborhood over full when the full diagram doesn't fit is the intended fallback.

## Impact

- **Priority**: P3 — visible rendering defect in the pinned-pane fallback, but only affects the neighborhood view for loops with fan-in/fan-out asymmetry under `--show-diagrams --clear`. Diagram still conveys topology, just with a misleading arrow and off-path predecessors.
- **Effort**: Small — two localized edits in `layout.py`, one parameter thread-through in `_helpers.py`, two regression tests.
- **Risk**: Low — `mode` defaults to `"full"` so existing callers/tests are unaffected; centered `_build_stack` is byte-identical to today when `|preds| == |succs|`.
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
- `/ll:capture-issue` - 2026-05-23T23:49:04Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/787b8c29-7b75-4828-8410-238863693d02.jsonl`
