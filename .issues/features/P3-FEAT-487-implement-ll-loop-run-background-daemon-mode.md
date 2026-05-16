---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
confidence_score: 98
outcome_confidence: 71
---

# FEAT-487: Implement `ll-loop run --background` daemon mode

## Summary

The `--background` / `-b` flag is wired into the `ll-loop run` CLI parser with help text `"Run as daemon (not yet implemented)"`. When passed, it emits a warning and falls through to foreground execution. The daemon/background execution path has no implementation.

## Current Behavior

```python
# cli/loop/__init__.py:89
run_parser.add_argument(
    "--background", "-b", action="store_true", help="Run as daemon (not yet implemented)"
)

# cli/loop/run.py:63-65
if getattr(args, "background", False):
    logger.warning("Background mode not yet implemented, running in foreground")
```

## Expected Behavior

When `--background` is passed, the loop process detaches from the terminal, writes a PID file for management, redirects stdout/stderr to a log file, and continues execution as a daemon. Status can be checked via `ll-loop status`.

## Motivation

Long-running loops (e.g., continuous scan-and-fix loops) benefit from background execution so users can continue other work in the terminal. The flag is already declared in the CLI, so users expect it to work.

## Use Case

A developer starts a long-running scan loop: `ll-loop run continuous-scan --background`. The process detaches, writing its PID to `.loops/.running/continuous-scan.pid`. The developer checks status with `ll-loop status continuous-scan` and stops it with `ll-loop stop continuous-scan`.

## Prior Art

This feature was previously filed as FEAT-255 and FEAT-431, both closed as Won't Fix:
- **FEAT-255**: "YAGNI / over-engineered. Users already have nohup, &, screen, and tmux."
- **FEAT-431**: "Reinvents solved problems at high maintenance cost. os.fork() is Unix-only. PID files, signal handling, zombie cleanup is a deep maintenance rabbit hole."

**Why proceeding**: The `--background` flag is publicly exposed in CLI help text. Either implement it or remove it — leaving a broken flag degrades user trust. The implementation should be minimal and leverage existing patterns (lock file PID tracking, signal handling from sprint runner).

## Acceptance Criteria

- [x] `ll-loop run <name> --background` detaches the process from the terminal
- [x] PID file written to `.loops/.running/<name>.pid` (follows existing `.running/` convention)
- [x] stdout/stderr redirected to `.loops/.running/<name>.log`
- [x] `ll-loop status` shows running background loops with PID and liveness check
- [x] `ll-loop stop <name>` sends SIGTERM to the background process via PID file
- [x] SIGTERM handler registered in loop CLI that calls `executor.request_shutdown()` (currently missing — see Signal Handling Gap below)
- [x] PID file cleaned up on exit (both normal and signal-based)

## Proposed Solution

Use `subprocess.Popen` with `start_new_session=True` to re-exec the loop command as a detached process (avoids `os.fork()` which is Unix-only — see FEAT-431 closure). The parent process writes the child PID to `.loops/.running/<name>.pid` and exits. The child redirects stdout/stderr to `.loops/.running/<name>.log`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Existing detach pattern**: `handoff_handler.py:114-122` already uses `subprocess.Popen(..., start_new_session=True, stdout=DEVNULL, stderr=DEVNULL, stdin=DEVNULL)` to spawn detached Claude processes
- **Signal handling gap**: `FSMExecutor` has `_shutdown_requested` flag and `request_shutdown()` method (`executor.py:340`), but **no signal handler** registers SIGTERM/SIGINT in the loop CLI path. The sprint runner (`sprint/run.py:24-40, 95-98`) has the exact pattern needed: module-level flag + `signal.signal()` registration
- **PID liveness check**: `concurrency.py:252-258` already implements `os.kill(pid, 0)` for checking if a PID is alive — reuse this for `cmd_status`
- **`cmd_stop` limitation**: Current implementation (`lifecycle.py:42-64`) only writes `"interrupted"` to the state file. The foreground executor never re-reads the state file, so this is effectively a no-op for foreground loops. For background mode, `cmd_stop` must read the PID file and send `os.kill(pid, signal.SIGTERM)`

