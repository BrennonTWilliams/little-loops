---
id: FEAT-1764
title: 'll-loop monitor: implement cmd_monitor subcommand with state polling and log tail'
type: FEAT
status: open
priority: P3
parent: FEAT-1761
size: Large
captured_at: '2026-05-27T00:00:00Z'
discovered_date: '2026-05-27'
discovered_by: issue-size-review
testable: true
decision_needed: false
---

# FEAT-1764: `ll-loop monitor` — Implement `cmd_monitor` Subcommand

## Summary

Implement the `ll-loop monitor <loop_name>` subcommand that lets users attach the rich realtime visual display to an already-running background loop — FSM state diagrams, iteration progress, and log streaming — using the `StateFeedRenderer` extracted in FEAT-1763.

## Parent Issue

Decomposed from FEAT-1761: `ll-loop monitor` — Realtime Attach and Visualization for Background Loop Runs

## Prerequisite

**Depends on FEAT-1763** (StateFeedRenderer extraction must be merged first).

## Proposed Solution

### Step 2: Implement state-polling feed

In `cmd_monitor()` (add to `lifecycle.py`), use `_find_instances(loop_name, running_dir)` from `persistence.py` to locate `{loop_name}-*.state.json`; then enter a `while True:` poll loop comparing `state_file.stat().st_mtime != prev_mtime` to detect changes; load updated state via `LoopState.from_dict(json.loads(state_file.read_text()))` and pass to `StateFeedRenderer` — fallback polling interval is 100ms, matching `logs.py:_cmd_tail()`.

### Step 3: Add log-tail support

Mirror `scripts/little_loops/cli/logs.py:_cmd_tail()` to tail `{instance_id}.log`: `f.seek(0, 2)` then `f.readline()` loop with 100ms sleep; render below the diagram panel (or in the same scroll region). Respect `--log-file PATH` override flag.

### Step 4: Register `monitor` subcommand

In `scripts/little_loops/cli/loop/__init__.py:main_loop()`: add `"monitor"` to `known_subcommands`; register `monitor_parser = subparsers.add_parser("monitor", ...)` reusing `--show-diagrams` with `nargs="?"`, `const=True`, `type=_parse_show_diagrams` (same pattern as `run_parser`); add dispatch `elif args.command == "monitor": return cmd_monitor(...)`.

### Step 5: Wire Ctrl-C as detach

Use simple `try: ... except KeyboardInterrupt: return 0` (the `_cmd_tail` pattern from `logs.py`) — do NOT call `register_loop_signal_handlers()` (which would signal the loop process); the monitor does not own the background subprocess.

### Step 6: Handle non-running case

Check PID liveness via `_process_alive(pid)` from `persistence.py`; if dead, print last known state from `.state.json` and exit `0`; if `.state.json` absent, print helpful message and exit `1`.

### Step 7: Add tests in `scripts/tests/test_cli_loop_monitor.py`

Follow `TestTail` pattern from `test_ll_logs.py`: inject `readline.side_effect` and patch `time.sleep` to raise `KeyboardInterrupt`; follow `TestCmdStatus` pattern from `test_cli_loop_lifecycle.py` for mocking `_find_instances`. Cover: attach to running loop, Ctrl-C detach (returns 0), non-running case (no PID), loop-not-found case.

### Step 8 + 11: Update docs

- `docs/loops.md` — update `ll-loop` CLI reference with `monitor` subcommand
- `docs/guides/LOOPS_GUIDE.md` — add usage example for `ll-loop monitor`
- `docs/reference/CLI.md` — add `#### ll-loop monitor` section (matching existing `#### ll-loop status`, `#### ll-loop stop`, `#### ll-loop resume` headings) and add `ll-loop monitor <name>` to the examples block

### Step 10: Add `test_monitor_subcommand_registered`

Add to `scripts/tests/test_ll_loop_execution.py` alongside `test_simulate_subcommand_registered`: `patch.object(sys, "argv", ["ll-loop", "monitor", "--help"])` → `main_loop()` → assert `SystemExit(code=0)`.

## API / CLI Interface

```
ll-loop monitor <loop_name>                        # attach with default diagram mode
ll-loop monitor <loop_name> --show-diagrams ascii  # specify diagram mode
ll-loop monitor <loop_name> --no-clear             # stream without clearing screen
ll-loop monitor <loop_name> --log-file PATH        # override log file location
```

- Discovers the running loop via PID file at `.loops/.running/<loop_name>.pid`
- If not running, exits 0 with last known state (or exit 1 if no state file)
- Ctrl-C detaches without stopping the background loop
- On natural loop completion, exits with the loop's exit code

## Files to Modify

- `scripts/little_loops/cli/loop/lifecycle.py` — add `cmd_monitor()` alongside `cmd_status()`, `cmd_stop()`, `cmd_resume()`
- `scripts/little_loops/cli/loop/__init__.py` — register `monitor` subcommand, add dispatch

## New Files

- `scripts/little_loops/cli/loop/monitor.py` _(optional)_ — if `cmd_monitor()` grows large enough to warrant its own module
- `scripts/tests/test_cli_loop_monitor.py` — new test file: `TestCmdMonitor`

## Files Updated (docs + tests)

- `scripts/tests/test_ll_loop_execution.py` — add `test_monitor_subcommand_registered`
- `docs/loops.md` — `monitor` subcommand reference
- `docs/guides/LOOPS_GUIDE.md` — usage example
- `docs/reference/CLI.md` — `#### ll-loop monitor` section

## Similar Patterns to Follow

- `scripts/little_loops/cli/logs.py:_cmd_tail()` — polling tail loop pattern (100ms, KeyboardInterrupt detach)
- `scripts/little_loops/cli/loop/lifecycle.py:cmd_status()` — reads `_find_instances()` + `st_mtime` for change detection
- `scripts/tests/test_ll_logs.py:TestTail` — tail test pattern with injectable readline side_effect

## Acceptance Criteria

- [ ] `ll-loop monitor <name>` attaches to a running background loop and renders FSM state changes in realtime.
- [ ] `--show-diagrams [MODE]` works identically to the foreground run path.
- [ ] Ctrl-C detaches without stopping the loop; loop continues running in background.
- [ ] If the loop is not running, prints last known state from `.state.json` and exits 0.
- [ ] If `.state.json` is absent, prints helpful message and exits 1.
- [ ] On loop completion, monitor exits with the loop's exit code.
- [ ] `test_monitor_subcommand_registered` passes (exit 0 on `--help`).
- [ ] All `TestCmdMonitor` tests pass including Ctrl-C detach returning 0.
- [ ] Docs updated in all three locations (loops.md, LOOPS_GUIDE.md, CLI.md).

## Impact

- **Effort**: Medium — uses extracted renderer; new subcommand wiring, poll loop, and test coverage
- **Risk**: Low — monitor is read-only; Ctrl-C must not propagate to background loop process
- **Breaking Change**: No

## Status

**Open** | Created: 2026-05-27 | Priority: P3

## Session Log
- `/ll:issue-size-review` - 2026-05-27T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d019e6bc-bb14-4867-a8ae-4b748fc8e055.jsonl`
