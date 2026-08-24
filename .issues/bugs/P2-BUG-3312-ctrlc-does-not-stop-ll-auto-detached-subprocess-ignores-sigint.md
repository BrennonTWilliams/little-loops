---
id: BUG-3312
type: BUG
title: "Ctrl+C does not stop ll-auto \u2014 detached subprocess ignores SIGINT"
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-24'
captured_at: '2026-08-24T16:07:51Z'
completed_at: '2026-08-24T17:24:15Z'
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
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

Pressing Ctrl+C during an `ll-auto` run should stop the run promptly:

1. The active `claude` subprocess is killed (via the existing process-group
   kill path) as soon as the interrupt is caught, rather than being left to
   run to completion or timeout.
2. The in-flight issue's remaining phases do **not** run. Killing the Phase 2
   subprocess alone is not sufficient — see "Shutdown must be observed at
   phase boundaries" under Root Cause.
3. A second Ctrl+C forces immediate exit, matching the `ll-loop` precedent
   (`_loop_signal_handler`, ENH-2516).
4. The interrupted run is recorded as *interrupted*, not as a Phase 2 crash.

## Motivation

An unresponsive Ctrl+C during long-running automated issue processing forces
users to wait out an entire in-progress issue implementation (potentially
many minutes) or resort to killing the process externally (e.g. `kill -9`),
which can leave orphaned child processes and worktrees behind. Fixing this
makes `ll-auto` runs safely interruptible, which is basic expected behavior
for a long-running CLI tool.

## Proposed Solution

Propagate the interrupt into the running subprocess *and* into the phase
sequencing, rather than relying on a flag the outer loop only consults
between issues.

### Decision 1 — shutdown signalling mechanism: module-level Event (settled)

Two options were considered; **option B is chosen**.

- **Option A (rejected)** — have `_signal_handler` reach the currently active
  `Popen` via the `on_process_start`/`on_process_end` hooks, as `ll-loop` and
  `WorkerPool` do. Rejected because `ll-auto`'s call chain crosses two
  *module-level, shared* functions — the local `run_claude_command` wrapper
  (`issue_manager.py:140`) and `run_with_continuation`
  (`issue_manager.py:256`) — that ll-parallel and sprint workers also call.
  There is no `self` to hang a `_current_process` attribute on across that
  boundary, so this option requires widening two shared signatures and still
  does nothing for Decision 3 (phase boundaries).
- **Option B (chosen)** — a module-level shutdown `threading.Event` in
  `subprocess_utils`, polled by the `run_claude_command` read loop alongside
  its existing wall-clock/idle-timeout checks (`subprocess_utils.py:504-526`).
  `_signal_handler` sets the event; the loop observes it within ≤1s via the
  existing `sel.select(timeout=1.0)` cadence and kills the process group.

Option B is preferred because it: requires no signature changes; covers every
caller of `run_claude_command` at once (ll-parallel and sprint workers get the
same behavior for free); performs the kill in normal loop context rather than
inside the signal handler — which matters, because
`_kill_process_group(grace_seconds>0)` calls `process.wait()`
(`subprocess_utils.py:330`) and blocking on a child inside a signal handler is
unsafe; and supplies the same readable signal that Decision 3's phase-boundary
checks need.

### Decision 2 — kill mechanism: `_kill_process_group` (settled)

Use `_kill_process_group()`, **not** the bare `proc.kill()` that `ll-loop`'s
`_loop_signal_handler` uses (`cli/loop/_helpers.py:123-174`). With
`start_new_session=True`, a bare `.kill()` reaps only the `claude` process and
orphans its Task/Workflow grandchildren — which is precisely the "orphaned
child processes" harm this issue's Motivation cites. The `ll-loop` precedent is
arguably a latent bug on its side and should not be copied here. This
supersedes the "contested convention" left open under Program Design.

`start_new_session=True` is required for the idle/wall-clock timeout kill path
(`_kill_process_group` uses `os.killpg`), so the fix must route SIGINT through
the same process-group kill machinery rather than removing
`start_new_session`.

