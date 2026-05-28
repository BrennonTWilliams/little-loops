---
id: FEAT-1761
title: 'll-loop monitor: realtime attach and visualization for background loop runs'
type: FEAT
status: done
priority: P3
size: Very Large
captured_at: '2026-05-28T03:46:53Z'
discovered_date: '2026-05-28'
discovered_by: capture-issue
testable: true
decision_needed: false
confidence_score: 96
outcome_confidence: 71
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 21
score_change_surface: 18
---

# FEAT-1761: `ll-loop monitor` — Realtime Attach and Visualization for Background Loop Runs

## Summary

Add an `ll-loop monitor <loop_name>` subcommand (or `--attach` flag on `ll-loop run`) that lets users view the same rich realtime visual display — FSM state diagrams, iteration progress, log streaming — for a loop that is already running in background mode, matching the UX of foreground runs with `--clear` and `--show-diagrams [MODE]`.

## Motivation

`ll-loop run <loop> --clear --show-diagrams [MODE]` provides a rich TUI-like display for foreground runs: live FSM state diagrams rendered in the terminal, per-iteration status, color-coded transitions, and streaming logs. When a loop is started with `--background` (or detached via `&`), all of that visibility is lost — the user can only poll `.loops/.running/<loop>.state.json` or `tail` a log file manually. There is no first-class way to "attach" the visual layer to an already-running background process.

## Expected Behavior

```
ll-loop monitor <loop_name>          # attach and display with default diagram mode
ll-loop monitor <loop_name> --show-diagrams ascii
ll-loop monitor <loop_name> --no-clear   # stream without clearing screen
```

- Discovers the running loop via its PID file at `.loops/.running/<loop_name>.pid`.
- If the loop is not currently running, exits with a helpful message showing last known state.
- Attaches to the loop's state feed (file-watch on `.loops/.running/<loop_name>.state.json` + log tail) and renders the same display pipeline that `ll-loop run --clear --show-diagrams` uses.
- Supports all existing `--show-diagrams [MODE]` values (`ascii`, `unicode`, `mermaid`).
- Ctrl-C detaches the monitor without stopping the background loop (unlike foreground runs where Ctrl-C signals the loop itself).
- On natural loop completion, the monitor detects the terminal state and exits cleanly, printing the final summary.

## Current Behavior

Background loops can only be observed by manually reading `.loops/.running/<loop>.state.json`, tailing a log file, or running `ll-loop status <loop>` (which gives a one-shot snapshot, not realtime updates).

## Proposed Solution

- The display/rendering pipeline already exists in the foreground run path (likely `_display.py` or similar). Extract it behind an interface that accepts a state feed rather than being coupled to the running loop subprocess.
- State feed abstraction: a generator/iterator that yields `LoopState` snapshots — foreground runs push states directly; monitor mode polls `.state.json` with `inotify`/`FSEvents`/fallback polling (100ms interval).
- Log streaming: `ll-loop monitor` should tail the loop's log file if one exists (configurable via `--log-file`), rendering it in the same panel as the foreground run.
- Diagram rendering is already conditional on `--show-diagrams`; the monitor reuses this flag with the same default.
- PID file location: `.loops/.running/<loop_name>.pid` (already written by `run_background()`).
- State file location: `.loops/.running/<loop_name>.state.json` (already written on each state transition).

## API/Interface

New subcommand:
```
ll-loop monitor <loop_name> [--show-diagrams [MODE]] [--no-clear] [--log-file PATH]
```

Alternatively surfaced as a flag on `ll-loop status`:
```
ll-loop status <loop_name> --watch [--show-diagrams [MODE]]
```

Decision: prefer a dedicated `monitor` subcommand for discoverability; `status --watch` can be a documented alias.

## Use Case

**Who**: A developer running long `ll-loop` automation sessions on a codebase

**Context**: They start a loop with `--background` to keep the terminal free, then later want to observe its progress — FSM state transitions, current iteration, and live log output — without having to parse `.state.json` manually.

**Goal**: Attach the same rich visual display used by foreground `--clear --show-diagrams` runs to an already-running background process.

**Outcome**: Real-time FSM diagram and log stream appear in the terminal; Ctrl-C detaches without interrupting the loop; a clean final summary prints when the loop finishes naturally.

