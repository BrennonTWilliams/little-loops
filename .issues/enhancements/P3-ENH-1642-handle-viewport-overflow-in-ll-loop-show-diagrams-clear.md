---
captured_at: "2026-05-23T19:35:10Z"
discovered_date: 2026-05-23
discovered_by: capture-issue
relates_to:
  - BUG-989
  - ENH-1506
  - ENH-846
  - ENH-935
  - ENH-1641
---

# ENH-1642: Handle viewport overflow in `ll-loop run --show-diagrams --clear`

## Summary

When `ll-loop run --show-diagrams --clear` is active, the terminal is in the alternate screen buffer (entered by BUG-989's fix via `\033[?1049h`). On every `state_enter` event the screen is cleared and the FSM diagram is printed followed by streamed action output. The implementation handles terminal **width** (`shutil.get_terminal_size().columns`, label truncation, box-width clamping) but never measures terminal **height**. When one iteration's diagram + chrome + action output exceeds the viewport — common on a small terminal or a large FSM — output scrolls past the top of the alt-screen buffer and is **silently lost**: the alt-screen has no scrollback, so the user cannot recover the diagram once action output pushes it off-screen. The comment at `_helpers.py:563` acknowledges scrollback contamination but not this in-iteration overflow.

## Current Behavior

In alt-screen mode (`--show-diagrams --clear` on a TTY), each `state_enter` event clears the screen with `\033[2J\033[H` and re-renders the diagram + state line, then streams action output linearly below it. Output is bounded by the terminal width but not by the terminal height — when the combined diagram + action output exceeds the viewport, earlier lines (including the diagram itself) scroll off the top and are unrecoverable because the alt-screen buffer has no scrollback.

## Expected Behavior

The diagram stays visible for the whole iteration, and action output scrolls in a bounded pane beneath it. When the diagram itself does not fit, fall back to a compact one-hop neighborhood view of the active state. When even the neighborhood view will not fit, fall back to a single-line status (`fsm: <prev> → [<active>] → <succs>`). Behavior of `--show-diagrams` alone or `--clear` alone is unchanged (the main buffer already has native scrollback).

## Motivation

`--show-diagrams --clear` is the canonical interactive monitoring mode for FSM loops. For any non-trivial loop (e.g. anything in `loops/oracles/` or `refine-to-ready-issue`) the diagram routinely exceeds 30 rows. On a default 24-row terminal — or any terminal where the operator has other panes open — the current behavior silently loses both the diagram and the early action output, defeating the purpose of the flag. BUG-989 fixed scrollback contamination; this issue closes the in-iteration overflow gap left by that fix.

## Proposed Solution

Split the alt-screen into two regions using ANSI scroll regions:

- **Pinned pane** (top): header + FSM diagram + nested sub-loop diagrams + `[N/max] state` line + horizontal separator. Redrawn on every `state_enter` event.
- **Scroll region** (bottom): `action_start` / `action_output` / `action_complete` / `evaluate` / `route` output. Bounded by `\033[<top>;<bottom>r`; lines scroll within the region as they stream.

Only activated when `show_diagrams and clear and sys.stdout.isatty()`. All other code paths keep current behavior.

**Fallback ladder** for tall FSMs:

1. Full FSM diagram (existing `_render_fsm_diagram`)
2. If `D_total + chrome + MIN_ACTION_ROWS > rows`: 1-hop neighborhood view (new `_render_neighborhood_diagram`) — predecessors | active | successors
3. If still over budget: single-line status — `fsm: <prev_state> → [<active>] → <succs joined by ",">`

**Key escape sequences:**
- `\033[<top>;<bottom>r` — set scroll region (rows are 1-indexed, inclusive)
- `\033[r` — reset scroll region to full screen (must be emitted **before** `\033[?1049l` to avoid leaving the main buffer with a restricted scroll region)
- `\033[<row>;<col>H` — cursor positioning to drop into the scroll region after redrawing the pinned pane

**Reuse:** box-drawing primitives, badge/edge-color logic, and `_render_horizontal_simple` (currently at `layout.py:1614`) — the neighborhood renderer synthesizes a small subgraph and feeds it through a stripped-down version of the existing renderer.

## API/Interface

No new CLI flags. Behavior is automatic when `--show-diagrams --clear` is combined on a TTY. New internal helpers:

```python
# scripts/little_loops/cli/output.py
def terminal_size() -> tuple[int, int]:
    """Returns (cols, rows) from shutil.get_terminal_size((80, 24))."""

# scripts/little_loops/cli/loop/layout.py
def _render_neighborhood_diagram(
    fsm, active_state, *, edge_label_colors, badges,
) -> str:
    """Renders 1-hop predecessors | active | 1-hop successors. Bounded:
    max(len(preds), len(succs), 1) * (box_height + 1) — typically 3-10 rows."""

# scripts/little_loops/cli/loop/_helpers.py (extracted for testability)
def _choose_pinned_layout(
    fsm, child_stack, rows: int,
) -> tuple[str, int]:
    """Returns (diagram_str, pinned_height). Selects full / neighborhood /
    single-line fallback based on available rows. Pure helper — no I/O."""
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/output.py` — add `terminal_size()` helper returning `(cols, rows)`; keep existing `terminal_width()` as a thin wrapper
- `scripts/little_loops/cli/loop/layout.py` — add `_render_neighborhood_diagram(...)` next to existing `_render_fsm_diagram` and `_render_horizontal_simple`
- `scripts/little_loops/cli/loop/_helpers.py` — main change in `run_foreground` (lines ~334–589):
  - Replace `state_enter` (depth==0) block (lines ~383–440) with pinned-pane layout: reset scroll region → clear+home → measure → render parent FSM (with neighborhood/single-line fallback per `_choose_pinned_layout`) → render each sub-loop FSM with the same fallback ladder → emit horizontal separator → set scroll region `\033[<pinned+1>;<rows>r` → move cursor into scroll region
  - Track `pinned_height` in a closure variable so non-`state_enter` events do not redraw the pinned pane
  - Install a `SIGWINCH` handler (alongside SIGINT/SIGTERM at line ~118) that sets a module-level `_needs_redraw` flag; before each event in `display_progress`, if `_needs_redraw` is set, re-emit the pinned pane for `last_state_at_depth[0]` and reset the flag. Only install when alt-screen mode is active; uninstall in `finally`
  - Extend teardown (lines ~571–574): `print("\033[r", ...)` (reset scroll region) **before** `print("\033[?1049l", ...)` (exit alt-screen)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:211` — only foreground caller of `run_foreground()`; wraps it in `try/finally` for lock release (lines 149–220); the scroll-region teardown can ride in the existing alt-screen `finally`
- `scripts/little_loops/cli/loop/lifecycle.py:261` — `cmd_resume` calls `executor.resume()` directly, NOT `run_foreground()`; `--show-diagrams`/`--clear` on `resume` remain decorative for foreground resume (out of scope, but see existing gap noted in ENH-1506)

### Similar Patterns
- Existing module-level flag pattern: `_using_alt_screen` (added by BUG-989) — follow the exact same pattern for `_needs_redraw` (init at module scope, reset in test `setup_method`)
- Existing signal-handler pattern: `_loop_signal_handler` at `_helpers.py:35–82` — add SIGWINCH alongside SIGINT/SIGTERM with the same install-on-entry / restore-on-finally shape
- Existing width-measurement: `terminal_width()` at `output.py:16–18` — extend, do not duplicate

### Tests
- `scripts/tests/test_ll_loop_display.py` — primary target; follow `_make_args` + `MockExecutor` + `capsys` + `patch("sys.stdout.isatty")` pattern at lines 34–52, 1691–1724:
  - `test_state_enter_emits_scroll_region_when_alt_screen_active` — `_make_args(show_diagrams=True, clear=True)` + `isatty=True`; assert `\033[<N>;<M>r` appears in out after pinned pane
  - `test_scroll_region_reset_before_alt_screen_exit` — assert `\033[r` precedes `\033[?1049l` in teardown sequence
  - `test_tall_fsm_falls_back_to_neighborhood` — mock `shutil.get_terminal_size` to `(80, 12)` against a tall synthetic FSM; assert neighborhood renderer is called (or active state row count is bounded)
  - `test_extreme_short_terminal_falls_back_to_single_line` — mock `(80, 6)`; assert single-line status `fsm: ... → [...] → ...` appears
- `scripts/tests/cli/loop/test_layout.py` (new or existing) — unit test for `_render_neighborhood_diagram`:
  - Build a small synthetic FSM; assert row count ≤ a known bound; assert active state appears highlighted
- `scripts/tests/cli/loop/test_choose_pinned_layout.py` (new) — pure-function unit tests for the extracted decision helper at varying `rows` values; no executor required
- `scripts/tests/test_cli_loop_background.py:13–111` — add reset of new `_needs_redraw` global to `setup_method` (lines 23–33), alongside the existing `_using_alt_screen` reset
- `scripts/tests/test_cli_loop_lifecycle.py:460–475` — add reset of `_needs_redraw` to the manual reset block (lines 466–470)
- `scripts/tests/test_cli_loop_background.py` — add `test_sigwinch_handler_triggers_redraw_flag` to verify SIGWINCH handler sets `_needs_redraw` only when alt-screen is active

### Documentation
- `docs/reference/CLI.md:253–254,297–298` — `--clear` and `--show-diagrams` flag descriptions; note that on small terminals the FSM diagram falls back to a one-hop neighborhood view, then a single-line status
- `docs/guides/LOOPS_GUIDE.md:1298–1299,1443` — flag reference table and prose; mention viewport-aware pinned-pane layout
- `README.md:287–288` — example invocations described as "live in-place dashboard"; mention the pinned + scroll-region split

### Configuration
- N/A — no new config knobs. `MIN_ACTION_ROWS = 6` is a module-level constant in `_helpers.py`.

## Implementation Steps

1. Add `terminal_size()` to `output.py`; keep `terminal_width()` as a wrapper
2. Add `_render_neighborhood_diagram(fsm, active_state, ...)` to `layout.py`, reusing existing box-drawing/badge/edge-color primitives
3. Extract a pure helper `_choose_pinned_layout(fsm, child_stack, rows) -> (diagram_str, pinned_height)` in `_helpers.py` for testable fallback logic
4. Rewrite the `state_enter` (depth==0) branch in `run_foreground.display_progress` to compose the pinned pane and set the scroll region, calling `_choose_pinned_layout`
5. Add module-level `_needs_redraw` flag + SIGWINCH handler installed only when `_using_alt_screen` is True; honor flag at top of each event
6. Update teardown to reset scroll region (`\033[r`) **before** exiting alt-screen (`\033[?1049l`)
7. Add unit tests for `_render_neighborhood_diagram` and `_choose_pinned_layout`; add display tests for scroll-region emission, teardown ordering, neighborhood fallback, and single-line fallback
8. Update CLI/LOOPS_GUIDE/README docs to describe the pinned + scroll-region layout

## Impact

- **Priority**: P3 — UX-affecting; on default 24-row terminals the current behavior silently loses diagram + early action output for any non-trivial loop. Same tier as BUG-989 which fixed the predecessor scrollback issue.
- **Effort**: Medium — new neighborhood renderer + scroll-region orchestration + SIGWINCH handler; touches three files in `scripts/little_loops/cli/loop/` plus tests across three test modules. Reuses existing box-drawing and signal-handler patterns.
- **Risk**: Low — gated entirely behind `show_diagrams and clear and isatty()`; non-alt-screen paths unchanged. Scroll regions and SIGWINCH are standard xterm-compatible features. Teardown ordering (`\033[r` before `\033[?1049l`) avoids the only known failure mode (restricted scroll region leaking into main buffer).
- **Breaking Change**: No

## Scope Boundaries

- Does **not** add a `--no-pin` or `--layout=...` escape hatch; behavior is automatic. If user feedback warrants opt-out, file as a follow-up
- Does **not** restructure how action output is rendered or buffered — only changes where it lands (inside scroll region vs. directly to terminal)
- Does **not** address `cmd_resume` not calling `run_foreground()` (pre-existing gap from ENH-1506; tracked separately if needed)
- Does **not** introduce ncurses or a TUI framework dependency — raw ANSI only, matching existing codebase style
- Does **not** change behavior when `--show-diagrams` or `--clear` is used alone

## Success Metrics

- On a 15-row × 80-col terminal, running a tall-FSM loop with `--show-diagrams --clear` keeps the diagram (or neighborhood fallback, or single-line status) visible at the top across all iterations; no diagram lines scroll off the top of the alt-screen buffer
- On terminal resize (SIGWINCH), the layout redraws cleanly on the next event
- On SIGINT mid-iteration, the terminal returns to the user's shell with no leftover scroll region (verifiable: `seq 1 50` after exit produces normal scrollback)
- Existing `--show-diagrams`-only and `--clear`-only paths produce byte-identical output to the current implementation (regression test via golden output)

## Related Key Documentation

| Document | Description | Relevance |
|----------|-------------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | System design and technical decisions | Low |
| [docs/guides/LOOPS_GUIDE.md](../../docs/guides/LOOPS_GUIDE.md) | Loop runtime guide; documents `--show-diagrams`/`--clear` semantics | High |
| [docs/reference/CLI.md](../../docs/reference/CLI.md) | CLI flag reference | High |

## Labels

`enhancement`, `ll-loop`, `tui`, `ux`, `captured`

## Status

**Open** | Created: 2026-05-23 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-05-23T19:35:10Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1dcaab2-247a-402c-ac8c-78f94253581e.jsonl`
