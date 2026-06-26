---
id: ENH-2300
type: ENH
priority: P3
status: done
size: Small
captured_at: '2026-06-25T00:00:00Z'
discovered_date: 2026-06-25
discovered_by: manual
relates_to:
- ENH-360
decision_needed: false
completed_at: '2026-06-25T21:00:00Z'
---

# ENH-2300: Harden FSM runner against BrokenPipe and subprocess spawn failures

## Summary

Two targeted resilience fixes to the FSM loop runner's exception-handling chain,
implementing Fix 1 and Fix 2 from `rn-enh-360-loop-runner-broken-pipe-fix.md`.
Previously, a `BrokenPipeError` (or any non-`TimeoutExpired` exception) escaping
`run_claude_command()` could propagate past `DefaultActionRunner.run()` and up the
call stack, potentially killing the runner mid-action with no `action_error` journal
event emitted. A spawn-time `OSError` from `subprocess.Popen()` had the same effect.

## Changes

### Fix 1 — `scripts/little_loops/fsm/runners.py`

Added `except Exception as exc` after the existing `except subprocess.TimeoutExpired`
block in `DefaultActionRunner.run()`. Any unexpected exception from `run_claude_command()`
(e.g. `BrokenPipeError`, `OSError`, `RuntimeError`) is now converted to an
`ActionResult(exit_code=1, stderr="Action failed: <exc>")` instead of propagating bare.
This ensures the FSM always receives a routable result and can recover via `on_error`
rather than crashing.

`HostNotConfigured` (from `resolve_host()`) is intentionally caught here — it propagates
through `run_claude_command()` unchanged and is caught at this layer, surfacing as a
clear `action_error` in the journal.

### Fix 2 — `scripts/little_loops/subprocess_utils.py`

Wrapped `subprocess.Popen()` in a try/except in `run_claude_command()`. An `OSError`
or other exception raised during process spawn (e.g. binary not found) now returns a
synthetic `CompletedProcess(returncode=1, stderr="Subprocess spawn failed: <exc>")` instead
of crashing. `resolve_host()` and `build_streaming()` are left unguarded so that
`HostNotConfigured` continues to propagate as a distinct exception to callers.

## Motivation

A `qa-pipeline` run ended with an orphaned `action_start` journal event and
`state.json` stuck at `status: running` after consecutive `BrokenPipeError`s.
The first broken pipe was caught by `_run_action_or_route`, but a second spawn
attempt could exit the process without emitting `action_error`, leaving the run
in an unrecoverable state until the next `_reconcile_stale_running()` call.

## Verification

- All 1024 tests in `scripts/tests/test_subprocess_utils.py` and
  `scripts/tests/test_builtin_loops.py` pass.
- Full suite: 11025 passed, 8 skipped.
- `mypy` clean on both modified files.
- Existing `test_host_not_configured_propagates` continues to pass — `HostNotConfigured`
  still propagates through `run_claude_command()` as before.


## Session Log
- `hook:posttooluse-status-done` - 2026-06-26T00:10:49 - `3ce78d2f-d1c6-446a-a875-e4084af0775b.jsonl`
