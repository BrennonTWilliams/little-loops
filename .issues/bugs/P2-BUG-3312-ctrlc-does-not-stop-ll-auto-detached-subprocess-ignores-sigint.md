---
id: BUG-3312
type: BUG
title: "Ctrl+C does not stop ll-auto \u2014 detached subprocess ignores SIGINT"
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-24'
captured_at: '2026-08-24T16:07:51Z'
confidence_score: 98
outcome_confidence: 75
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 12
score_change_surface: 22
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- Both listed options have direct codebase precedent (codebase-pattern-finder): the first option (reach the active `Popen` from the signal handler via `on_process_start`/`on_process_end`) is the exact idiom already used by `ll-loop`'s FSM path (`ActionRunner._current_process` in `fsm/runners.py:114,205-215,237-238`; `FSMExecutor._current_process` in `fsm/executor.py:290,2484,2540`; consumed by `_loop_signal_handler` in `cli/loop/_helpers.py:123-174` via `getattr(obj, "_current_process", None)` then `.kill()`) and by `WorkerPool._active_processes` (`parallel/worker_pool.py:189,939-947,967-968`, consumed by `terminate_all_processes()` at `:249-276`). `ll-auto`'s call chain (`issue_manager.py`) is the one place these hooks are unused end-to-end (see Integration Map finding above).
- Kill-mechanism discrepancy: the `ll-loop` precedent kills with bare `proc.kill()`, not `_kill_process_group()` — see the "Contested convention" finding under Program Design. If this issue's fix reuses the `on_process_start`/`on_process_end` wiring pattern but insists on process-group kill (per this section's existing requirement), it will be a variant of the `ll-loop` idiom rather than a literal copy of it; that divergence should be a deliberate choice, not an oversight.
- Second option (poll a shutdown flag/event inside the `run_claude_command` read loop) is also directly actionable: the loop already re-enters its top once per second via `sel.select(timeout=1.0)` (`subprocess_utils.py:528`), alongside its existing per-iteration wall-clock/idle-timeout checks (`subprocess_utils.py:504-526`) — a shutdown check would slot in next to those with no new blocking primitive required. No existing precedent in the codebase threads a `threading.Event` (or similar) into this specific read loop for cancellation; both `ll-auto` and `ll-loop`'s existing shutdown paths use plain module/instance-level boolean flags, not `threading.Event`.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- Precise call chain confirmed (codebase-analyzer): `AutoManager.run()` loop (`issue_manager.py:1951`) -> `AutoManager._process_issue()` (`issue_manager.py:2056`) -> `process_issue_inplace()` (`issue_manager.py:689`, Phase 2 call at `:1293`) -> `run_with_continuation()` (`issue_manager.py:256`, its own loop at `:348`) -> local `run_claude_command()` wrapper (`issue_manager.py:140-222`) -> `subprocess_utils.run_claude_command` (imported aliased as `_run_claude_base`, `issue_manager.py:66-68`) -> `subprocess_utils.py:347`, where the `Popen` is created (`subprocess_utils.py:457`).
- At every hop in that chain, **none of the call sites pass `on_process_start`/`on_process_end`** — the local `run_claude_command()` wrapper at `issue_manager.py:140` does not even declare those two parameters, so it has no way to forward them even if a caller wanted to. This is the concrete reason `_signal_handler` (`issue_manager.py:1741`) has nothing to reach into: the `Popen` created at `subprocess_utils.py:457` is a pure local variable of that function's stack frame for the entire `ll-auto` path.
- Existing precedent that DOES wire this up (codebase-pattern-finder + codebase-analyzer): `ll-loop`'s FSM path already tracks the active `Popen` via paired `on_process_start`/`on_process_end` callbacks — `ActionRunner._current_process` (`fsm/runners.py:114`, set/cleared by `_on_proc_start`/`_on_proc_end` closures at `fsm/runners.py:205-215`, wired into its `run_claude_command()` call at `fsm/runners.py:237-238`) and `FSMExecutor._current_process` (`fsm/executor.py:290`, set at `:2484`, cleared at `:2540`) for its own subprocess path. `WorkerPool._active_processes` (`parallel/worker_pool.py:189`, populated via `on_start`/`on_end` closures at `:939-947`, wired at `:967-968`) is a second, dict-keyed instance of the same idiom. `ll-auto`'s `AutoManager`/`issue_manager.py` call chain is the one place in the codebase where these hooks are defined-but-unused end-to-end.
- Test coverage: `scripts/tests/test_issue_manager.py:4102-4138` (`TestSignalHandler`, docstring cites ENH-207) covers only the flag-flip behavior of `_signal_handler` — no test in that file exercises killing an active subprocess. The analogous already-solved case has its own test class: `scripts/tests/test_cli_loop_background.py:13-108` (`TestLoopSignalHandler`), with `test_signal_handler_kills_current_process` (BUG-592) and `test_signal_handler_kills_fsm_executor_current_process` (BUG-818) as direct templates for a new `ll-auto` equivalent, plus `test_signal_handler_no_current_process_is_safe` (BUG-592) as the template for the "no active process yet" case.

