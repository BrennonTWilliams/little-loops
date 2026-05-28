# FEAT-1763: Extract StateFeedRenderer from run_foreground() - Implementation Plan

## Issue Reference
- **File**: .issues/features/P3-FEAT-1763-ll-loop-monitor-extract-state-feed-renderer.md
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

Three closures inside `run_foreground()` (lines 741-1031 of `_helpers.py`) capture shared mutable state via closure scope:

- `_elapsed_str()` (line 741) — closure over `loop_start_time`
- `_redraw_pinned(state0)` (line 747) — closure over `facets`, iteration state, FSM state dicts
- `display_progress(event)` (line 767) — main event handler closure over all of the above

Shared mutable state (lines 732-737):
```python
current_iteration: list[int]       # [0] — list-box pattern for closure mutation
last_state_at_depth: dict[int, str]
prev_state_at_depth: dict[int, str]
child_fsm_stack: dict[int, FSMLoop | None]
pinned_height: list[int]           # [0]
loop_start_time: float
```

Module-level helpers (`_build_pinned_pane`, `_render_pinned_pane`, `_choose_pinned_layout`) and signal globals (`_needs_redraw`, `_using_alt_screen`, `_original_sigwinch`) remain unchanged.

### Key Discoveries
- `MockExecutor` in tests uses `_on_event` fallback (not `event_bus`), so both wiring paths must be preserved
- `display_progress` reads module-level `_needs_redraw` — this stays as a module global importable by `handle_event`

## Desired End State

`StateFeedRenderer` class in `_helpers.py` encapsulating the three closures as methods and shared state as instance variables. `run_foreground()` instantiates it and wires `renderer.handle_event` to the executor.

### How to Verify
- All existing tests pass without modification to call sites
- `test_state_feed_renderer.py` tests pass
- `StateFeedRenderer` importable from `little_loops.cli.loop._helpers`

## What We're NOT Doing
- Not changing `run_foreground()` public signature
- Not changing module-level functions (`_build_pinned_pane`, `_render_pinned_pane`, `_choose_pinned_layout`)
- Not changing module-level signal globals
- Not implementing `cmd_monitor` (FEAT-1764) — just making the renderer reusable

## Implementation Phases

### Phase 0: Write Tests — Red (TDD)

Write `scripts/tests/test_state_feed_renderer.py` with standalone unit tests. Tests instantiate `StateFeedRenderer` directly and call `renderer.handle_event(event_dict)`, asserting output via `capsys`.

Test cases:
- `test_handle_state_enter_basic` — state_enter event prints iteration line
- `test_handle_action_start_non_verbose` — action_start shows preview
- `test_handle_action_start_verbose` — action_start verbose shows full lines
- `test_handle_action_complete` — action_complete shows duration
- `test_handle_action_complete_timed_out` — exit_code 124 → "timed out"
- `test_handle_evaluate_yes` — yes verdict shows checkmark
- `test_handle_evaluate_no` — no verdict shows x-mark
- `test_handle_evaluate_error` — error verdict shows raw_preview
- `test_handle_route` — route event shows transition
- `test_handle_max_iterations_summary` — summary event
- `test_handle_stall_detected` — stall event
- `test_elapsed_str` — elapsed time formatting

These tests will FAIL (Red) because `StateFeedRenderer` doesn't exist yet.

### Phase 1: Define StateFeedRenderer class

Define `StateFeedRenderer` in `_helpers.py` between `_render_pinned_pane` (line ~449) and `get_builtin_loops_dir` (line ~452).

Constructor accepts: `fsm`, `args`, `highlight_color`, `edge_label_colors`, `badges`.

Methods:
- `_elapsed_str()` — was closure over `loop_start_time`
- `_redraw_pinned(state0)` — was closure over facets, iteration state
- `handle_event(event)` — was `display_progress`

### Phase 2: Update run_foreground()

Replace closure definitions and mutable state with `StateFeedRenderer` instantiation. Wire `renderer.handle_event` to executor.

### Phase 3: Update docs and test comments

Update:
- `docs/reference/OUTPUT_STYLING.md` line 237 — `display_progress()` → `StateFeedRenderer.handle_event`
- `test_cli_loop_lifecycle.py` — update comments referencing "display_progress"

## Testing Strategy

### Unit Tests (new)
- `test_state_feed_renderer.py` — standalone tests for StateFeedRenderer

### Regression Tests (existing)
- `test_ll_loop_display.py` — 30+ tests must pass unchanged
- `test_cli_loop_lifecycle.py` — test_resume_wires_display_callback_to_event_bus
- `test_cli_loop_background.py` — signal handler tests (module globals unchanged)
- `test_cli_loop_queue.py` — patches run_foreground via string
- `test_cli_loop_worktree.py` — patches run_foreground via string

## References
- Original issue: `.issues/features/P3-FEAT-1763-ll-loop-monitor-extract-state-feed-renderer.md`
- Primary extraction target: `_helpers.py:run_foreground()` (line 677)
- Related module-level helpers: `_build_pinned_pane` (line 272), `_render_pinned_pane` (line 371)
- Test patterns: `TestHandoffHandler` in `test_handoff_handler.py`
