---
id: FEAT-1763
title: 'll-loop monitor: extract StateFeedRenderer from run_foreground()'
type: FEAT
status: open
priority: P3
parent: FEAT-1761
size: Medium
captured_at: '2026-05-27T00:00:00Z'
discovered_date: '2026-05-27'
discovered_by: issue-size-review
testable: true
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1763: `ll-loop monitor` — Extract StateFeedRenderer from `run_foreground()`

## Summary

Extract the display/rendering pipeline from `run_foreground()` in `_helpers.py` into a reusable `StateFeedRenderer` class or standalone helpers so both the foreground run path and the new `cmd_monitor` path can share the same rendering logic.

## Parent Issue

Decomposed from FEAT-1761: `ll-loop monitor` — Realtime Attach and Visualization for Background Loop Runs

## Use Case

A developer implementing `cmd_monitor` (FEAT-1764) needs to render live loop-state updates in a terminal when attaching to a background run. They instantiate `StateFeedRenderer(fsm, args, ...)` and call `renderer.handle_event(event)` from the monitor's polling loop, reusing the same rendering logic as `run_foreground()` without duplicating the closures or their shared mutable state.

## Current Behavior

The rendering pipeline — `_elapsed_str`, `_redraw_pinned`, and `display_progress` — exists as three closures with shared mutable state inside `run_foreground()` in `_helpers.py`. This makes the display logic inaccessible to any code path other than the foreground run, preventing reuse in the new `cmd_monitor` attach path.

## Expected Behavior

The closures and their shared mutable state are extracted into a `StateFeedRenderer` class defined in `_helpers.py`. `run_foreground()` instantiates `StateFeedRenderer` and wires `renderer.handle_event` to the executor, preserving its existing public signature. All existing callers and tests continue to work without modification.

## Proposed Solution

Perform a pure refactoring extraction with no behavior change:

1. **Extract display pipeline** — In `scripts/little_loops/cli/loop/_helpers.py`, extract `_build_pinned_pane()`, `_render_pinned_pane()`, and the `display_progress` callback out of `run_foreground()` into a `StateFeedRenderer` class or standalone helper. The interface should accept a `LoopState` snapshot so both foreground and monitor paths can call it.

2. **Preserve `run_foreground` signature** — Ensure `run_foreground()` retains its existing public signature throughout the extraction. `scripts/little_loops/cli/loop/run.py:cmd_run()` and `lifecycle.py:cmd_resume()` both import it directly — do NOT change the call sites unless the signature truly must change, and if it does, update both callers.

3. **Verify `test_ll_loop_display.py` still passes** — `TestDisplayProgressEvents` has 30+ `run_foreground()` call sites and 3 inline `_choose_pinned_layout` imports; keep `run_foreground` and `_choose_pinned_layout` importable at their current paths in `_helpers.py`.

4. **Update `test_resume_wires_display_callback_to_event_bus`** if `display_progress` is renamed or attached via a new API during the `StateFeedRenderer` refactor — this test in `test_cli_loop_lifecycle.py` asserts that `display_progress` is registered on `executor.event_bus`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical correction to step 1**: `_build_pinned_pane()` (line 272), `_render_pinned_pane()` (line 371), and `_choose_pinned_layout()` (line 234) are **already module-level functions** in `_helpers.py` — they are NOT inside `run_foreground()`. The actual extraction target is the three **closures defined inside `run_foreground()`** and their shared mutable state:

- `_elapsed_str()` — closure over `loop_start_time`
- `_redraw_pinned(state0)` — closure over `facets`, iteration state, FSM state dicts
- `display_progress(event)` — the main event handler closure over all of the above

These become methods of `StateFeedRenderer`. The mutable closure-captured state variables become instance variables:

```python
current_iteration: list[int]       # [0] — list-box pattern for closure mutation
last_state_at_depth: dict[int, str]
prev_state_at_depth: dict[int, str]
child_fsm_stack: dict[int, FSMLoop | None]
pinned_height: list[int]           # [0]
loop_start_time: float
```