## Implementation Steps

1. **Extract display pipeline** — In `scripts/little_loops/cli/loop/_helpers.py`, extract `_build_pinned_pane()`, `_render_pinned_pane()`, and the `display_progress` callback out of `run_foreground()` into a `StateFeedRenderer` class or standalone helper so both foreground and monitor paths can call it with a `LoopState` snapshot

2. **Implement state-polling feed** — In `cmd_monitor()` (in `lifecycle.py`), use `_find_instances(loop_name, running_dir)` from `persistence.py` to locate `{loop_name}-*.state.json`; then enter a `while True:` poll loop comparing `state_file.stat().st_mtime != prev_mtime` to detect changes; load updated state via `LoopState.from_dict(json.loads(state_file.read_text()))` and pass to `StateFeedRenderer` — fallback polling interval is 100ms, matching `logs.py:_cmd_tail()`

3. **Add log-tail support** — Mirror `scripts/little_loops/cli/logs.py:_cmd_tail()` to tail `{instance_id}.log`: `f.seek(0, 2)` then `f.readline()` loop with 100ms sleep; render below the diagram panel (or in the same scroll region)

4. **Register `monitor` subcommand** — In `scripts/little_loops/cli/loop/__init__.py:main_loop()`: add `"monitor"` to `known_subcommands`; register `monitor_parser = subparsers.add_parser("monitor", ...)` reusing `--show-diagrams` with `nargs="?"`, `const=True`, `type=_parse_show_diagrams` (same pattern as `run_parser`); add dispatch `elif args.command == "monitor": return cmd_monitor(...)`

5. **Wire Ctrl-C as detach** — Use simple `try: ... except KeyboardInterrupt: return 0` (the `_cmd_tail` pattern from `logs.py`) — do NOT call `register_loop_signal_handlers()` (which would signal the loop process); the monitor does not own the background subprocess

6. **Handle non-running case** — Check PID liveness via `_process_alive(pid)` from `persistence.py`; if dead, print last known state from `.state.json` and exit `0`; if `.state.json` absent, print helpful message and exit `1`

7. **Add tests** in `scripts/tests/test_cli_loop_monitor.py` — Follow `TestTail` pattern from `test_ll_logs.py`: inject `readline.side_effect` and patch `time.sleep` to raise `KeyboardInterrupt`; follow `TestCmdStatus` pattern from `test_cli_loop_lifecycle.py` for mocking `_find_instances`

8. **Update docs** — Add `monitor` subcommand to `docs/loops.md` and `docs/guides/LOOPS_GUIDE.md` usage examples

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Preserve `run_foreground` signature** — When extracting `StateFeedRenderer`, ensure `run_foreground()` retains its existing public signature; `scripts/little_loops/cli/loop/run.py:cmd_run()` and `lifecycle.py:cmd_resume()` both import it directly — do NOT change the call sites unless changing the signature, and if the signature must change, update both callers
10. **Add `test_monitor_subcommand_registered`** to `scripts/tests/test_ll_loop_execution.py` — follow the `test_simulate_subcommand_registered` pattern: `patch.object(sys, "argv", ["ll-loop", "monitor", "--help"])` → `main_loop()` → assert `SystemExit(code=0)`
11. **Update `docs/reference/CLI.md`** — add `#### ll-loop monitor` section (matching existing `#### ll-loop status` / `#### ll-loop stop` heading structure) and add `ll-loop monitor <name>` to the examples block
12. **Verify `test_ll_loop_display.py` still passes** after `StateFeedRenderer` extraction — `TestDisplayProgressEvents` has 30+ `run_foreground()` call sites and 3 inline `_choose_pinned_layout` imports; keep these symbols importable at their current paths in `_helpers.py`
13. **Update `test_resume_wires_display_callback_to_event_bus`** if `display_progress` is renamed or attached via a new API during the `StateFeedRenderer` refactor

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — Extract `_build_pinned_pane()`, `_render_pinned_pane()`, and the `display_progress` callback out of `run_foreground()` into a reusable `StateFeedRenderer` interface; adapt Ctrl-C handling so monitor mode uses `KeyboardInterrupt` detach instead of signaling the loop process
- `scripts/little_loops/cli/loop/__init__.py:main_loop()` — Add `"monitor"` to `known_subcommands` set; register `monitor_parser = subparsers.add_parser("monitor", ...)` with `--show-diagrams`, `--no-clear`, `--log-file` flags; add `elif args.command == "monitor": return cmd_monitor(...)` dispatch branch
- `scripts/little_loops/cli/loop/lifecycle.py` — Add `cmd_monitor()` function alongside `cmd_status()`, `cmd_stop()`, `cmd_resume()`