## API/Interface

```bash
ll-loop run <name> --background   # Detach as daemon; writes PID to .loops/.running/<name>.pid
ll-loop stop <name>               # Send SIGTERM via PID file; removes PID file on confirmed exit
ll-loop status [<name>]           # Show running background loops with PID + liveness check
```

## Implementation Steps

1. **Add SIGTERM/SIGINT signal handler to loop CLI** — In `run.py:cmd_run()`, register signal handlers (following `sprint/run.py:24-40` pattern) that call `executor.request_shutdown()`. This is a prerequisite — without it, neither foreground nor background loops handle signals gracefully.

2. **Implement `run_background()` in `_helpers.py`** — New function alongside existing `run_foreground()`. Uses `subprocess.Popen` with `start_new_session=True` to re-exec `ll-loop run <name> --foreground-internal` (an internal flag that skips re-daemonization). Parent writes child PID to `.loops/.running/<name>.pid`, prints confirmation, and returns 0.

3. **Add PID file management** — Write PID file at daemon startup, register cleanup in an `atexit` handler and in the signal handler. Use `fcntl.flock` for atomic writes (pattern from `concurrency.py:116`).

4. **Add log file redirection** — In the daemonized child process, redirect stdout/stderr to `.loops/.running/<name>.log` before calling `run_foreground()`.

5. **Enhance `cmd_stop` in `lifecycle.py:42-64`** — Read PID from `.loops/.running/<name>.pid`, verify liveness with `os.kill(pid, 0)` (pattern from `concurrency.py:252-258`), send `os.kill(pid, signal.SIGTERM)`, wait briefly, clean up PID file.

6. **Enhance `cmd_status` in `lifecycle.py:12-39`** — If a `.pid` file exists, read it and verify process liveness. Show PID and whether process is actually alive vs just having stale state files.

7. **Update `__init__.py:89`** — Remove "(not yet implemented)" from `--background` help text.

8. **Add tests** — Follow `test_handoff_handler.py:55-80` pattern for daemon spawn assertions. Follow `test_cli.py:2251-2297` pattern for signal handler tests. Add lifecycle tests for start/status/stop cycle.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/run.py:63-65` — Replace background stub with `run_background()` call; add signal handler registration before `run_foreground()` call (line 94)
- `scripts/little_loops/cli/loop/_helpers.py` — Add `run_background()` function alongside existing `run_foreground()` (line 136)
- `scripts/little_loops/cli/loop/lifecycle.py:42-64` — Enhance `cmd_stop()` to read PID file and send SIGTERM
- `scripts/little_loops/cli/loop/lifecycle.py:12-39` — Enhance `cmd_status()` to show PID and liveness
- `scripts/little_loops/cli/loop/__init__.py:89` — Update `--background` help text to remove "(not yet implemented)"

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:340` — `request_shutdown()` method — called by new signal handler
- `scripts/little_loops/fsm/persistence.py:131-132` — State and events files in `.loops/.running/` — new PID/log files colocated here
- `scripts/little_loops/fsm/concurrency.py:103,252-258` — `mkdir()` pattern and `_process_alive()` liveness check — reuse for PID management

### Similar Patterns
- `scripts/little_loops/fsm/handoff_handler.py:114-122` — `subprocess.Popen(start_new_session=True, stdout=DEVNULL)` for detached process creation
- `scripts/little_loops/cli/sprint/run.py:24-40,95-98` — Module-level signal handler with double-signal pattern (graceful then force)
- `scripts/little_loops/parallel/orchestrator.py:163-173` — Instance signal handler with save/restore of original handlers
- `scripts/little_loops/fsm/concurrency.py:107-120` — PID tracking in JSON lock files with `fcntl.flock` atomic writes
- `scripts/little_loops/parallel/merge_coordinator.py:81-111` — `daemon=True` thread lifecycle pattern