**`display_progress` event wiring** (lines 1033–1038 of `_helpers.py`): Two wiring paths must be preserved:
```python
if hasattr(executor, "event_bus"):
    executor.event_bus.register(display_progress)  # primary: PersistentExecutor
else:
    executor._on_event = display_progress           # fallback: MockExecutor in tests
```
`MockExecutor` in `test_ll_loop_display.py:34` exposes `_on_event`, not `event_bus` — the fallback path must remain.

**`test_resume_wires_display_callback_to_event_bus` assertion** (line 573 in `test_cli_loop_lifecycle.py`): Checks `mock_exec_cls.return_value.event_bus.register.call_count >= 1` — does NOT assert on which callable was registered. Safe to rename `display_progress` to `renderer.handle_event` as long as at least one `event_bus.register()` call still happens.

**`run_foreground()` exact signature** (line 677):
```python
def run_foreground(
    executor: Any,
    fsm: FSMLoop,
    args: argparse.Namespace,
    highlight_color: str = "32",
    edge_label_colors: dict[str, str] | None = None,
    badges: dict[str, str] | None = None,
    mode: str = "run",
    instance_id: str | None = None,
    running_dir: Path | None = None,
) -> int:
```

**`StateFeedRenderer` constructor arguments**: Should accept `fsm: FSMLoop`, `args: argparse.Namespace`, `highlight_color: str`, `edge_label_colors: dict[str, str] | None`, `badges: dict[str, str] | None` — mirroring what `run_foreground` currently reads from its params to set up closures. `resolve_facets(args)` and `in_pinned_mode` derivation happen in `__init__`.

**Two `state_enter` rendering code paths**: Pinned mode calls `_redraw_pinned()` → `_render_pinned_pane()` → `_build_pinned_pane()`. Non-pinned show_diagrams mode duplicates the sub-loop resolution + breadcrumb header inline, calling `_render_fsm_diagram()` directly. Both paths should be preserved as methods.