### New Files
- `scripts/little_loops/cli/loop/monitor.py` _(optional)_ — if `cmd_monitor()` grows large enough to warrant its own module (import pattern matches existing siblings)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py:_find_instances()` — called by monitor to discover `{loop_name}-*.state.json` files in `.loops/.running/`; `LoopState.from_dict()` deserializes state snapshots
- `scripts/little_loops/fsm/persistence.py:StatePersistence` — `save_state()` writes state atomically; monitor reads these files
- `scripts/little_loops/cli/loop/layout.py:_render_fsm_diagram()` — primary diagram renderer; called with `highlight_state=current_state` from the extracted `StateFeedRenderer`
- `scripts/little_loops/cli/loop/layout.py:_render_neighborhood_diagram()` — compact 3-column layout used as fallback detail level
- `scripts/little_loops/cli/loop/layout.py:_render_pinned_pane()` — renders pinned header + diagram + state line; will be extracted into shared renderer
- `scripts/little_loops/cli/loop/diagram_modes.py:resolve_facets()` — converts `--show-diagrams` args to `DiagramFacets`; monitor reuses unchanged
- `scripts/little_loops/cli/loop/diagram_modes.py:_parse_show_diagrams()` — custom `type=` validator for `--show-diagrams`; monitor parser reuses same registration pattern

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py:cmd_run()` — top-level import `from little_loops.cli.loop._helpers import (..., run_foreground)`; if `run_foreground` signature changes during `StateFeedRenderer` extraction, this caller breaks — keep signature stable or update this site [Agent 1 finding]
- `scripts/little_loops/cli/loop/lifecycle.py:cmd_resume()` — deferred import `from little_loops.cli.loop._helpers import run_foreground` inside the function body; same breakage risk as `run.py` (already in Files to Modify, but this specific coupling is not noted in the extraction plan) [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/cli/logs.py:_cmd_tail()` — exact polling tail loop for background loops; uses `f.seek(0, 2)` + `f.readline()` + `time.sleep(0.1)` polling and `except KeyboardInterrupt: return 0` for clean detach — **the primary pattern for monitor's state and log file watching**
- `scripts/little_loops/cli/loop/_helpers.py:run_foreground()` — existing rendering pipeline to extract and reuse; `display_progress` callback is the central abstraction point
- `scripts/little_loops/cli/loop/lifecycle.py:cmd_status()` — reads `_find_instances()` + `log_file.stat().st_mtime` for change detection; monitor extends this to a continuous poll loop

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py` — existing `TestCmdStatus` pattern: mock `_find_instances` as the injectable seam; follow for `cmd_monitor` tests
- `scripts/tests/test_ll_logs.py:TestTail._mock_open_with_readline()` — tail test pattern: inject `readline.side_effect = [line, KeyboardInterrupt()]` and patch `time.sleep` to raise `KeyboardInterrupt` for termination
- `scripts/tests/test_cli_loop_background.py:TestLoopSignalHandler` — signal handler module-global reset pattern if needed
- NEW: `scripts/tests/test_cli_loop_monitor.py` — new test file: `TestCmdMonitor` with `_find_instances` mock seam, `st_mtime` change detection, and Ctrl-C detach returning `0`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_display.py` — **update risk**: imports `run_foreground` and `_choose_pinned_layout` at module level; `TestDisplayProgressEvents` has 30+ direct `run_foreground()` call sites; three test methods have inline `from little_loops.cli.loop._helpers import _choose_pinned_layout` imports — if `run_foreground` signature changes or `_choose_pinned_layout` moves into `StateFeedRenderer`, these imports and call sites break; keep `run_foreground` signature stable and keep `_choose_pinned_layout` importable from `_helpers` [Agent 2 finding]
- `scripts/tests/test_ll_loop_execution.py` — **new test needed**: add `test_monitor_subcommand_registered` alongside existing `test_simulate_subcommand_registered` siblings, following the `patch.object(sys, "argv", ["ll-loop", "monitor", "--help"])` → `main_loop()` → `SystemExit(0)` pattern [Agent 3 finding]
- `scripts/tests/test_cli_loop_lifecycle.py:TestCmdResumeBackground.test_resume_wires_display_callback_to_event_bus` — **may break**: asserts that `display_progress` is registered on `executor.event_bus`; if the callback is renamed (e.g., `StateFeedRenderer.on_event`) or attached via a different API (e.g., `renderer.attach(executor.event_bus)` vs. direct `register()`), this assertion target must be updated [Agent 3 finding]

### Documentation
- `docs/loops.md` — update `ll-loop` CLI reference with `monitor` subcommand
- `docs/guides/LOOPS_GUIDE.md` — add usage example for `ll-loop monitor`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — exhaustive `####`-headed subcommand listing for `ll-loop`; needs a new `#### ll-loop monitor` section (matching existing `#### ll-loop status`, `#### ll-loop stop`, `#### ll-loop resume` headings) and an `ll-loop monitor <name>` entry in the examples block [Agent 2 finding]

### Configuration
- N/A — state file paths follow existing conventions: `.loops/.running/{instance_id}.state.json`, `.loops/.running/{instance_id}.pid`, `.loops/.running/{instance_id}.log`

## Acceptance Criteria

- [ ] `ll-loop monitor <name>` attaches to a running background loop and renders FSM state changes in realtime.
- [ ] `--show-diagrams [MODE]` works identically to the foreground run path.
- [ ] Ctrl-C detaches without stopping the loop; loop continues running in background.
- [ ] If the loop is not running, prints last known state from `.state.json` and exits 0.
- [ ] On loop completion, monitor exits with the loop's exit code.
- [ ] Works on macOS (FSEvents or polling) and Linux (inotify or polling).

## Impact

- **Priority**: P3 — Quality-of-life improvement; background loops are functional, this adds live observability
- **Effort**: Medium — Display rendering pipeline exists; requires abstraction layer, new subcommand, and Ctrl-C signal handling
- **Risk**: Low — Monitor is read-only; main risk is Ctrl-C handling (must not propagate signal to the background loop process)
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-loop`, `ux`, `observability`

## Related Issues

- FEAT-1232: `ll-loop parallel` subcommand (deferred) — background group launcher
- FEAT-047: `ll-loop` CLI tool (core runner)

## Status

**Open** | Created: 2026-05-28 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-27_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- Extraction complexity: `display_progress` closure at `_helpers.py:767` is the primary refactor target; 30+ `run_foreground()` call sites in `test_ll_loop_display.py` will catch regressions, but any signature change has broad test impact — keep `run_foreground` signature stable throughout
- Implementation style open: `StateFeedRenderer` as a class vs standalone helpers is unspecified; choose based on how much state needs to share across poll iterations — if `display_progress` is the only shared state, a thin wrapper class suffices

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-27
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- FEAT-1763: `ll-loop monitor` — Extract StateFeedRenderer from `run_foreground()`
- FEAT-1764: `ll-loop monitor` — Implement `cmd_monitor` subcommand with state polling and log tail

## Session Log
- `/ll:issue-size-review` - 2026-05-27T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d019e6bc-bb14-4867-a8ae-4b748fc8e055.jsonl`
- `/ll:confidence-check` - 2026-05-27T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad4714ef-b93d-4988-81dd-ef19e6fce315.jsonl`
- `/ll:wire-issue` - 2026-05-28T04:10:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe8ebcef-7f9f-46d0-8e30-6d14cdc93e1d.jsonl`
- `/ll:refine-issue` - 2026-05-28T04:04:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e4c4580-ff53-491f-b559-91a0d8e16e9f.jsonl`
- `/ll:format-issue` - 2026-05-28T03:58:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34d7caed-10b0-415b-91c0-c8c95443f1f9.jsonl`
- `/ll:capture-issue` - 2026-05-28T03:46:53Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2bcb218-a171-4a8f-92ee-aeaf8000e6a2.jsonl`