## Program Design

### Types

- (none new — reuses existing `Popen` handle already tracked via
  `on_process_start`/`on_process_end` callbacks)

### Signatures

- `_signal_handler(self, signum: int, frame: FrameType | None) -> None` (existing, `issue_manager.py:1741`)
- `_kill_process_group(process: subprocess.Popen) -> None` (existing, `subprocess_utils.py`)

### Call Path

`_signal_handler` -> `run_claude_command` -> `_kill_process_group`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- Refined Call Path (codebase-analyzer, supersedes the earlier one-line version — the intermediate hops matter for where a shutdown check or hook-forwarding change actually lands): `AutoManager._signal_handler` (`issue_manager.py:1741`) -> [currently dead-ends; needs to reach] -> `_run_claude_base` (`subprocess_utils.run_claude_command`, `subprocess_utils.py:347`)'s active `Popen` (`subprocess_utils.py:457`), traversing `run_with_continuation` (`issue_manager.py:256`) -> local `run_claude_command` wrapper (`issue_manager.py:140`) -> `_run_claude_base`.
- Read-loop insertion point (codebase-analyzer): the selector loop `while sel.get_map():` (`subprocess_utils.py:502-627`) already checks wall-clock timeout and idle timeout once per iteration before calling `sel.select(timeout=1.0)` (line 528) — a shutdown check inserted alongside those two would fire within ≤1s of a signal using the loop's existing polling cadence, no new blocking primitive needed.
- Contested convention — kill mechanism (codebase-pattern-finder): the issue's own Proposed Solution requires routing through `_kill_process_group()` (process-group SIGTERM/SIGKILL escalation, `subprocess_utils.py:311-344`). But the only existing precedent for "external signal handler reaches into an active `Popen` and kills it" — `ll-loop`'s `_loop_signal_handler` (`cli/loop/_helpers.py:123-174`) — calls bare `proc.kill()` directly on the `Popen` (single process, not the process group), bypassing `_kill_process_group()` entirely. The two conventions disagree: `_kill_process_group` is used today only for the timeout/idle-timeout paths *inside* `run_claude_command` itself (`subprocess_utils.py:505,516,643`), never from an external signal handler. Whether the SIGINT fix should reuse `_kill_process_group` (as the issue proposes) or follow the `ll-loop` precedent of bare `.kill()` is an open implementation decision, not settled by existing convention.

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
- `/ll:confidence-check` - 2026-08-24T16:39:51 - `9960f916-2441-4af1-90fa-4a886fc8f95c.jsonl`
- `/ll:refine-issue` - 2026-08-24T16:21:11 - `e5f4e5f1-003d-4663-97d4-27dbe660784d.jsonl`
- `/ll:format-issue` - 2026-08-24T16:12:01 - `b85ae83c-887b-4e17-9a4e-1911475585d3.jsonl`
- `/ll:capture-issue` - 2026-08-24T16:07:57 - `69c375ac-5c89-44f2-a3fc-ad8aa6520c60.jsonl`