### Tests
- `scripts/tests/test_handoff_handler.py:55-80` — Pattern for testing `Popen(start_new_session=True)` assertions
- `scripts/tests/test_cli.py:2251-2297` — Pattern for testing signal handlers (module flag reset + direct handler invocation)
- `scripts/tests/test_cli_loop_lifecycle.py` — Existing lifecycle tests to extend for PID-based stop
- `scripts/tests/test_ll_loop_commands.py` — Existing loop command tests to extend
- `scripts/tests/test_concurrency.py:19-55` — Pattern for PID dataclass tests

### Documentation
- `scripts/little_loops/cli/loop/__init__.py:89` — Remove "(not yet implemented)" from help text
- `docs/guides/LOOPS_GUIDE.md` — Document background mode usage

### Configuration
- N/A — uses existing `loops_dir` from `LoopsConfig` (`config.py:339`), no new config keys needed

## Impact

- **Priority**: P3 — Completing a declared but unimplemented feature
- **Effort**: Large — Daemon management, PID files, signal handling
- **Risk**: Medium — Process management is platform-sensitive
- **Breaking Change**: No

## Labels

`feature`, `cli`, `loops`, `daemon`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a32a1e4-137e-4580-a6db-a31be30ec313.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is well-specified with specific file references and daemon pattern; no knowledge gaps identified
- `/ll:refine-issue` - 2026-02-27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2279c5d8-0ee5-4951-b318-c58cfb3e1d4f.jsonl` - Deep research: found 2 prior closed issues (FEAT-255, FEAT-431), signal handling gap, directory convention mismatch, enriched integration map with 17 pattern references

## Resolution

**Implemented** on 2026-02-27.

### Changes Made

1. **Signal handler registration** (`run.py`): Module-level SIGTERM/SIGINT handler following sprint runner pattern. First signal calls `executor.request_shutdown()` for graceful shutdown; second signal forces `sys.exit(1)`. Benefits both foreground and background execution.

2. **Background process spawning** (`_helpers.py`): New `run_background()` function uses `subprocess.Popen(start_new_session=True)` to re-exec `ll-loop run <name> --foreground-internal` as a detached daemon. Parent writes PID file and returns immediately.

3. **PID-based stop** (`lifecycle.py`): Enhanced `cmd_stop()` reads PID from `.loops/.running/<name>.pid` and sends `os.kill(pid, signal.SIGTERM)`. Falls back to state-only stop for foreground loops. Auto-cleans stale PID files.

4. **PID-based status** (`lifecycle.py`): Enhanced `cmd_status()` shows PID and liveness check (`running` vs `stale PID file`) when a `.pid` file exists.

5. **PID cleanup on exit** (`run.py`): `--foreground-internal` flag registers `atexit` handler and signal handler cleanup for the PID file.

6. **Updated CLI help** (`__init__.py`): Removed "(not yet implemented)" from `--background` help text. Added hidden `--foreground-internal` argument.

7. **17 new tests** (`test_cli_loop_background.py`): Signal handler, `run_background()` spawn, PID file management, PID-based stop/status, arg forwarding. Updated 1 existing test (`test_ll_loop_execution.py`).

### Files Modified
- `scripts/little_loops/cli/loop/run.py` — Signal handler, background dispatch, foreground-internal PID cleanup
- `scripts/little_loops/cli/loop/_helpers.py` — `run_background()` function
- `scripts/little_loops/cli/loop/lifecycle.py` — PID-based `cmd_stop()` and `cmd_status()`
- `scripts/little_loops/cli/loop/__init__.py` — Updated `--background` help, added `--foreground-internal`
- `scripts/tests/test_cli_loop_background.py` — New test file (17 tests)
- `scripts/tests/test_ll_loop_execution.py` — Updated existing background test

---

## Status

**Completed** | Created: 2026-02-24 | Completed: 2026-02-27 | Priority: P3
