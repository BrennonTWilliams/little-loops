---
id: BUG-3312
type: BUG
title: "Ctrl+C does not stop ll-auto \u2014 detached subprocess ignores SIGINT"
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-24'
captured_at: '2026-08-24T16:07:51Z'
---

# BUG-3312: Ctrl+C does not stop ll-auto — detached subprocess ignores SIGINT

## Summary

Pressing Ctrl+C during an `ll-auto` run does not stop the run. It prints
`[HH:MM:SS] Received signal 2, shutting down gracefully...` once, then the
run continues to completion of the in-progress issue (or its own
timeout/idle-timeout) before actually exiting.

## Current Behavior

Pressing Ctrl+C during an `ll-auto` run sets `_shutdown_requested = True` and
prints a one-time log line, but the currently running `claude` CLI subprocess
— spawned detached via `start_new_session=True` — never receives the signal
and keeps running to completion (or its own timeout) before the outer loop
notices the flag and exits.

## Expected Behavior

Pressing Ctrl+C during an `ll-auto` run should stop the run promptly: the
active `claude` subprocess should be killed (via the existing process-group
kill path) as soon as the interrupt is caught, rather than being left to run
to completion or timeout before shutdown proceeds.

## Motivation

An unresponsive Ctrl+C during long-running automated issue processing forces
users to wait out an entire in-progress issue implementation (potentially
many minutes) or resort to killing the process externally (e.g. `kill -9`),
which can leave orphaned child processes and worktrees behind. Fixing this
makes `ll-auto` runs safely interruptible, which is basic expected behavior
for a long-running CLI tool.

## Proposed Solution

Propagate the interrupt into the running subprocess rather than relying on a
flag the outer loop only consults between issues. Options:
- Have `_signal_handler` reach the currently active `Popen` (e.g. via the
  existing `on_process_start`/`on_process_end` callback hooks already
  threaded through `run_claude_command`) and call `_kill_process_group()` on
  it when a shutdown signal fires.
- Have the `run_claude_command` read loop poll a shutdown flag/event each
  iteration (it already loops every ~1s via `sel.select(timeout=1.0)`) and
  break out to kill the process group when set.

Either way, `start_new_session=True` is required for the idle/wall-clock
timeout kill path (`_kill_process_group` uses `os.killpg`), so the fix must
route SIGINT through the same process-group kill machinery rather than
removing `start_new_session`.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` (`_signal_handler`,
  `IssueManager.__init__` signal registration)
- `scripts/little_loops/subprocess_utils.py` (`run_claude_command` read loop,
  `_kill_process_group`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — `_process_issue()` ->
  `run_with_continuation()` -> `run_claude_command()` call chain that must
  keep working for non-interrupted runs

### Similar Patterns
- Existing idle/wall-clock timeout kill path in `run_claude_command`
  (`_kill_process_group` via `os.killpg`) is the pattern to reuse for the
  SIGINT case rather than inventing a second kill mechanism

### Tests
- `scripts/tests/` — tests covering `IssueManager` shutdown handling and
  `run_claude_command` timeout/kill behavior (add a case simulating SIGINT
  during an active subprocess)

### Documentation
- N/A

## Program Design

### Types

- (none new — reuses existing `Popen` handle already tracked via
  `on_process_start`/`on_process_end` callbacks)

### Signatures

- `_signal_handler(self, signum: int, frame: FrameType | None) -> None` (existing, `issue_manager.py:1741`)
- `_kill_process_group(process: subprocess.Popen) -> None` (existing, `subprocess_utils.py`)

### Call Path

`_signal_handler` -> `run_claude_command` -> `_kill_process_group`

## Implementation Steps

1. Track the currently active `Popen` (or a shutdown event) so it's
   reachable from `_signal_handler` or pollable from the
   `run_claude_command` read loop.
2. On SIGINT/SIGTERM, kill the active process group via
   `_kill_process_group()` instead of only setting `_shutdown_requested`.
3. Verify: reproduce the Ctrl+C-during-Phase-2 scenario from Steps to
   Reproduce and confirm the run exits promptly instead of running to
   completion/timeout.

## Impact

- **Priority**: P2 - Interrupting a long-running automated run is a basic
  usability expectation; not data-loss-critical but a frequent annoyance
  that can force `kill -9` and orphaned processes.
- **Effort**: Small - Reuses the existing `_kill_process_group` /
  `os.killpg` machinery already used for timeout kills; no new kill
  mechanism needed.
- **Risk**: Low - Change is additive (wiring SIGINT to an existing kill
  path); non-interrupted runs are unaffected.
- **Breaking Change**: No

## Root Cause

Three things combine to make the interrupt a no-op for the currently running
work:

1. `IssueManager.__init__` (`scripts/little_loops/issue_manager.py:1738-1739`)
   registers a custom `SIGINT`/`SIGTERM` handler,
   `_signal_handler` (`scripts/little_loops/issue_manager.py:1741-1744`), that
   only does `self._shutdown_requested = True` and logs the message. Python's
   default `KeyboardInterrupt` behavior is replaced, so nothing unwinds the
   current call stack.

2. `_shutdown_requested` is only checked at the top of the outer processing
   loop, `while not self._shutdown_requested:`
   (`scripts/little_loops/issue_manager.py:1951`) — i.e. between issues. Once
   `_process_issue()` -> `run_with_continuation()` -> `run_claude_command()`
   is underway, nothing inside that call chain re-checks the flag until it
   returns.

3. The actual `claude` CLI subprocess is spawned in `run_claude_command()`
   via `subprocess.Popen(cmd_args, ..., start_new_session=True)`
   (`scripts/little_loops/subprocess_utils.py:457-465`). `start_new_session=True`
   puts the child in its own session/process group, detached from the
   terminal. Ctrl+C only delivers `SIGINT` to the terminal's *foreground
   process group*, so the detached child never receives it and keeps running
   normally.

The read loop in `run_claude_command`
(`scripts/little_loops/subprocess_utils.py:501-627`) has no shutdown/cancel
check at all — it only exits on the pipes closing, the wall-clock `timeout`,
the idle timeout, or a stream-json `result` event.

Net effect: Ctrl+C logs a message and sets a flag nothing currently
executing looks at. The detached subprocess is unaffected by the signal and
runs to completion; only then does control return to the outer loop, which
finally observes `_shutdown_requested` and stops picking up new issues.

## Steps to Reproduce

1. Run `ll-auto` against a project with at least one processable issue.
2. While Phase 2 (implement) is running — i.e. the `claude` CLI subprocess
   is actively streaming — press Ctrl+C.
3. Observe: `[HH:MM:SS] Received signal 2, shutting down gracefully...` is
   printed, but the run does not stop; the current issue's implementation
   subprocess keeps running to completion (or timeout) before the process
   actually exits.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-24 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-08-24T16:12:01 - `b85ae83c-887b-4e17-9a4e-1911475585d3.jsonl`
- `/ll:capture-issue` - 2026-08-24T16:07:57 - `69c375ac-5c89-44f2-a3fc-ad8aa6520c60.jsonl`