### Decision 3 — abort the in-flight issue at phase boundaries (new scope)

Killing the Phase 2 subprocess is **not** sufficient to stop the run.
`_shutdown_requested` is read in exactly two places today —
`issue_manager.py:1951` (outer loop head) and `:1981` (cleanup guard) — so a
killed Phase 2 falls straight through to Phase 3 verify (`:1420-1423`), which
spawns a *fresh* `claude` subprocess. The fix must additionally:

- Check shutdown at each phase boundary in `process_issue_inplace` (before
  Phase 2 at `:1251`, before Phase 3 at `:1420`) and return an interrupted
  result instead of advancing.
- Check shutdown at the top of `run_with_continuation`'s continuation loop
  (`:348`) so a killed session is not retried or continued.
- Ensure the Phase-2-exited-non-zero branch (`:1342-1354`) does not treat a
  SIGINT kill as ordinary failure and auto-commit a killed session's partial
  work.

### Decision 4 — second signal forces exit (new scope)

`AutoManager._signal_handler` has no escalation tier. Mirror
`_loop_signal_handler` (ENH-2516): first signal requests graceful shutdown,
second signal exits immediately. Without this, any hang after the kill (Phase
3, a `process.wait(timeout=10)`, cleanup) leaves the user in exactly the state
this issue reports.

### Decision 5 — attribute the interrupt correctly (new scope)

ENH-2522 solved this for `ll-loop` by marking `_signal_handler_killed_subproc`
so `exit_code=-9` is reported as `interrupted` rather than `system_signal`.
`ll-auto` has no equivalent, so an interrupted issue would be recorded as a
Phase 2 failure. Note also that `mark_attempted` already fired at
`issue_manager.py:2068` *before* the kill, so the interrupted issue is burned
for `--resume` unless explicitly un-marked. The implementation must decide and
document whether an interrupted issue stays in `attempted_issues`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- Both listed options have direct codebase precedent (codebase-pattern-finder): the first option (reach the active `Popen` from the signal handler via `on_process_start`/`on_process_end`) is the exact idiom already used by `ll-loop`'s FSM path (`ActionRunner._current_process` in `fsm/runners.py:114,205-215,237-238`; `FSMExecutor._current_process` in `fsm/executor.py:290,2484,2540`; consumed by `_loop_signal_handler` in `cli/loop/_helpers.py:123-174` via `getattr(obj, "_current_process", None)` then `.kill()`) and by `WorkerPool._active_processes` (`parallel/worker_pool.py:189,939-947,967-968`, consumed by `terminate_all_processes()` at `:249-276`). `ll-auto`'s call chain (`issue_manager.py`) is the one place these hooks are unused end-to-end (see Integration Map finding above).
- Kill-mechanism discrepancy: the `ll-loop` precedent kills with bare `proc.kill()`, not `_kill_process_group()` — see the "Contested convention" finding under Program Design. If this issue's fix reuses the `on_process_start`/`on_process_end` wiring pattern but insists on process-group kill (per this section's existing requirement), it will be a variant of the `ll-loop` idiom rather than a literal copy of it; that divergence should be a deliberate choice, not an oversight.
- Second option (poll a shutdown flag/event inside the `run_claude_command` read loop) is also directly actionable: the loop already re-enters its top once per second via `sel.select(timeout=1.0)` (`subprocess_utils.py:528`), alongside its existing per-iteration wall-clock/idle-timeout checks (`subprocess_utils.py:504-526`) — a shutdown check would slot in next to those with no new blocking primitive required. No existing precedent in the codebase threads a `threading.Event` (or similar) into this specific read loop for cancellation; both `ll-auto` and `ll-loop`'s existing shutdown paths use plain module/instance-level boolean flags, not `threading.Event`.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — `AutoManager._signal_handler`
  (`:1741`) and its signal registration in `AutoManager.__init__`
  (`:1738-1739`); phase-boundary shutdown checks in `process_issue_inplace`
  (`:1251`, `:1420`); continuation-loop shutdown check in
  `run_with_continuation` (`:348`); Phase-2-non-zero branch (`:1342-1354`)
