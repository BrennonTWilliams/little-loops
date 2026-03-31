---
discovered_date: 2026-03-31
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
---

# ENH-899: `ll-loop status` Should Show Log File Details

## Summary

The `ll-loop status` command currently shows basic loop state (name, status, current state, iteration, timestamps, PID) but omits useful information available in the loop's log file (`.loops/.running/<name>.log`). Adding log file path, last modified time, and last event would give operators better situational awareness without needing to manually find and tail the log.

## Current Behavior

`ll-loop status <name>` outputs:

```
Loop: eval-refine-auto-cycle
Status: running
Current state: run_eval
Iteration: 7
Started: 2026-03-31T05:19:44.874437+00:00
Updated: 2026-03-31T12:24:26.122628+00:00
PID: 478566 (running)
```

No log file information is shown. Users must know the log path convention and manually inspect it.

## Expected Behavior

`ll-loop status <name>` should additionally show:

```
Log: .loops/.running/eval-refine-auto-cycle.log
Log updated: 3m ago
Last event: [STATE] run_eval → evaluating (iteration 7)
```

Specifically:
- **Log path**: Relative path to the log file
- **Log updated**: Human-readable time since the log file was last modified (e.g., "3m ago", "1h ago")
- **Last event**: The last meaningful log line (state transition, error, or status message)

## Motivation

When monitoring long-running loops, the current status output lacks the most actionable information: what the loop last did and how recently. Users frequently need to `tail` the log manually to check if a loop is stuck or progressing. Surfacing this in `status` saves a step and makes loop monitoring more self-service.

## Success Metrics

- **Log visibility**: `ll-loop status <name>` output includes log path, last modified time, and last event line when a log file exists
- **Graceful absence**: When no log file exists, output shows `Log: (not found)` without errors
- **Time readability**: Relative time format is human-readable (e.g., "3m ago", "1h 23m ago")

## API/Interface

New output fields appended to `ll-loop status` CLI output:

```
Log: .loops/.running/<name>.log
Log updated: <relative-time>
Last event: <last-meaningful-log-line>
```

No breaking changes — additive output only.

## Proposed Solution

In the `cmd_status` function in `scripts/little_loops/cli/loop/lifecycle.py:36-83`:

1. Derive the log file path from the loop name — `running_dir / f"{loop_name}.log"` — mirroring the existing PID file derivation at `lifecycle.py:53-55` and matching the convention in `_helpers.py:222`
2. If the log file exists:
   - Show its relative path (using `print(f"Log: {log_file}")` following the existing `Label: value` pattern)
   - Calculate time since last modification via `time.time() - log_file.stat().st_mtime` and format as "Xm ago" / "Xh Ym ago" / "Xd ago"
   - Read the last non-empty line via `splitlines()[-1]` and display as "Last event"
3. If the log file doesn't exist, show `Log: (not found)`
4. For JSON output (`args.json` branch at `lifecycle.py:57-61`), include `log_file`, `log_updated_ago`, and `last_event` keys

A new `_format_relative_time(seconds: float) -> str` helper is needed — no existing "X ago" formatter exists in the codebase. The three existing `_format_duration` functions (in `info.py:305`, `interpolation.py:262`, `logger.py:115`) format durations but not relative times.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/lifecycle.py:36-83` — `cmd_status` function (text output at lines 63-82, JSON output at lines 57-61)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:331` — dispatches `cmd_status(args.loop, loops_dir, logger, args)`
- No other callers — `cmd_status` is a CLI endpoint

