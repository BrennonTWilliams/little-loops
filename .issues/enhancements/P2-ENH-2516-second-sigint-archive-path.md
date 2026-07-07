---
id: ENH-2516
title: Wire second-SIGINT force-exit branch to PersistentExecutor archive path
type: ENH
status: done
priority: P2
parent: ENH-2514
decision_needed: false
captured_at: '2026-07-07T06:36:33Z'
completed_at: '2026-07-07T10:40:32Z'
discovered_date: '2026-07-07'
discovered_by: issue-size-review
relates_to:
- ENH-2514
- ENH-2515
- BUG-2501
- BUG-2513
labels:
- loops
- fsm
- ll-loop
- signal-handling
- audit-trail
confidence_score: 95
outcome_confidence: 81
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2516: Wire second-SIGINT force-exit branch to PersistentExecutor archive path

## Summary

Modify `_loop_signal_handler`'s second-SIGINT force-exit branch
(`scripts/little_loops/cli/loop/_helpers.py:97`) to invoke the archive path
before `sys.exit(1)`, closing the gap where the second Ctrl-C currently
bypasses every durability step. Extract a signal-handler-safe `archive_run_only()`
(or `finalize_run(terminated_by)`) method on `PersistentExecutor` to support
the call without re-entering `executor.run()`.

## Motivation