- `scripts/little_loops/subprocess_utils.py` — module-level shutdown `Event`,
  read-loop poll alongside the existing timeout checks (`:504-526`), reusing
  `_kill_process_group` (`:311-344`)

> **Note:** there is no `IssueManager` class. The class that registers the
> signal handlers is **`AutoManager`** (`issue_manager.py:1631`). An earlier
> revision of this issue named `IssueManager` throughout; that was wrong.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` — `AutoManager._process_issue()`
  (`:2056`) -> `process_issue_inplace()` (`:689`) ->
  `run_with_continuation()` (`:256`) -> local `run_claude_command()` wrapper
  (`:140`) -> `subprocess_utils.run_claude_command` (`:347`) call chain that
  must keep working for non-interrupted runs
- Other callers of `subprocess_utils.run_claude_command` (ll-parallel worker
  pool, sprint workers, `fsm/runners.py`) inherit the module-level shutdown
  Event under Decision 1 — verify none of them regress

### Similar Patterns
- Existing idle/wall-clock timeout kill path in `run_claude_command`
  (`_kill_process_group` via `os.killpg`) is the pattern to reuse for the
  SIGINT case rather than inventing a second kill mechanism
- `_loop_signal_handler` (`cli/loop/_helpers.py:123-174`) is the template for
  the two-tier (graceful / force) handler shape — but **not** for its kill
  mechanism (see Decision 2)

### Tests
- `scripts/tests/test_issue_manager.py:4102-4138` (`TestSignalHandler`) —
  extend; today it covers only the flag-flip behavior
- `scripts/tests/test_cli_loop_background.py:13-108`
  (`TestLoopSignalHandler`) — the direct template, specifically
  `test_signal_handler_kills_current_process` (BUG-592),
  `test_signal_handler_kills_fsm_executor_current_process` (BUG-818), and
  `test_signal_handler_no_current_process_is_safe` (BUG-592)
- New cases required: subprocess killed on first signal; phase-boundary abort
  (no Phase 3 spawn after an interrupted Phase 2); second-signal force exit;
  interrupt attributed as `interrupted` not a crash

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

- `AutoManager._signal_handler(self, signum: int, frame: FrameType | None) -> None` (existing, `issue_manager.py:1741`) — gains the two-tier graceful/force behavior of Decision 4
- `_kill_process_group(process: subprocess.Popen, grace_seconds: float = 0.0) -> None` (existing, `subprocess_utils.py:311`)
- New module-level shutdown `Event` in `subprocess_utils` plus its set/clear/read accessors (Decision 1) — exact names to be chosen at implementation time

### Call Path

`AutoManager._signal_handler` -> sets module-level shutdown Event -> `subprocess_utils.run_claude_command` read loop observes it (≤1s) -> `_kill_process_group`; the same Event is then read at the `process_issue_inplace` phase boundaries and the `run_with_continuation` loop head so the in-flight issue aborts rather than advancing to Phase 3.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- Refined Call Path (codebase-analyzer, supersedes the earlier one-line version — the intermediate hops matter for where a shutdown check or hook-forwarding change actually lands): `AutoManager._signal_handler` (`issue_manager.py:1741`) -> [currently dead-ends; needs to reach] -> `_run_claude_base` (`subprocess_utils.run_claude_command`, `subprocess_utils.py:347`)'s active `Popen` (`subprocess_utils.py:457`), traversing `run_with_continuation` (`issue_manager.py:256`) -> local `run_claude_command` wrapper (`issue_manager.py:140`) -> `_run_claude_base`.
- Read-loop insertion point (codebase-analyzer): the selector loop `while sel.get_map():` (`subprocess_utils.py:502-627`) already checks wall-clock timeout and idle timeout once per iteration before calling `sel.select(timeout=1.0)` (line 528) — a shutdown check inserted alongside those two would fire within ≤1s of a signal using the loop's existing polling cadence, no new blocking primitive needed.
- **RESOLVED by Decision 2 (Proposed Solution).** The finding below is retained for its evidence; the decision is settled — use `_kill_process_group()`, because a bare `.kill()` orphans the Task/Workflow grandchildren that `start_new_session=True` places in the child's process group.
- Contested convention — kill mechanism (codebase-pattern-finder): the issue's own Proposed Solution requires routing through `_kill_process_group()` (process-group SIGTERM/SIGKILL escalation, `subprocess_utils.py:311-344`). But the only existing precedent for "external signal handler reaches into an active `Popen` and kills it" — `ll-loop`'s `_loop_signal_handler` (`cli/loop/_helpers.py:123-174`) — calls bare `proc.kill()` directly on the `Popen` (single process, not the process group), bypassing `_kill_process_group()` entirely. The two conventions disagree: `_kill_process_group` is used today only for the timeout/idle-timeout paths *inside* `run_claude_command` itself (`subprocess_utils.py:505,516,643`), never from an external signal handler. Whether the SIGINT fix should reuse `_kill_process_group` (as the issue proposes) or follow the `ll-loop` precedent of bare `.kill()` is an open implementation decision, not settled by existing convention.

## Implementation Steps

1. Add a module-level shutdown `Event` to `subprocess_utils` (Decision 1),
   with accessors to set, clear, and read it.
2. Poll it in the `run_claude_command` read loop next to the existing
   wall-clock/idle-timeout checks (`subprocess_utils.py:504-526`); on set,
   kill via `_kill_process_group()` (Decision 2) and return an interrupted
   result distinguishable from a timeout.
3. Have `AutoManager._signal_handler` set the Event in addition to
   `_shutdown_requested` — and make it two-tier, so a second signal forces
   immediate exit (Decision 4), mirroring `_loop_signal_handler`/ENH-2516.
4. Add shutdown checks at the `process_issue_inplace` phase boundaries
   (before Phase 2 `:1251`, before Phase 3 `:1420`) and at the head of
   `run_with_continuation`'s continuation loop (`:348`), returning an
   interrupted result rather than advancing (Decision 3).
5. Ensure the Phase-2-exited-non-zero branch (`:1342-1354`) recognizes an
   interrupt and does not auto-commit a killed session's partial work.
6. Attribute the interrupt as `interrupted` rather than a Phase 2 crash, and
   decide + document whether the interrupted issue stays in
   `attempted_issues` given `mark_attempted` already fired at `:2068`
   (Decision 5).
7. Add the tests listed under Integration Map > Tests.
8. Verify manually: reproduce the Ctrl+C-during-Phase-2 scenario from Steps
   to Reproduce and confirm the run exits promptly, with no Phase 3 spawn,
   and no orphaned `claude` descendants (`pgrep -f claude`).

## Impact

- **Priority**: P2 - Interrupting a long-running automated run is a basic
  usability expectation; not data-loss-critical but a frequent annoyance
  that can force `kill -9` and orphaned processes.
- **Effort**: Medium - The kill wiring alone is small and reuses the existing
  `_kill_process_group` / `os.killpg` machinery, but the fix is not complete
  without the phase-boundary aborts (Decision 3), the two-tier handler
  (Decision 4), and outcome attribution (Decision 5), which touch several
  call sites across `issue_manager.py`.
- **Risk**: Medium - The kill wiring is additive, but a mis-placed
  phase-boundary shutdown check could abort healthy runs, and the
  module-level Event is shared with ll-parallel / sprint / FSM callers of
  `run_claude_command`.
- **Breaking Change**: No

## Root Cause

Three things combine to make the interrupt a no-op for the currently running
work:

1. `AutoManager.__init__` (`scripts/little_loops/issue_manager.py:1738-1739`)
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

### Shutdown must be observed at phase boundaries, not just in the read loop

A fourth factor makes "kill the subprocess" insufficient on its own.
`_shutdown_requested` is read in exactly two places in the entire file:
`issue_manager.py:1951` (outer loop head) and `:1981` (cleanup guard). So even
once SIGINT kills the Phase 2 subprocess, `process_issue_inplace` treats the
resulting `-9` as an ordinary non-zero Phase 2 exit and falls through to
Phase 3 verify (`:1420-1423`), which spawns a **fresh** `claude` subprocess.
From the user's seat the run visibly continues after the interrupt. The
Phase-2-non-zero branch at `:1342-1354` can additionally auto-commit the
killed session's partial work, and `run_with_continuation`'s own loop
(`:348`) has no shutdown check either. Any complete fix therefore has to
propagate the shutdown signal into the phase sequencing, not only into the
subprocess.

## Steps to Reproduce

1. Run `ll-auto` against a project with at least one processable issue.
2. While Phase 2 (implement) is running — i.e. the `claude` CLI subprocess
   is actively streaming — press Ctrl+C.
3. Observe: `[HH:MM:SS] Received signal 2, shutting down gracefully...` is
   printed, but the run does not stop; the current issue's implementation
   subprocess keeps running to completion (or timeout) before the process
   actually exits.

## Acceptance Criteria

1. **Subprocess dies on first signal.** With an active `claude` subprocess in
   Phase 2, a SIGINT causes `run_claude_command` to kill it within ~1s via
   `_kill_process_group()` and return an interrupted result that is
   distinguishable from a wall-clock or idle timeout.
2. **No orphaned descendants.** After the interrupt, no `claude` process from
   the killed process group survives (the group, not just the direct child,
   is reaped — Decision 2).
3. **No further phases run.** An interrupt during Phase 2 does not spawn a
   Phase 3 verify subprocess, and `run_with_continuation` does not start
   another continuation round.
4. **No partial-work auto-commit.** The Phase-2-non-zero branch
   (`:1342-1354`) does not commit a killed session's working tree as if it
   were a completed deliverable.
5. **Second signal forces exit.** A second SIGINT exits immediately rather
   than waiting on any in-progress cleanup or `process.wait()`.
6. **Correct attribution.** The run's recorded outcome for the interrupted
   issue reads as `interrupted`, not as a Phase 2 crash or `system_signal`;
   the behavior of `attempted_issues` under `--resume` is documented and
   tested (Decision 5).
7. **No regression for uninterrupted runs.** Existing `ll-auto`, ll-parallel,
   sprint, and FSM paths through `subprocess_utils.run_claude_command` behave
   identically when no shutdown signal fires; the shared module-level Event
   does not leak state between runs in the same process (it is cleared at run
   start).
8. **Tests.** The cases listed under Integration Map > Tests exist and pass;
   `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-24 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-24T17:23:52 - `8fa6ad25-06d2-4755-aec9-4be3d7428376.jsonl`
- `/ll:ready-issue` - 2026-08-24T16:58:51 - `0f974fac-ad32-471d-97f9-75e34da794da.jsonl`
- `/ll:confidence-check` - 2026-08-24T16:56:17 - `a004c617-912f-49b1-90dd-64ce4fe53f29.jsonl`
- `/ll:confidence-check` - 2026-08-24T16:39:51 - `9960f916-2441-4af1-90fa-4a886fc8f95c.jsonl`
- `/ll:refine-issue` - 2026-08-24T16:21:11 - `e5f4e5f1-003d-4663-97d4-27dbe660784d.jsonl`
- `/ll:format-issue` - 2026-08-24T16:12:01 - `b85ae83c-887b-4e17-9a4e-1911475585d3.jsonl`
- `/ll:capture-issue` - 2026-08-24T16:07:57 - `69c375ac-5c89-44f2-a3fc-ad8aa6520c60.jsonl`