**Module-level signal globals**: `_needs_redraw`, `_using_alt_screen`, `_original_sigwinch` are module-level — keep them module-level (signal handlers can't easily be instance-scoped); `display_progress`/`handle_event` can continue to read `_needs_redraw` as a module global.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — primary extraction target; define `StateFeedRenderer` class here alongside the existing module-level helpers; `run_foreground()` instantiates it and wires `renderer.handle_event` to `executor.event_bus`

### Dependent Files (Callers of `run_foreground`)
- `scripts/little_loops/cli/loop/run.py:cmd_run()` — imports `run_foreground`; passes `mode="run"` (default); no signature change expected
- `scripts/little_loops/cli/loop/lifecycle.py:cmd_resume()` — imports `run_foreground`; passes `mode="resume"` explicitly; no signature change expected

### Tests
- `scripts/tests/test_ll_loop_display.py` — `TestDisplayProgressEvents` (line 1645): 30+ `run_foreground()` call sites with `MockExecutor` (uses `_on_event` fallback); `TestChoosePinnedLayout` (line 3737): 3 imports of `_choose_pinned_layout` from `little_loops.cli.loop._helpers` — must stay importable
- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdResume.test_resume_wires_display_callback_to_event_bus` (line 539): asserts `event_bus.register.call_count >= 1` only; no specific callable check

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_background.py` — `TestLoopSignalHandler`: directly reads/writes `_needs_redraw`, `_using_alt_screen`, `_loop_shutdown_requested` module globals in `setup_method`/`teardown_method`; verify all pass (these globals remain module-level per issue spec)
- `scripts/tests/test_cli_loop_queue.py` — patches `little_loops.cli.loop.run.run_foreground` via string; unaffected by extraction, verify still passes
- `scripts/tests/test_cli_loop_worktree.py` — patches `little_loops.cli.loop.run.run_foreground` via string; unaffected, verify still passes
- `scripts/tests/test_state_feed_renderer.py` — **new file to create**: standalone unit tests for `StateFeedRenderer`; instantiate directly and call `renderer.handle_event(event_dict)` with `capsys` assertions; follow `TestHandoffHandler` pattern in `scripts/tests/test_handoff_handler.py` combined with event-dict inputs from `TestDisplayProgressEvents`

### Similar Patterns / Infrastructure
- `scripts/little_loops/events.py:EventBus.register()` (line 81) — `callback: Callable[[dict[str, Any]], None]`; optional `filter` arg; registration is append-only
- `scripts/little_loops/cli/loop/diagram_modes.py:DiagramFacets` — frozen dataclass consumed by `StateFeedRenderer`; created via `resolve_facets(args)`
- `scripts/little_loops/cli/loop/layout.py` — `_render_fsm_diagram()`, `_render_neighborhood_diagram()` called by `_build_pinned_pane()`
- `scripts/little_loops/fsm/persistence.py:LoopState` — snapshot dataclass; `current_state`, `iteration`, `status` consumed by `cmd_resume()` before calling `run_foreground()`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/OUTPUT_STYLING.md` — line 237, "Edge label colors" note: `"The ✓/✗ verdict symbol colors in display_progress() ..."` — update prose to reference `StateFeedRenderer.handle_event` after rename
- `docs/development/loop-diagram-show-only-deepest.md` — lines 18 and 67 reference `display_progress` inside `run_foreground` as "Site 2"; cosmetic/low-priority staleness after rename

### Future Consumer (FEAT-1764)
- `scripts/little_loops/cli/loop/lifecycle.py:cmd_monitor()` — will instantiate `StateFeedRenderer` directly with a `LoopState` snapshot from a polling loop

## Files to Modify

- `scripts/little_loops/cli/loop/_helpers.py` — primary extraction target
- `scripts/tests/test_ll_loop_display.py` — verify imports remain valid (no call-site changes expected)
- `scripts/tests/test_cli_loop_lifecycle.py` — update `test_resume_wires_display_callback_to_event_bus` if `display_progress` reference changes
- `docs/reference/OUTPUT_STYLING.md` — update "Edge label colors" prose (line 237) to reference `StateFeedRenderer.handle_event` instead of `display_progress()` [Wiring pass]
- `scripts/tests/test_state_feed_renderer.py` — new file: standalone unit tests for `StateFeedRenderer` [Wiring pass]

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/OUTPUT_STYLING.md` — line 237 "Edge label colors" prose names `display_progress()` by name; update to `StateFeedRenderer.handle_event` after rename
6. Update docstring/comment in `test_cli_loop_lifecycle.py:TestCmdResume.test_resume_wires_display_callback_to_event_bus` — lines 540, 544, 572 reference "display_progress" and "display closure" in comments; update to `renderer.handle_event` (runtime assertion `call_count >= 1` already passes without change)
7. Create `scripts/tests/test_state_feed_renderer.py` — standalone unit tests for `StateFeedRenderer` class: instantiate directly, call `renderer.handle_event(event_dict)`, assert `capsys` output; follow `TestHandoffHandler` pattern in `scripts/tests/test_handoff_handler.py` combined with event-dict inputs from `TestDisplayProgressEvents`

## Acceptance Criteria

- [ ] `StateFeedRenderer` (class or helpers) is extracted and callable with a `LoopState` snapshot.
- [ ] `run_foreground()` signature is unchanged; all existing callers pass without modification.
- [ ] `_choose_pinned_layout` remains importable from `_helpers.py`.
- [ ] All existing tests in `test_ll_loop_display.py` pass with no changes to call sites.
- [ ] `test_resume_wires_display_callback_to_event_bus` passes.

## Impact

- **Effort**: Small — pure refactor within one file; no new behavior
- **Risk**: Low — existing tests act as a comprehensive regression net (30+ call sites in test_ll_loop_display.py)
- **Breaking Change**: No

## Labels

`refactoring`, `cli`, `loop`

## Status

**Open** | Created: 2026-05-27 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-28T04:31:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e097599-5bb8-4042-b028-dbcf64320294.jsonl`
- `/ll:wire-issue` - 2026-05-28T04:27:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/90f38bbf-f167-4cba-bdb4-9006604ff987.jsonl`
- `/ll:refine-issue` - 2026-05-28T04:20:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/41d3cbb1-7199-4507-ba24-2665bb6a3ff3.jsonl`
- `/ll:issue-size-review` - 2026-05-27T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d019e6bc-bb14-4867-a8ae-4b748fc8e055.jsonl`
