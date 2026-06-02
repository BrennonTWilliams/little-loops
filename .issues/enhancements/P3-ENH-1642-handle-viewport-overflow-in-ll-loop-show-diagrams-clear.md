---
captured_at: '2026-05-23T19:35:10Z'
completed_at: '2026-05-23T23:24:44Z'
status: done
discovered_date: 2026-05-23
discovered_by: capture-issue
relates_to:
- BUG-989
- ENH-1506
- ENH-846
- ENH-935
- ENH-1641
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1642: Handle viewport overflow in `ll-loop run --show-diagrams --clear`

## Summary

When `ll-loop run --show-diagrams --clear` is active, the terminal is in the alternate screen buffer (entered by BUG-989's fix via `\033[?1049h` at `_helpers.py:629`). On every `state_enter` event the screen is cleared and the FSM diagram is printed followed by streamed action output. The implementation handles terminal **width** (`shutil.get_terminal_size().columns`, label truncation, box-width clamping) but never measures terminal **height**. When one iteration's diagram + chrome + action output exceeds the viewport — common on a small terminal or a large FSM — output scrolls past the top of the alt-screen buffer and is **silently lost**: the alt-screen has no scrollback, so the user cannot recover the diagram once action output pushes it off-screen. The comment at `_helpers.py:609–610` acknowledges scrollback contamination but not this in-iteration overflow.

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

**Reuse:** box-drawing primitives, badge/edge-color logic, and `_render_horizontal_simple` (at `layout.py:1653`) — the neighborhood renderer synthesizes a small subgraph and feeds it through a stripped-down version of the existing renderer. Verified helpers available for reuse: `_box_inner_lines` (`layout.py:150`), `_draw_box` (`layout.py:567`), `_render_layered_diagram` (`layout.py:675`), and `_render_fsm_diagram` (`layout.py:1534`).

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
- `scripts/little_loops/cli/output.py` — add `terminal_size()` helper returning `(cols, rows)`; keep existing `terminal_width()` (at `output.py:16`) as a thin wrapper. Current implementation passes `(default, 24)` to `shutil.get_terminal_size()` but ignores the rows value
- `scripts/little_loops/cli/loop/layout.py` — add `_render_neighborhood_diagram(...)` next to existing `_render_fsm_diagram` (`layout.py:1534`) and `_render_horizontal_simple` (`layout.py:1653`)
- `scripts/little_loops/cli/loop/_helpers.py` — main change in `run_foreground` (starts at `_helpers.py:336`, extends past line 660):
  - Replace `state_enter` branch (`if event_type == "state_enter":` at line 384, extending to ~line 488; clear-screen `\033[2J\033[H` at line 394; `_render_fsm_diagram` call at line 439) with pinned-pane layout: reset scroll region → clear+home → measure → render parent FSM (with neighborhood/single-line fallback per `_choose_pinned_layout`) → render each sub-loop FSM with the same fallback ladder → emit horizontal separator → set scroll region `\033[<pinned+1>;<rows>r` → move cursor into scroll region
  - `display_progress` (nested at `_helpers.py:376`) is a closure over `current_iteration`, `last_state_at_depth`, `child_fsm_stack`, `loop_start_time`, `quiet`, `verbose`, `show_diagrams`, `show_diagrams_mode` (tri-state `None`/`"main"`/`"full"` — relevant because pinned renderer should honor `verbose=(show_diagrams_mode == "full")`), `clear_screen`, plus `executor`/`fsm`/`highlight_color`/`edge_label_colors`/`badges` from the outer scope — track `pinned_height` in the same closure so non-`state_enter` events do not redraw the pinned pane
  - Install a `SIGWINCH` handler (alongside SIGINT/SIGTERM registration in `register_loop_signal_handlers` at `_helpers.py:119–120`) that sets a module-level `_needs_redraw` flag; before each event in `display_progress`, if `_needs_redraw` is set, re-emit the pinned pane for `last_state_at_depth[0]` and reset the flag. Only install when alt-screen mode is active; uninstall in `finally`. NOTE: no `SIGWINCH` reference exists anywhere in `scripts/` today — this is a net-new dependency on `signal.SIGWINCH`. **Pattern choice**: prefer the save/restore signal-handler pattern from `parallel/orchestrator.py:183–193` (`_setup_signal_handlers`/`_restore_signal_handlers` — stash previous handler, restore in `finally`) over the simpler no-restore pattern at `_helpers.py:104–120` (SIGINT/SIGTERM), because SIGWINCH is a session-level signal that could otherwise leak across multiple loop invocations within a single Python process (e.g. `cmd_next_loop` auto-advance via `cmd_run`)
  - Extend teardown (`finally:` at `_helpers.py:633`; current sequence: `print("\033[?1049l", ...)` at line 635, `_using_alt_screen = False` at line 636): emit `print("\033[r", ...)` (reset scroll region) **before** `print("\033[?1049l", ...)` to avoid leaving the main buffer with a restricted scroll region
  - **Forced-exit path also needs the same reset** (added by codebase research): `_loop_signal_handler` at `_helpers.py:53` already emits `\033[?1049l` to `sys.stderr` when `_using_alt_screen` is True on the second signal (force-quit path); this branch must also emit `\033[r` first, otherwise SIGINT mid-iteration leaves the user's shell with a restricted scroll region — which is one of the listed Success Metrics. Add a parallel `\033[r` emission to `sys.stderr` (gated on the same `_using_alt_screen` check) right before the existing `print("\033[?1049l", end="", file=sys.stderr, flush=True)`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:352` — only foreground caller of `run_foreground()`; wrapped in the `try:` block at line 289 with `lock_manager.release(...)` in `finally:` at lines 360–363; the scroll-region teardown stays inside `run_foreground`'s own `finally` and does not need changes here
- `scripts/little_loops/cli/loop/lifecycle.py:307` — `cmd_resume` (definition at line 307; `executor.resume()` at line 431, not line 418 as originally stated) calls the executor directly, NOT `run_foreground()`; `--show-diagrams`/`--clear` on `resume` remain decorative for foreground resume (out of scope, but see existing gap noted in ENH-1506)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/next_loop.py:318–319` — production caller in the auto-advance path; constructs an inline args namespace with `show_diagrams=None, clear=False` and calls `cmd_run(top_candidate.loop, run_args, loops_dir, logger)` at line 328 (which then calls `run_foreground()` internally — one level of indirection beyond the original claim). Args shape unchanged by this issue but listed as a `run_foreground` caller that must not break [Agent 1 finding]

### Similar Patterns
- Existing module-level flag block at `_helpers.py:35–38`:
  ```python
  _loop_shutdown_requested: bool = False
  _loop_executor: Any = None
  _loop_pid_file: Path | None = None
  _using_alt_screen: bool = False
  ```
  Add `_needs_redraw: bool = False` at line 39 and reset it in `setup_method`/`teardown_method` of `test_cli_loop_background.py:23–33` alongside the other four
- Existing signal-handler pattern: `_loop_signal_handler` at `_helpers.py:41` (body ends ~line 71) — declares `global _loop_shutdown_requested, _using_alt_screen` and on forced exit emits `\033[?1049l` to `sys.stderr` (line 53). The simple install-only pattern in `register_loop_signal_handlers` at `_helpers.py:104–120` (SIGINT/SIGTERM via plain `signal.signal(...)`, no restore) is sufficient for process-fatal signals but **not** for SIGWINCH — see `parallel/orchestrator.py:183–193` for the save-and-restore variant that stashes the previous handler in `self._original_sigint`/`_original_sigterm` and restores it in `finally`. Mirror that variant for SIGWINCH so a handler doesn't leak across multiple `run_foreground` invocations in the same Python process (e.g. `cmd_next_loop` auto-advance)
- Existing ANSI convention: SGR color sequences flow through `colorize()` at `output.py:97`, but cursor/screen control sequences (`\033[?1049h`, `\033[?1049l`, `\033[2J\033[H`) are emitted directly via `print("\033[...", end="", flush=True)` at `_helpers.py:394, 629, 635`. The new scroll-region sequences (`\033[<top>;<bottom>r`, `\033[r`) belong to the second class — emit them as bare `print()` literals, not via `colorize()`
- Existing fallback pattern in renderer: `_render_fsm_diagram` at `layout.py:1590–1609` already branches on topology+state-count to choose between `_render_horizontal_simple` (single-state path) and `_render_layered_diagram` (general path). The new `_choose_pinned_layout` three-tier ladder (full → neighborhood → single-line) should be stylistically consistent: a single function that computes a budget, then guards branches on that budget
- Existing width-measurement: `terminal_width()` at `output.py:16` — extend, do not duplicate. Every one of the 15+ existing callers across `scripts/little_loops/` assigns to `tw` or `width` and never unpacks rows; new `terminal_size()` callers should use a clear `(tw, th) = terminal_size()` form to avoid confusion. No height measurement exists anywhere in `scripts/little_loops/cli/loop/` today
- No `\033[r` (DECSTBM scroll region) or `SIGWINCH` references exist anywhere in `scripts/` — both are net-new ANSI/signal capabilities for this issue

### Tests
- `scripts/tests/test_ll_loop_display.py` — primary target. `MockExecutor` at lines 34–52. `_make_args` is a method on the `TestDisplayProgressEvents` class at line 1645 (note: it shims `show_diagrams=True` to `"main"` internally). Follow the existing `_make_args` + `MockExecutor` + `capsys` + `patch("sys.stdout.isatty", return_value=True)` pattern. Concrete model to mirror is `test_clear_flag_emits_ansi_clear_when_tty` around lines 2030–2134, which asserts substring presence and ordering (`out.index("\033[?1049h") < out.index("\033[2J\033[H")`). New tests:
  - `test_state_enter_emits_scroll_region_when_alt_screen_active` — `_make_args(show_diagrams=True, clear=True)` + `isatty=True`; assert `\033[<N>;<M>r` appears in out after pinned pane
  - `test_scroll_region_reset_before_alt_screen_exit` — assert `\033[r` precedes `\033[?1049l` in teardown sequence (use the same `out.index(...) < out.index(...)` pattern as the existing test)
  - `test_tall_fsm_falls_back_to_neighborhood` — mock `shutil.get_terminal_size` to `(80, 12)` against a tall synthetic FSM; assert neighborhood renderer is called (or active state row count is bounded)
  - `test_extreme_short_terminal_falls_back_to_single_line` — mock `(80, 6)`; assert single-line status `fsm: ... → [...] → ...` appears
- `scripts/tests/cli/loop/test_layout.py` (new or existing) — unit test for `_render_neighborhood_diagram`:
  - Build a small synthetic FSM; assert row count ≤ a known bound; assert active state appears highlighted
- `scripts/tests/cli/loop/test_choose_pinned_layout.py` (new) — pure-function unit tests for the extracted decision helper at varying `rows` values; no executor required
- `scripts/tests/test_cli_loop_background.py:23–33` — `setup_method` and `teardown_method` already reset `_loop_shutdown_requested`, `_loop_executor`, `_loop_pid_file`, and `_using_alt_screen` on `self.helpers`. Add a fifth reset for `_needs_redraw` to both methods
- `scripts/tests/test_cli_loop_lifecycle.py:580` — existing line `_h._using_alt_screen = False` is the manual reset point; add `_h._needs_redraw = False` alongside it (the previously claimed range 460–475 was incorrect; that region contains `test_resume_awaiting_continuation_prompt_shown`)
- `scripts/tests/test_cli_loop_background.py` — add `test_sigwinch_handler_triggers_redraw_flag` to verify SIGWINCH handler sets `_needs_redraw` only when alt-screen is active. Pattern reference: existing test at line 119 sets `self.helpers._using_alt_screen = True` to exercise the signal-handler exit path

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_output.py` → new `TestTerminalSize` class — follow the existing `TestTerminalWidth` pattern (`patch.object(shutil, "get_terminal_size", return_value=os.terminal_size((cols, rows)))`); assert that `terminal_size()` returns a `(cols, rows)` tuple where the rows component is the second element. The three existing `TestTerminalWidth` tests do not test the rows dimension; new class covers the gap [Agent 3 finding]
- `scripts/tests/test_ll_loop_display.py` → `TestDisplayProgressEvents.test_clear_flag_emits_ansi_clear_when_tty` (line 2030) — **will break**: asserts `"\033[2J\033[H" in out`; the new pinned-pane layout replaces the bare full-screen clear with scroll-region setup (`\033[<N>;<M>r` + cursor positioning) in the alt-screen path; update assertion to check for scroll-region sequence instead [Agent 2/3 finding]
- `scripts/tests/test_ll_loop_display.py` → `TestDisplayProgressEvents.test_show_diagrams_and_clear_enters_alt_screen` (line 2060) — **will break**: asserts `out.index("\033[?1049h") < out.index("\033[2J\033[H")`; same root cause; update to assert `\033[?1049h` precedes the scroll-region sequence `\033[<N>;<M>r` rather than `\033[2J\033[H` [Agent 2/3 finding]

### Documentation
- `docs/reference/CLI.md:253–254,297–298` — `--clear` and `--show-diagrams` flag descriptions; note that on small terminals the FSM diagram falls back to a one-hop neighborhood view, then a single-line status
- `docs/guides/LOOPS_GUIDE.md:1298–1299,1443` — flag reference table and prose; mention viewport-aware pinned-pane layout
- `README.md:287–288` — example invocations described as "live in-place dashboard"; mention the pinned + scroll-region split

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/OUTPUT_STYLING.md` — `### Terminal width` section (line 13) documents only `terminal_width()` and directs contributors to use it for all layout calculations (line 309 usage rule); update to also document `terminal_size()` and note when to prefer it (height-aware layout decisions) [Agent 2 finding]

### Configuration
- N/A — no new config knobs. `MIN_ACTION_ROWS = 6` is a module-level constant in `_helpers.py`.

## Implementation Steps

1. Add `terminal_size()` to `output.py`; keep `terminal_width()` as a wrapper
2. Add `_render_neighborhood_diagram(fsm, active_state, ...)` to `layout.py`, reusing existing box-drawing/badge/edge-color primitives
3. Extract a pure helper `_choose_pinned_layout(fsm, child_stack, rows) -> (diagram_str, pinned_height)` in `_helpers.py` for testable fallback logic
4. Rewrite the `state_enter` (depth==0) branch in `run_foreground.display_progress` to compose the pinned pane and set the scroll region, calling `_choose_pinned_layout`
5. Add module-level `_needs_redraw` flag + SIGWINCH handler installed only when `_using_alt_screen` is True; honor flag at top of each event
6. Update teardown to reset scroll region (`\033[r`) **before** exiting alt-screen (`\033[?1049l`) — apply in **both** the normal `finally:` path in `run_foreground` (`_helpers.py:633–636`) **and** the forced-exit branch in `_loop_signal_handler` (`_helpers.py:53`); without the signal-handler change, SIGINT mid-iteration leaves the user's shell with a restricted scroll region and fails the listed Success Metric
7. Add unit tests for `_render_neighborhood_diagram` and `_choose_pinned_layout`; add display tests for scroll-region emission, teardown ordering, neighborhood fallback, and single-line fallback
8. Update CLI/LOOPS_GUIDE/README docs to describe the pinned + scroll-region layout

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Create `scripts/tests/cli/loop/` directory with an empty `__init__.py` — this directory does not exist yet; `test_layout.py` and `test_choose_pinned_layout.py` (Steps 7) require it before they can be imported by pytest
10. Update `TestDisplayProgressEvents.test_clear_flag_emits_ansi_clear_when_tty` (`test_ll_loop_display.py:2030`) — replace `"\033[2J\033[H" in out` assertion with scroll-region equivalent; this test will fail with the new pinned-pane layout
11. Update `TestDisplayProgressEvents.test_show_diagrams_and_clear_enters_alt_screen` (`test_ll_loop_display.py:2060`) — replace `out.index("\033[2J\033[H")` ordering check with `\033[<N>;<M>r` scroll-region sequence; same failure mode as Step 10
12. Add `TestTerminalSize` class to `scripts/tests/test_cli_output.py` — tests for the new `terminal_size()` function following the `TestTerminalWidth` `patch.object(shutil, "get_terminal_size", ...)` pattern; assert `(cols, rows)` tuple shape
13. Update `docs/reference/OUTPUT_STYLING.md` `### Terminal width` section — add `terminal_size()` documentation and update the "Contributing" usage rule at line 309 to mention when to prefer `terminal_size()` over `terminal_width()`

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-23_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- Broad change surface (13 sites): while most changes are local or mechanical, the `_helpers.py` `state_enter` rewrite is a multi-function change adding a new closure variable (`pinned_height`), a module-level `_needs_redraw` flag, and a SIGWINCH handler sharing that state — plan for extra testing of the concurrent signal + event-loop path
- Two existing tests will break mid-implementation: `test_clear_flag_emits_ansi_clear_when_tty` (line 2030) and `test_show_diagrams_and_clear_enters_alt_screen` (line 2060) both assert `\033[2J\033[H` which the new pinned-pane layout replaces — update these in tandem with the `_helpers.py` changes to keep CI green
- New test subdirectory `scripts/tests/cli/loop/` must be created (Step 9) before pytest can discover `test_layout.py` and `test_choose_pinned_layout.py` — do this early to avoid silent test-skip during incremental development

## Session Log
- `/ll:manage-issue` - 2026-05-23T23:24:44Z - `d302e094-e886-4f1c-9e6a-9cb4dda50f7a.jsonl`
- `/ll:ready-issue` - 2026-05-23T23:01:41 - `92b102a9-99e9-4cdd-8526-0159e852073f.jsonl`
- `/ll:refine-issue` - 2026-05-23T22:43:55 - `0f15a5c6-3934-4aa0-9929-5919c5d54ab9.jsonl`
- `/ll:confidence-check` - 2026-05-23T00:00:00Z - `fb2aacf2-aaf0-4d77-a561-a081f97a838b.jsonl`
- `/ll:confidence-check` - 2026-05-23T00:00:01Z - `1a5569b1-158a-4faa-90cf-e467767979cc.jsonl`
- `/ll:wire-issue` - 2026-05-23T20:49:12 - `94688148-bcef-4c17-a138-b92c41a25e82.jsonl`
- `/ll:refine-issue` - 2026-05-23T20:37:47 - `dc466dbf-f3b4-404a-ac13-8482df50d3d6.jsonl`
- `/ll:format-issue` - 2026-05-23T19:40:39 - `00d572b0-3074-4df8-b905-4443cc9bb298.jsonl`
- `/ll:capture-issue` - 2026-05-23T19:35:10Z - `f1dcaab2-247a-402c-ac8c-78f94253581e.jsonl`