### Similar Patterns
- `lifecycle.py:53-55` — PID file derivation (`running_dir / f"{loop_name}.pid"`) is the exact structural analog for log file derivation
- `_helpers.py:222` — log file path creation: `log_file = running_dir / f"{loop_name}.log"`
- `_helpers.py:328-332` — inline seconds-to-"Xm Ys" formatting pattern
- `_helpers.py:433-438` — `splitlines()[-N:]` tail pattern for reading last lines
- `session_log.py:82` — `f.stat().st_mtime` pattern for file modification time

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py:15-76` — primary `TestCmdStatus` class (mock `StatePersistence` + `patch("builtins.print")`)
- `scripts/tests/test_cli_loop_background.py:526-619` — `TestCmdStatusWithPid` (writes real PID file to `tmp_path` — closest structural analog for log file tests)
- `scripts/tests/test_ll_loop_commands.py:2007-2105` — `TestCmdStatusJson` (`capsys` + `patch.object` variant)

### Documentation
- N/A — additive CLI output change

### Configuration
- N/A

## Implementation Steps

1. **Add `_format_relative_time` helper** in `lifecycle.py` — takes seconds as float, returns strings like `"3m ago"`, `"1h 23m ago"`, `"2d ago"`. Follow the unit set from `text_utils.py:173` (`s`, `m`, `h`, `d`).
2. **Add log file info to `cmd_status` text output** at `lifecycle.py:63-82` — derive `log_file = running_dir / f"{loop_name}.log"` (parallel to PID derivation at line 53), then:
   - If exists: `print(f"Log: {log_file}")`, compute mtime age, `print(f"Log updated: {age}")`, read last non-empty line, `print(f"Last event: {last_line}")`
   - If not exists: `print("Log: (not found)")`
3. **Add log info to JSON output** at `lifecycle.py:57-61` — add `log_file`, `log_updated_ago`, `last_event` keys to the dict
4. **Add tests** in `test_cli_loop_lifecycle.py` following the `TestCmdStatusWithPid` pattern from `test_cli_loop_background.py:526` — write a real `.log` file to `tmp_path / ".running" / "test-loop.log"`, use `os.utime()` for mtime control, assert on print output
5. **Run `python -m pytest scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_cli_loop_background.py scripts/tests/test_ll_loop_commands.py -v`** to verify

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Location correction**: `cmd_status` is in `lifecycle.py:36-83`, NOT `info.py` as originally stated. `info.py` contains `cmd_list`, `cmd_show`, and `cmd_history`.
- **Log path convention**: `_helpers.py:222` creates log files as `running_dir / f"{loop_name}.log"` where `running_dir = loops_dir / ".running"`. The PID file at `lifecycle.py:53` follows the identical pattern — log derivation should mirror it.
- **No "ago" formatter exists**: Three `_format_duration` helpers exist (`info.py:305`, `interpolation.py:262`, `logger.py:115`) but all format durations, not relative times. A new `_format_relative_time` function is needed.
- **JSON output**: `cmd_status` has a `--json` flag (registered at `__init__.py:177`, handled at `lifecycle.py:57-61`) that serializes `state.to_dict()` — log info should be included here too.
- **Test infrastructure**: `test_cli_loop_background.py:526-619` (`TestCmdStatusWithPid`) writes real files to `tmp_path/.running/` and asserts on print output — this is the exact pattern to follow for log file tests.
- **File reading pattern**: `_helpers.py:433-438` uses `splitlines()[-N:]` for tailing output — apply same pattern for reading last log line.

## Impact

- **Priority**: P3 - Quality of life improvement for loop monitoring
- **Effort**: Small - Reads an existing file and appends a few output lines
- **Risk**: Low - Additive change to output, no breaking changes
- **Breaking Change**: No

## Scope Boundaries

- Only `ll-loop status` is in scope; `ll-loop list` and `ll-loop show` are not
- No changes to log file format or location
- No interactive/follow mode (that would be a separate feature)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-03-31T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16b71ea4-65ba-45df-b40c-1250b0bfb74b.jsonl`
- `/ll:refine-issue` - 2026-03-31T17:25:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16b71ea4-65ba-45df-b40c-1250b0bfb74b.jsonl`
- `/ll:format-issue` - 2026-03-31T17:21:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16b71ea4-65ba-45df-b40c-1250b0bfb74b.jsonl`
- `/ll:capture-issue` - 2026-03-31T12:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/705d8dcf-207a-4293-9698-d61e0449c1de.jsonl`

---

## Status

**Open** | Created: 2026-03-31 | Priority: P3