This enhancement closes the audit-trail gap that surfaces in `/ll:audit-loop-run`'s
pre-flight gate (BUG-2501 / BUG-2513): when a user force-quits a loop with a
second Ctrl-C, the run artifacts (`state.json` / `events.jsonl` archive) are
never written, so post-mortem inspection and learning-test reuse of the run are
blocked. Decomposed from ENH-2514; this child is the signal-handler half of the
durability fix (sister to ENH-2515's persistence-layer flush+fsync).

## Expected Behavior

After this change, the second SIGINT (force-exit Ctrl-C) writes the current
run's `state.json` snapshot and `events.jsonl` archive before `sys.exit(1)` —
matching the durability already provided by the first-SIGINT graceful path,
and matching the `cmd_stop` precedent at `lifecycle.py:316-375` which calls
`persistence.save_state(state)` directly after SIGTERM.

## Current Behavior

Verified by codebase research: the first SIGINT DOES trigger a graceful
archive. `_loop_signal_handler` on the first signal sets
`_loop_shutdown_requested = True`, calls `_loop_executor.request_shutdown()`,
which returns `self._finish("interrupted")` → emits `loop_complete` → triggers
`_save_state` via `_handle_event` gating → returns to `PersistentExecutor.run`
which calls `save_state` + `archive_run`. So a single Ctrl-C DOES archive the
run.

The real gap is the SECOND SIGINT force-exit path. When
`_loop_shutdown_requested` is already `True` (the user hit Ctrl-C twice), the
handler at `_loop_signal_handler` (lines 87-97) skips the graceful path
entirely and calls `sys.exit(1)` (line 97) directly. No `save_state`, no
`archive_run`. The only filesystem write on this path is the PID-file `unlink`
(line 88).

This child implements the "Selected: Signal-flush" path from ENH-2514.

## Parent Issue

Decomposed from ENH-2514: ll-loop should flush events.jsonl / state.json on
forced termination. The persistence-layer durability change is decomposed into
ENH-2515; this child covers only the signal-handling path.

## Implementation Steps

1. Extract the post-block inside `PersistentExecutor.run`
   (`scripts/little_loops/fsm/persistence.py:841-867`) into a new public method
   on `PersistentExecutor`:
   ```python
   def archive_run_only(self, terminated_by: str) -> Path | None:
       """Archive the current run without re-entering executor.run().

       Signal-handler-safe: does NOT mutate executor state. Invokes save_state
       + archive_run. Returns the archive path or None if neither state.json
       nor events.jsonl exists.
       """
   ```
   The body mirrors lines 841-867: compute `final_status` from
   `result.terminated_by`, call `self.persistence.save_state(final_state)` (line 865),
   then `self.persistence.archive_run(run_dir=...)` (line 867). Return the archive path.
2. Modify `_loop_signal_handler` second-SIGINT branch
   (`scripts/little_loops/cli/loop/_helpers.py:97`) to invoke the new method
   before `sys.exit(1)`:
   ```python
   # existing: PID-file unlink (line 88), alt-screen reset (line 94),
   # print("Force shutdown requested") (line 96)
   # NEW: invoke archive before exit
   try:
       if _loop_executor is not None:
           _loop_executor.archive_run_only(terminated_by="interrupted_force")
   except OSError:
       pass  # mirror _signal_process_group's defensive coding at lifecycle.py:116
   sys.exit(1)  # existing line 97
   ```
3. Reentrancy safety: do NOT mutate `_shutdown_requested` (already True); do
   NOT print to stderr after invoking archive (the existing `print(colorize(...))`
   at line 96 runs before the archive call).
4. Add unit tests in `scripts/tests/test_cli_loop_background.py` extending
   `TestLoopSignalHandler` (line 13). New test:
   - `test_second_signal_archives_before_exit`:
     1. Set `self.helpers._loop_shutdown_requested = True` (precondition).
     2. Patch `_loop_executor.archive_run_only` to a `MagicMock`.
     3. Wrap the second-signal call in `pytest.raises(SystemExit)`.
     4. Assert `archive_run_only.assert_called_once_with(terminated_by="interrupted_force")`.
     5. Restore globals in `teardown_method` (lines 32-37).
5. Add an idempotency test (third Ctrl-C must NOT double-archive):
   - After the first force-exit, the handler should be a no-op (executor is
     gone or `_shutdown_requested` semantics prevent re-entry).

## API/Interface

New public method on `PersistentExecutor`:
- `archive_run_only(terminated_by: str) -> Path | None`

Signal handler at `_loop_signal_handler` second-SIGINT branch gains an
`archive_run_only()` call.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — add `archive_run_only()` method
  to `PersistentExecutor`.
- `scripts/little_loops/cli/loop/_helpers.py` — modify second-SIGINT branch
  (`_loop_signal_handler` line 97).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py:316-375` (`cmd_stop`) — already
  calls `persistence.save_state(state)` directly after SIGTERM. Orchestration
  precedent; no caller change required but the new `archive_run_only()` method
  is a cleaner API for future callers.
- Sister pattern at `scripts/little_loops/parallel/orchestrator.py:188-196` —
  `try/except KeyboardInterrupt / finally: self._cleanup(); self._restore_signal_handlers()`
  is the precedent for centralized post-signal cleanup.

### Similar Patterns
- `scripts/little_loops/cli/sprint/run.py:60-88` (`_run_with_timeout` SIGALRM)
  — save/restore pattern is the inverse of `_loop_signal_handler`'s current
  leak (handlers install but never restore). For ENH-2516, install at executor
  start, restore in `finally` before `executor.close_transports()` runs.

### Tests
- Direct-call unit test in `TestLoopSignalHandler`
  (`scripts/tests/test_cli_loop_background.py`):
  `test_second_signal_archives_before_exit` (per Implementation Step 4).
- Idempotency test for third Ctrl-C.
- Reentrancy test: signal handler must NOT mutate executor state.

### Documentation
- N/A

### Configuration
- N/A

## Scope Boundaries

- **In scope**: Second-SIGINT force-exit branch modification + new
  `PersistentExecutor.archive_run_only()` method + direct-call unit tests.
- **Out of scope**: Persistence-layer flush+fsync upgrade (covered by ENH-2515).
- **Out of scope**: Subprocess SIGINT integration test (covered by ENH-2517).
- **Out of scope**: Applying the same fix to `_sprint_signal_handler`
  (`scripts/little_loops/cli/sprint/run.py:101`) — out of scope per ENH-2514
  Scope Boundaries; flag for backlog grooming as a follow-up.

## Impact

- **Priority**: P2 — Closes the BUG-2501 / BUG-2513 audit-trail gap.
- **Effort**: Small — one new method + one branch modification + ~30 lines of
  test code.
- **Risk**: Medium — signal-handler reentrancy. Mitigation: wrap archive in
  `try/except OSError` (mirror `_signal_process_group` at `lifecycle.py:116`);
  do NOT mutate `_shutdown_requested`; do NOT print to stderr after invoking
  archive.
- **Breaking Change**: No — strictly improves observability.

## Status

**Done** | Created: 2026-07-07 | Completed: 2026-07-07 | Priority: P2

## Session Log
- `/ll:manage-issue improve ENH-2516` - 2026-07-07T10:40:32Z - implement archive_run_only() + wire second-SIGINT
- `/ll:ready-issue` - 2026-07-07T10:22:50 - `782bf49a-f898-45f7-ac83-ffb91023d80b.jsonl`
- `/ll:format-issue` - 2026-07-07T10:14:11 - `351ee465-a1ee-432a-87a0-b2693032c142.jsonl`
- `/ll:issue-size-review` - 2026-07-07T06:36:33Z - `fc70cacc-0621-41d5-a7b3-89f8f15d4569.jsonl`
- `/ll:confidence-check` - 2026-07-07T10:17:49Z - `b2d5a4a3-fb4d-4394-b22e-f1752132537e.jsonl`