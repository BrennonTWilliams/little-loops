---
id: ENH-2514
title: ll-loop should flush events.jsonl / state.json on forced termination
type: ENH
status: done
priority: P2
decision_needed: false
implementation_order_risk: true
captured_at: '2026-07-07T06:36:33Z'
discovered_date: '2026-07-07'
discovered_by: audit-loop-run
relates_to:
- BUG-2501
- BUG-2513
labels:
- loops
- fsm
- ll-loop
- audit-trail
- observability
confidence_score: 90
outcome_confidence: 72
score_complexity: 14
score_test_coverage: 19
score_ambiguity: 19
score_change_surface: 20
size: Very Large
completed_at: '2026-07-07T09:50:24Z'
---

# ENH-2514: ll-loop should flush events.jsonl / state.json on forced termination

## Summary

`ll-loop` writes the run history folder (`events.jsonl`, `state.json`) only on
graceful exit. When the BUG-2501 `autodev` run was killed
(`.loops/runs/autodev-20260706T212035/`), `/ll:audit-loop-run`'s hard pre-flight
gate refused to emit any verdict because there was no `events.jsonl` to read — the
FSM-level failure mode had to be reconstructed indirectly from host-CLI session
logs (see BUG-2513).

## Motivation

Discovered during the BUG-2501 kill analysis; this is the structural cause of
the unresolvable residual uncertainty there (the audit could not distinguish
the exact `refine_current` exit branch that fired because the FSM event log
was missing). Fixing this makes future killed-run audits possible without
session-log archaeology.

User kills are common; crashes are rare. Optimizing the archive path for
graceful exit only means the most common termination case produces zero audit
evidence.

## Current Behavior

`ll-loop run` writes the run history folder (`events.jsonl`, `state.json`) only
on graceful exit. A user-initiated SIGINT/SIGTERM bypasses that write, leaving
the run directory with only scratch files. SIGKILL cannot be trapped. No FSM
event log for the killed run exists at all.

### Codebase Research Findings

_Added by `/ll:refine-issue` — corrections to current-behavior description based on codebase analysis:_

The framing above is partially inaccurate. The actual current behavior, verified against the code:

- **Per-event append IS in place.** `StatePersistence.append_event`
  (`scripts/little_loops/fsm/persistence.py:425`) opens the events file with
  `open(self.events_file, "a", encoding="utf-8")`, writes one JSON line, and
  closes. Closing the file drains Python's user-space buffer to the OS, so
  the bytes reach the kernel page cache after every event. What is NOT in
  place is `f.flush()` + `os.fsync(f.fileno())` after the write — the kernel
  page cache itself is not forced to disk. SIGKILL (which Python cannot
  trap) still loses any pending transitions because the OS-level buffer
  hasn't been flushed.
- **First SIGINT DOES trigger a graceful archive.** `_loop_signal_handler`
  (`scripts/little_loops/cli/loop/_helpers.py:78`) on the first signal sets
  `_loop_shutdown_requested = True` (line 98), calls
  `_loop_executor.request_shutdown()` (line 101), which sets
  `FSMExecutor._shutdown_requested = True` (executor.py:331). The executor
  checks this flag at the top of its main loop (executor.py:346-348) and
  returns `self._finish("interrupted")` (line 348). `_finish` (line 2269)
  emits a `loop_complete` event with `terminated_by="interrupted"`, which
  triggers `_save_state` via `_handle_event`'s gating
  (`event_type in {"state_enter", "loop_complete", "baseline_complete"}`,
  persistence.py:714). Control then returns to `PersistentExecutor.run`
  (persistence.py:811), which calls `save_state` (line 850) and
  `archive_run` (line 852). So a single Ctrl-C DOES archive the run.

- **The real gap is the SECOND SIGINT force-exit path.** When
  `_loop_shutdown_requested` is already `True` (i.e. the user hit Ctrl-C
  twice), the handler at `_loop_signal_handler` (lines 87-97) skips the
  graceful path entirely and calls `sys.exit(1)` (line 97) directly.
  No `save_state`, no `archive_run`. The only filesystem write on this path
  is the PID-file `unlink` (line 88). This is the gap that surfaces in
  `/ll:audit-loop-run`'s pre-flight gate (BUG-2501 / BUG-2513).

- **`atexit` does not fire on SIGKILL.** `_cleanup_pid` is registered via
  `atexit.register` (`run.py:315`, `lifecycle.py:460`), but `atexit` only
  fires on graceful Python exit (including `sys.exit`), not on
  `os._exit` and not when the process is killed by SIGKILL. So even if the
  atexit hook attempted archive, it would not help in the SIGKILL case.

## Expected Behavior

After the fix:

- After SIGINT/SIGTERM to a running `ll-loop run`, the run directory contains
  a readable `events.jsonl` and `state.json` sufficient for
  `/ll:audit-loop-run` to proceed past its pre-flight gate.
- After SIGKILL, `events.jsonl` contains all transitions completed before the
  signal (partial trail, not empty).
- A pytest under `scripts/tests/` runs a short loop, sends SIGINT, and asserts
  the archive is present and parseable.
- No regression to the existing graceful-exit archive path.

## Proposed Solution

Either (or both):

- **Signal-flush**: trap SIGTERM/SIGINT in the loop runner and treat
  user-initiated termination as a graceful exit — final `state.json` write plus
  history-folder archive before exiting. SIGKILL cannot be trapped, so document
  that `ll-loop run` should be run under a supervisor / in a detachable session
  and that Ctrl-C (SIGINT) now archives cleanly.

> **Selected:** Signal-flush — modify `_loop_signal_handler` second-SIGINT branch (`_helpers.py:97`) to invoke the archive path before `sys.exit(1)`, closing the gap where the second Ctrl-C currently bypasses every durability step.

- **Incremental append**: append one record to `events.jsonl` per FSM transition
  rather than buffering to exit. A hard kill then leaves a partial-but-usable
  trail instead of an empty folder. This also covers SIGKILL, which trapping
  cannot.

> **Selected:** Incremental append — add `f.flush()` + `os.fsync(f.fileno())` per event in `StatePersistence.append_event` (`persistence.py:425`) plus the sister append-only writers (`usage.jsonl`, `messages.jsonl`, `meta-eval.jsonl`) so the kernel page cache is forced to disk; covers SIGKILL where the signal trap cannot.

Incremental append is the more robust of the two (survives SIGKILL); the signal
trap additionally ensures `state.json` and the run's history archive are complete
on the graceful/SIGINT path.

## Implementation Steps

1. Locate current flush points in `scripts/little_loops/fsm/executor.py`
   (likely inside `FSMExecutor.execute`) — confirm `events.jsonl` is buffered
   until exit rather than flushed per transition.
2. Switch `events.jsonl` from buffered-to-exit to append-per-transition
   (open with `O_APPEND`, `flush()` after each record, or `fsync` per event).
3. Register SIGTERM/SIGINT handlers in `LoopRunner.run()` (or
   `scripts/little_loops/cli/loop/_helpers.py`) that invoke the same archive
   path as graceful exit before raising `SystemExit`.
4. Document the SIGKILL limitation in `ll-loop run --help` and in
   `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (recommend supervisor / detachable
   session for hard-kill safety).
5. Add a pytest under `scripts/tests/` exercising the SIGINT path (spawn a short
   loop in a subprocess, send SIGINT, assert archive exists and parses).
6. Add a pytest covering incremental append (verify mid-execution reads show a
   partial trail before exit completes).

### Codebase Research Findings

_Added by `/ll:refine-issue` — implementation-step refinements based on codebase analysis:_

**Step 1 clarification**: `append_event` (`scripts/little_loops/fsm/persistence.py:425`) is ALREADY per-call (open → write → close). The change is NOT switching from buffered-to-exit to append-per-transition. The remaining durability gap is:
- No `f.flush()` after the write call (line 432)
- No `os.fsync(f.fileno())` after the flush

Update step 1 to: "Locate `append_event` at `scripts/little_loops/fsm/persistence.py:425` — it already opens/closes per call (Python flushes user-space on close). Add `f.flush()` and `os.fsync(f.fileno())` after the write so the kernel page cache is forced to disk."

**Step 2**: Sister append-only writers that need the same flush+fsync treatment:
- `_handle_event` `usage.jsonl` path (persistence.py:696-697)
- `_handle_event` `messages.jsonl` path (persistence.py:710-711)
- `_write_meta_eval_entry` (persistence.py:776-777)

These are inside `_handle_event` (called from `FSMExecutor._emit` line 1978), so adding flush+fsync to all three sites keeps parity with `events.jsonl`.

**Step 3 clarification**: `register_loop_signal_handlers` (`_helpers.py:146`) is ALREADY wired at:
- `scripts/little_loops/cli/loop/run.py:494` (`cmd_run`)
- `scripts/little_loops/cli/loop/lifecycle.py:560` (`cmd_resume`)

The change is NOT registering new handlers — it's modifying the existing `_loop_signal_handler` force-exit branch (line 97) to invoke the archive path before `sys.exit(1)`.

Concretely, the change at `_loop_signal_handler` line 97 should:
1. Call `_loop_executor._finalize_or_archive()`-equivalent — but `_finalize_run` does NOT exist as a named symbol. The equivalent is the post-block inside `PersistentExecutor.run` (persistence.py:825-852). Either extract that block into a method on `PersistentExecutor` (e.g. `_finalize_run()`) that takes a `terminated_by` arg, OR add a new `archive_only()` public method that wraps just the `save_state` + `archive_run` calls so the signal handler can call it without re-entering the executor.
2. Then `sys.exit(1)`.

This must be safe under signal-handler re-entrancy: do NOT mutate `self._shutdown_requested` (already True), do NOT print to stderr after invoking archive (the existing `print(colorize(...))` at line 96 is fine because it runs before the archive call).

**Step 4**: The `ll-loop run --help` text is generated from the `@click.command` decorators in `scripts/little_loops/cli/loop/run.py` — no docstring/option text to update directly. The signal-handling caveat belongs in the help text for `cmd_run` (around line 90-300) and in `docs/reference/CLI.md` (line 700, 706, 724 — already mentions Ctrl-C resumability).

**Step 5 — real-subprocess SIGINT test** (NET-NEW ground):
Existing tests use the direct-call idiom (`_loop_signal_handler(signal.SIGINT, None)`). A true subprocess test needs:
1. Spawn `ll-loop run <short-loop> --foreground-internal` via `subprocess.Popen` (NOT `subprocess.run` — needs to keep running so the test can deliver SIGINT).
2. Poll `.loops/running/<loop>.pid` until the PID file appears OR poll the run dir for `events.jsonl`.
3. `os.kill(pid, signal.SIGINT)`, then `proc.wait(timeout=10)`.
4. Assert `<run_dir>/state.json` exists AND parses (use `json.loads(state.json.read_text())` to validate).
5. Assert `<run_dir>/events.jsonl` exists AND contains ≥1 `loop_start` event.
6. Assert `.history/<run_id>-<loop_name>/events.jsonl` was archived (the audit-trail deliverable).
7. Clean up: `proc.kill()` if still alive after timeout, `tmp_path` fixture handles dir cleanup.

Template at `scripts/tests/test_hooks_integration.py:56-130` (subprocess.run with shell-scripts, no signal involved) — adapt the spawn-and-poll shape but add signal delivery.

**Step 6 — partial-trail test**:
This can be a unit test (no subprocess needed):
1. Construct `StatePersistence` with a `tmp_path`-backed `running_dir`.
2. Call `append_event({"event": "loop_start", ...})` 3 times.
3. Without closing the persistence object, use a separate file descriptor to `open(events_file, "r")` and read — assert ≥3 lines visible (proves per-call open/close is already in place, validates the existing behavior, regression-guard for the new flush+fsync).
4. Add a parallel test that asserts `f.flush()` was called (mock the file object) and `os.fsync` was called (mock the fileno).

Place new tests in `scripts/tests/test_fsm_persistence.py` alongside `TestAppendEvent` (line 308) and `TestArchiveRun` (line 409).

## API/Interface

No public CLI surface changes. Internal contract:

- Signal trap: SIGTERM/SIGINT handlers in `LoopRunner` invoke the same archive
  code path as graceful exit before terminating the process.
- `events.jsonl` write semantics change from "buffered until exit" to
  "flush-per-record" (open with `O_APPEND`, `flush()` after each write).

### Codebase Research Findings

_Added by `/ll:refine-issue` — clarifications based on codebase analysis:_

- `_finalize_run` is referenced in this issue but does NOT exist as a named
  symbol in the codebase. The equivalent is the post-block inside
  `PersistentExecutor.run` (`scripts/little_loops/fsm/persistence.py:825-852`):
  - Compute `final_status` from `result.terminated_by` (lines 825-834)
  - `self.persistence.save_state(final_state)` (line 850)
  - `self.persistence.archive_run(run_dir=...)` (line 852)
- Recommended refactor: extract that block into a public method on
  `PersistentExecutor` (e.g. `finalize_run(terminated_by: str)` or
  `archive_run_only()`) so `_loop_signal_handler` can call it without
  re-entering `executor.run()`. This also makes the force-exit path testable
  in isolation without a full subprocess harness.
- Signal-handler-safe API: the new method must be reentrancy-safe — it can be
  invoked from a SIGINT handler at any point in the executor's life cycle.
  Avoid mutating executor state; only call `save_state` and `archive_run`.
- `events.jsonl` write contract: the existing per-call open/close at
  `append_event` (persistence.py:425) is already correct for userspace
  durability. The new contract adds `f.flush()` + `os.fsync(f.fileno())`
  after each write to force kernel-level durability. Do NOT change
  `open(mode="a")` to `os.open(O_APPEND)` — Python's text-mode `"a"` already
  uses `O_APPEND` at the syscall level.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py` — switch `events.jsonl` writes from
  buffered-to-exit to flush-per-transition in `FSMExecutor.execute`.
- `scripts/little_loops/cli/loop/_helpers.py` — register SIGTERM/SIGINT handlers
  that invoke the existing archive path.
- `scripts/little_loops/cli/loop/run.py` (or equivalent entry point) — ensure
  signal handlers are installed before the runner starts and removed on exit.

### Dependent Files (Callers/Importers)

- `/ll:audit-loop-run` skill — depends on `events.jsonl` existing; its pre-flight
  gate currently blocks on missing file. This fix unblocks it.
- `ll-loop diagnose-evaluators` / `ll-loop calibrate-budget` — consume
  `events.jsonl`.

### Similar Patterns

- Other long-running subprocesses (`ll-sprint`, `ll-parallel`) — out of scope
  here but worth noting as a follow-up pattern.

### Codebase Research Findings

_Added by `/ll:refine-issue` — similar patterns in-scope (orchestrator, lifecycle):_

- `scripts/little_loops/parallel/orchestrator.py:188-196` — `try/except
  KeyboardInterrupt / finally: self._cleanup(); self._restore_signal_handlers()`.
  The `finally` block is the precedent for "centralized post-signal cleanup"
  that ENH-2514 needs in the force-exit branch. The orchestrator's
  `_setup_signal_handlers` / `_restore_signal_handlers` pair (lines 198-208)
  also saves and restores the original SIGINT/SIGTERM handlers — currently
  `_loop_signal_handler` does NOT save originals, which means handlers leak
  across `cmd_run` / `cmd_resume` invocations within the same Python process.
  For ENH-2514, this is fine because each CLI invocation is its own process,
  but worth flagging for any future in-process reuse.
- `scripts/little_loops/cli/loop/lifecycle.py:316-375` (`cmd_stop`) — when
  stopping a backgrounded loop, sets `state.status = "interrupted"` and calls
  `persistence.save_state(state)` (line 375) directly after sending SIGTERM
  via `_kill_with_timeout`. This is the orchestration-side analogue of "force
  exit also writes state" — the in-process handler can follow the same
  pattern by calling a refactored `PersistentExecutor.archive_run_only()`.
- `scripts/little_loops/cli/loop/lifecycle.py:87-127` (`_kill_with_timeout`) —
  SIGTERM → poll → SIGKILL escalation via `os.killpg`. Applies to `cmd_stop`
  (sending signal to a backgrounded process), NOT directly to ENH-2514's
  in-process self-signal handler.
- `scripts/little_loops/cli/loop/lifecycle.py:116` (`_signal_process_group`) —
  lower-level helper called by `_kill_with_timeout`. Sends a signal to a
  process group via `os.killpg(pgid, sig)` with fallback to `os.kill(pid, sig)`
  on Windows (where `os.killpg` is unavailable). Swallows `ProcessLookupError`
  / `PermissionError` silently. Useful reference for the in-process signal
  handler's defensive coding (call `archive_run` inside `try/except OSError`).
- **`scripts/little_loops/cli/sprint/run.py:101` (`_sprint_signal_handler`)** —
  sister pattern with the **same** two-strike + `sys.exit(1)` gap. First
  signal sets `_sprint_shutdown_requested = True` and prints "Shutdown
  requested, will exit after current wave..."; second signal `sys.exit(1)`.
  Out of scope for ENH-2514 (sprint orchestration, not FSM loop), but the
  structural symmetry means a future ENH should mirror the fix in
  `_sprint_signal_handler` too. Flag for backlog grooming.
- **`scripts/little_loops/cli/sprint/run.py:60-88` (`_run_with_timeout` SIGALRM)** —
  save/restore pattern for signal handlers in a `try/finally`:
  ```python
  prev_handler = signal.signal(signal.SIGALRM, _timeout_handler)
  signal.alarm(max_seconds)
  try:
      return process_issue_inplace(...)
  finally:
      signal.alarm(0)
      signal.signal(signal.SIGALRM, prev_handler)
  ```
  This is the inverse pattern of `_loop_signal_handler`'s leak (which
  installs but never restores). Worth modeling `cmd_run` after when wiring
  `register_loop_signal_handlers` — install at executor start, restore in
  `finally` before `executor.close_transports()` runs.
- **`scripts/little_loops/parallel/worker_pool.py:240-260` (`_shutdown`)** —
  real-subprocess SIGTERM escalation pattern, useful template for the
  net-new `subprocess.Popen` + `os.kill(pid, SIGINT)` test:
  ```python
  process.terminate()                    # = os.kill(pid, SIGTERM)
  try:
      process.wait(timeout=5)
  except subprocess.TimeoutExpired:
      process.kill()                     # = os.kill(pid, SIGKILL)
      process.wait(timeout=2)
  ```
  This is the established idiom for graceful→forced shutdown on subprocess
  objects in this codebase — preferable to hand-rolled `os.killpg` in tests.
- **`scripts/little_loops/issue_manager.py:1185-1196` + `_process_all:1325-1333`** —
  third signal-handler pattern: set-only flag in handler, `try/except
  Exception / finally: self.event_bus.close_transports()`. The `finally`
  checks `_shutdown_requested` and skips redundant cleanup if shutdown is
  in progress. Good precedent for "centralized teardown that respects
  shutdown state."

### Codebase Research Findings (Round 2)

_Added by `/ll:refine-issue` (re-research 2026-07-07) — durability-side gaps surfaced by 3-agent pass:_

- **`archive_run` does NOT copy `usage.jsonl` or `messages.jsonl` to `.history/`** —
  verified at `scripts/little_loops/fsm/persistence.py:463-513`:
  ```python
  if has_state:     shutil.copy2(self.state_file,  archive_dir / "state.json")
  if has_events:    shutil.copy2(self.events_file, archive_dir / "events.jsonl")
  if self.meta_eval_file.exists():
                    shutil.copy2(self.meta_eval_file, archive_dir / "meta-eval.jsonl")
  if run_dir is not None and (summary_src := run_dir / "summary.json").exists():
                    shutil.copy2(summary_src, archive_dir / "summary.json")
  ```
  `usage.jsonl` and `messages.jsonl` only survive via the live `run_dir`.
  For ENH-2514, this is a **design implication**: if the kill recovery
  audit (`/ll:audit-loop-run`) needs token-usage or message history from a
  killed run, it must read from `<run_dir>/usage.jsonl` directly — not from
  `.history/`. Consider whether to extend `archive_run`'s copy list to
  include these (in scope for ENH-2514? — implementation-step decision).
- **`archive_run` return type is `Path | None`** — returns `None` when
  neither `state.json` nor `events.jsonl` exists. The new `finalize_run()`
  method should propagate this so callers know whether the archive actually
  landed. Current callers at `persistence.py:852` discard the return value.
- **`archive_dir.mkdir(exist_ok=True)` + `shutil.copy2` rely on the page cache**
  — neither call does an `os.fsync` on the destination directory entry or the
  destination file contents. For the audit-trail guarantee, the per-event
  `flush+fsync` on `events.jsonl` is sufficient (the bytes are durable on
  the source side before `copy2` reads them). For belt-and-suspenders, an
  `os.fsync(archive_dir)` after the copies is possible but out of scope.
- **PID file is deleted TWICE on second-SIGINT path** — line 88 in
  `_helpers.py` calls `_loop_pid_file.unlink(missing_ok=True)`, then
  `sys.exit(1)` triggers `atexit._cleanup_pid` (registered at `run.py:318`
  and `lifecycle.py:463`) which calls the same `unlink(missing_ok=True)`.
  Idempotent and harmless — `missing_ok=True` swallows the second error —
  but worth knowing if any test asserts the PID file is missing for a
  specific reason (e.g. via a mock that counts calls).
- **`os.fsync` is genuinely first usage** — confirmed by grep: zero matches
  in `scripts/little_loops/`. `.flush()` is used in `_TeeWriter.flush()`
  (`_helpers.py:70-72`), `mcp_call.py:87`, and `fsm/runners.py:380`, all of
  which are stream-flushes (user-space → kernel) not fsyncs (kernel →
  disk). The new persistence change introduces the first `os.fsync` in
  the codebase; consider an inline comment to flag the durability semantic
  for future readers.

### Codebase Research Findings (Round 3)

_Added by `/ll:refine-issue --full-rewrite` (2026-07-07) — stale-run reconciliation paths, existing test surface, atomic-write consolidation opportunity:_

- **Stale-run reconciliation is the existing delayed-archive path.** The
  current issue framing implies "the audit trail is NEVER recoverable for killed
  runs." This is partially incorrect. Two read-side self-heal paths exist:
  - `_reconcile_stale_running` (`scripts/little_loops/fsm/persistence.py:160`)
    — flips `running` → `interrupted` when the PID is provably dead, then calls
    `persistence.save_state(state)` (line 181). Called from `cmd_status` /
    `list_running_loops`.
  - `_reconcile_stale_runs` (`scripts/little_loops/fsm/persistence.py:523`) —
    at startup, archives files in `.running/` belonging to dead processes via
    `persistence.clear_all()` (line 573) → `archive_run()` (line 517) before
    clearing.

  So a killed run's events/state **DO** land in `.history/`, but only when the
  **next** `ll-loop run` startup reconciles the stale `.running/` files. Until
  then, the audit-trail deliverable lives only in
  `.running/<stem>.state.json` and `.running/<stem>.events.jsonl` (and only if
  those were flushed before the kill — the precise gap ENH-2514 closes for
  SIGKILL). For the BUG-2501 audit case (audit-loop-run called immediately
  after the kill, before any new `ll-loop run`), the reconciliation path does
  not help. This refines the issue's Motivation: the gap is "audit-trail
  recovery is **deferred to next startup**, not absent" — SIGKILL still loses
  events not yet flushed to `.running/`.

- **`TestSignalHandlingPersistence` already exists** at
  `scripts/tests/test_fsm_persistence.py:1896` — the prior round's
  recommendation ("new tests should land at line 308 alongside
  `TestAppendEvent`") is suboptimal. Signal-driven durability tests belong in
  this existing class, which already pairs signal handling with persistence
  concerns. Verify by reading `TestSignalHandlingPersistence` (line 1896
  onward) before placing new tests.

- **`TestReconcileStaleRuns` already exists** at
  `scripts/tests/test_fsm_persistence.py:2670` — covers the
  `_reconcile_stale_runs` path. Useful for asserting that `archive_run`
  survives the kill→restart→reconcile sequence without ENH-2514 intervention
  (i.e., ENH-2514 only changes the **immediate** audit-trail availability;
  the next-startup reconciliation path is unchanged).

- **`file_utils.atomic_write` shared primitive exists** at
  `scripts/little_loops/file_utils.py:16-32` but `StatePersistence.save_state`
  (`scripts/little_loops/fsm/persistence.py:379`) does NOT use it — it
  re-implements the `tempfile.mkstemp` + `os.replace` pattern inline. Sister
  sites that DO use a similar atomic-write pattern:
  - `scripts/little_loops/state.py:134-155` — `StateManager.save`
  - `scripts/little_loops/fsm/rate_limit_circuit.py:121-134` —
    `RateLimitCircuit._write_atomic`
  - `scripts/little_loops/parallel/orchestrator.py:608-637` — `_save_state`

  **Opportunity (out of scope for ENH-2514 but worth flagging in the issue
  body):** if `atomic_write` were extended with an optional `fsync: bool`
  parameter (defaulting to `True` for high-durability callers), all 5
  sister sites would get kernel-level durability for free. ENH-2514 could
  either:
  1. Inline `f.flush()` + `os.fsync` at the four append-only writers (current
     plan) and leave `state.json` atomic-write as-is (existing race-temp-file
     pattern is already SIGKILL-safe via `os.replace`).
  2. **Refactor** to add an `atomic_write_json(path, data, fsync=True)`
     helper and route both `save_state` and the four JSONL writers through
     it. Larger blast radius but establishes a durable-write idiom for the
     whole codebase.

  Recommendation: stick with option 1 (inline) for ENH-2514 to keep scope
  tight; file a follow-up issue for option 2 if the pattern is needed
  elsewhere.

- **Sister signal-handler test classes** (established patterns for
  multi-stage handler tests):
  - `scripts/tests/test_sprint.py:585-650` — `TestSprintSignalHandler`
    (mirror of `TestLoopSignalHandler` for sprint runner)
  - `scripts/tests/test_orchestrator.py:213-264` — `TestSignalHandlers`
    (covers `_setup_signal_handlers` / `_restore_signal_handlers`)
  - `scripts/tests/test_orchestrator.py:3173-3176` —
    `test_signal_handler_idempotent` (asserts handler is safe to call
    multiple times — useful template for the new archive-then-exit path,
    which must NOT double-archive if the user hits Ctrl-C a third time)
  - `scripts/tests/test_issue_manager.py:3070` — direct-call assertion of
    `_shutdown_requested` flag

  These four classes are the established multi-stage signal-handler test
  patterns; new tests for the modified `_loop_signal_handler` second-signal
  branch should match this shape (direct call + reset module globals +
  MagicMock executor + idempotency variant).

- **`test_state.py:560-620` (`TestStateManagerAtomicSave`)** — concrete
  precedent for "patch `os.replace` to count calls and simulate failure":
  ```python
  def test_save_uses_os_replace(self, temp_state_file: Path, mock_logger: MagicMock) -> None:
      manager = StateManager(temp_state_file, mock_logger)
      manager.state.phase = "testing"

      replace_calls: list[tuple[str, str]] = []
      import os as _os
      original_replace = _os.replace

      def capture_replace(src: str, dst: str) -> None:
          replace_calls.append((src, str(dst)))
          original_replace(src, dst)

      with patch("os.replace", side_effect=capture_replace):
          manager.save()

      assert len(replace_calls) == 1, "os.replace must be called exactly once"
  ```

  Companion `scripts/tests/test_ll_issues_atomic_write.py:15-55` uses the
  same shape to assert atomic-rename semantics. Use this pattern for new
  tests that verify `os.fsync` is called per `append_event` invocation
  (mock `os.fsync` and `f.flush`, count calls, assert exactly once per
  write).

- **`fsm/runners.py:380` calls `sys.stdout.flush()`** — the only other
  `.flush()` site in the codebase besides `_TeeWriter.flush()` and
  `mcp_call.py:87`. Confirmed by the pattern-finder that the ENH-2514
  fsync change is the first `os.fsync` in `scripts/little_loops/`; consider
  an inline comment at the call site explaining the durability semantic
  (kernel page cache → disk) for future readers unfamiliar with the
  `flush()` vs `fsync()` distinction.

### Tests

- New pytest under `scripts/tests/` exercising the SIGINT path on a short loop.
- New pytest covering incremental append (partial trail on mid-exit read).

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete test-file anchors based on codebase analysis:_

- `scripts/tests/test_cli_loop_background.py:13-134` — `TestLoopSignalHandler`
  class is the existing direct-call test surface. New unit tests for the
  modified `_loop_signal_handler` should add a method here (e.g.
  `test_second_signal_archives_before_exit`) that:
  1. Sets `self.helpers._loop_shutdown_requested = True` (precondition).
  2. Patches `archive_run` to a `MagicMock`.
  3. Wraps the second-signal call in `pytest.raises(SystemExit)`.
  4. Asserts `archive_run.assert_called_once()`.
  5. Restores globals in `teardown_method` (lines 32-37).
- `scripts/tests/test_fsm_persistence.py:308` — `TestAppendEvent`. New
  flush/fsync tests should land here. Mock the file object to assert
  `f.flush()` and `f.fileno()` (then `os.fsync` on the fileno mock) are
  called per `append_event` invocation. Pattern-finder confirmed
  `os.fsync` does NOT currently appear anywhere in `scripts/little_loops/`
  — this introduces the first usage.
- `scripts/tests/test_fsm_persistence.py:409` — `TestArchiveRun`. New
  "archive-on-force-exit" tests should land here. Mock the executor's
  signal-handler attachment, invoke the force-exit branch, and assert
  `archive_run` was called.
- **Real-subprocess + `os.kill(pid, SIGINT)` test** — does NOT exist in
  `scripts/tests/`. This is net-new ground. Recommended approach (see
  Implementation Step 5 Codebase Research Findings):
  - Place in a new file `scripts/tests/test_fsm_signal_integration.py`
    (alongside `test_signal_detector.py` which is the closest family
    member).
  - Use `subprocess.Popen` (NOT `subprocess.run`) to keep the child alive.
  - Poll `.loops/running/<loop>.pid` until present, then `os.kill(pid, signal.SIGINT)`.
  - Assert `state.json` and `events.jsonl` exist in both the running dir
    AND `.history/<run_id>-<loop_name>/` after `proc.wait(timeout=10)`.

### Documentation

- `docs/reference/API.md` — note signal handling and SIGKILL limitation in the
  `ll-loop run` section.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — update `ll-loop run` guidance to
  recommend running under a supervisor / detachable session.
- `ll-loop run --help` — add a short note on signal handling.

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Confirmed persistence write sites** (`scripts/little_loops/fsm/persistence.py`):
- `StatePersistence.append_event` (line 425) — opens with `open(self.events_file, "a", encoding="utf-8")` then writes `json.dumps(event) + "\n"`. Per-call open/close drains Python user-space buffer; **no `f.flush()`, no `os.fsync(f.fileno())`**. Kernel page cache still buffers after function return, so SIGKILL still loses the most recent transition.
- `StatePersistence.save_state` (line 379) — uses `tempfile.mkstemp(dir=..., suffix=".tmp")` (line 393) + `os.fdopen(tmp_fd, "w")` (line 395) + `os.replace(tmp_path, self.state_file)` (line 397). Atomic at the directory-entry level, but contents can be torn on power loss because the temp fd is never fsync'd before the rename.
- Sister append-only writers in the same module follow the same shape with no durability upgrade: `_write_meta_eval_entry` (line 776, `meta_eval_file`), `usage.jsonl` (line 696), `messages.jsonl` (line 710). All are flush-fsync-naive.

**Confirmed signal-handler wiring** (`scripts/little_loops/cli/loop/_helpers.py`):
- `_loop_signal_handler` (line 78) — two-strike pattern:
  - First signal: sets `_loop_shutdown_requested = True` (line 98), prints notice (line 99), calls `_loop_executor.request_shutdown()` (line 101), best-effort `proc.kill()` on action runner subprocess (lines 105-113).
  - Second signal: PID-file `unlink` (line 88), alt-screen reset (line 94), `print("Force shutdown requested")` (line 96), `sys.exit(1)` (line 97). **This is the actual gap** — second SIGINT bypasses every durability step.
- `register_loop_signal_handlers` (line 146) — installs `signal.signal(SIGINT, …)` and `signal.signal(SIGTERM, …)` (lines 161-162). Already wired at:
  - `scripts/little_loops/cli/loop/run.py:494` (`cmd_run` foreground path)
  - `scripts/little_loops/cli/loop/lifecycle.py:560` (`cmd_resume`)

**Confirmed executor/persistence integration** (`scripts/little_loops/fsm/executor.py`):
- `FSMExecutor._emit` (line 1978) — synchronous fan-out to `PersistentExecutor._handle_event` (line 669 in persistence.py), which calls `append_event` for every event and `save_state` only for `event_type in {"state_enter", "loop_complete", "baseline_complete"}` (line 714). Action_start/action_complete/action_output events do NOT trigger `save_state`.
- `FSMExecutor.run` checks `self._shutdown_requested` (line 346-348) at the top of each iteration; on True returns `self._finish("interrupted")` (line 348).
- `FSMExecutor._finish` (line 2269) emits a `loop_complete` event with `terminated_by="interrupted"` payload, which DOES trigger `_save_state` (because of the gating above).

**Confirmed graceful-exit archive path** (`scripts/little_loops/fsm/persistence.py`):
- `PersistentExecutor.run` (line 811) — after `self._executor.run()` returns, computes `final_status` from `result.terminated_by` (lines 825-834), calls `self.persistence.save_state(final_state)` (line 850), then `self.persistence.archive_run(run_dir=...)` (line 852). `archive_run` (line 463) does `shutil.copy2` of `state.json` + `events.jsonl` (+ `meta-eval.jsonl` + `summary.json`) into `<loops_dir>/.history/<run_id>-<loop_name>/`.
- **NOTE**: `_finalize_run` is referenced in the issue but does NOT exist as a named symbol in the codebase. The equivalent is the post-block inside `PersistentExecutor.run` (lines 825-852). Treat any reference to `_finalize_run` in implementation steps as shorthand for that block.

**Run-dir layout creation timing**:
- `running_dir` (parent of `events.jsonl` + `state.json`) is created in `StatePersistence.initialize()` (line 375) BEFORE the first state transition.
- `events.jsonl` is created lazily by the first `append_event` call — typically the `loop_start` event emitted at `FSMExecutor.run` line 342.
- `state.json` first appears on the first `state_enter` event (because that's the gating event type for `_save_state`).
- `run_dir` (where `usage.jsonl`, `messages.jsonl`, `summary.json`, `ab.json` land) is created at `scripts/little_loops/cli/loop/run.py:483` BEFORE the executor is constructed.

**Sister patterns worth modeling after**:
- `scripts/little_loops/parallel/orchestrator.py:188-196` — `try/except KeyboardInterrupt / finally: self._cleanup(); self._restore_signal_handlers()` pattern. The `finally` block is the analogue for "centralized post-signal cleanup" that ENH-2514 needs on the force-exit path.
- `scripts/little_loops/parallel/orchestrator.py:198-208` — `_setup_signal_handlers` / `_restore_signal_handlers` save the original SIGINT/SIGTERM handlers and restore them on exit. ENH-2514's `_loop_signal_handler` does NOT save/restore originals; consider whether `cmd_run` / `cmd_resume` should restore after `run_foreground` returns (currently handlers leak across commands in the same process — likely fine for CLI entry-point scripts but worth flagging).
- `scripts/little_loops/cli/loop/lifecycle.py:87-127` — `_kill_with_timeout` (SIGTERM → poll → SIGKILL escalation via `os.killpg`). This is the orchestration-side kill, not the same-process self-signal handler; applies to `cmd_stop`, not directly relevant to ENH-2514's in-process handler.

**Existing test surface for signal handling** (`scripts/tests/`):
- `test_cli_loop_background.py:13-134` — `TestLoopSignalHandler` class. Direct-call idiom: `self.helpers._loop_signal_handler(signal.SIGINT, None)` followed by module-globals reset in `setup_method` / `teardown_method` (lines 23-46). Second-signal `pytest.raises(SystemExit)` at lines 116-122 is the established pattern for testing force-exit. New tests should build on this class.
- `test_cli_loop_lifecycle.py:799, 811` — calls `_loop_signal_handler` directly with SIGINT in resume tests.
- `test_cli_loop_lifecycle.py:138-198` — `test_stop_with_pid_sends_sigterm_and_waits` patches `os.killpg` and asserts `mock_killpg.assert_any_call(99, signal.SIGTERM)`. Useful template for the orchestration-side caller test (asserts `cmd_stop`-like paths, not directly applicable here).
- **Real-subprocess + `os.kill(pid, SIGINT)` test** — does NOT exist in `scripts/tests/`. Closest prior art is `test_hooks_integration.py:56-130` (subprocess.run with shell-scripts, no signal involved). A new pytest that does subprocess → `os.kill(pid, SIGINT)` → assert archive is net-new ground. See Implementation Step 5.

**Existing pytest targets for persistence**:
- `scripts/tests/test_fsm_persistence.py:308` — `TestAppendEvent` class (≥50 tests covering append semantics, archive semantics, run-history).
- `scripts/tests/test_fsm_persistence.py:409` — `TestArchiveRun` class (11+ `archive_run` tests). New fsync/flush tests should land alongside these.

**Existing precedent for archived-run audit**:
- `scripts/little_loops/cli/loop/lifecycle.py:316-375` (`cmd_stop`) — sets `state.status = "interrupted"` and calls `persistence.save_state(state)` (line 375) directly when sending SIGTERM to a backgrounded run. This is the analogue of "force-exit also archives state" that ENH-2514 needs in the in-process signal handler.

**Issue-premise corrections** (also flagged in `## Confidence Check Notes` below):
- "events.jsonl is buffered until exit" is inaccurate — `append_event` (persistence.py:425) already opens/closes per call. The remaining durability gap is kernel-level buffering (no `flush()`/`fsync()`), not user-space buffering.
- "register SIGTERM/SIGINT handlers in the loop runner" is partially redundant — `register_loop_signal_handlers` is already wired at `run.py:494` and `lifecycle.py:560`. The implementation change is INSIDE the handler (second-signal force-exit branch, line 97), not the registration site.

## Scope Boundaries

- **Out of scope**: handling SIGKILL (cannot be trapped; document the supervisor
  workaround instead).
- **Out of scope**: applying the same flush-per-event pattern to other
  long-running subprocesses (`ll-sprint`, `ll-parallel`, etc.) — separate
  future enhancement.
- **Out of scope**: changes to `/ll:audit-loop-run` beyond relying on the
  now-present `events.jsonl`.
- **In scope**: `ll-loop run` only (not the wider `loops/` runtime).

## Impact

- **Priority**: P2 — Audit-trail gap surfaces only on killed runs; current
  `audit-loop-run` workaround (session-log archaeology) is feasible but slow
  and error-prone (see BUG-2501 / BUG-2513 history).
- **Effort**: Medium — touches FSM executor + signal handling. Incremental
  append is a small change to the write site; signal-trap interaction with
  Python subprocess / `os.fork` needs care.
- **Risk**: Low — additive (signal trap + flush-per-event); no change to
  graceful-exit path.
- **Breaking Change**: No — strictly improves observability.

## Status

**Decomposed** | Created: 2026-07-07 | Priority: P2 | Decomposed: 2026-07-07

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-07
- **Reason**: Issue too large for single session — score 11/11 (Very Large); spans persistence-layer durability + signal-handler modification + integration tests + docs across 5+ change sites.

### Decomposed Into

- **ENH-2515**: Add per-event flush+fsync at StatePersistence append sites (persistence.py:425 + 3 sister writers; unit tests in test_fsm_persistence.py)
- **ENH-2516**: Wire second-SIGINT force-exit branch to PersistentExecutor archive path (extract `archive_run_only()` method, modify `_loop_signal_handler` second-SIGINT branch, direct-call tests in test_cli_loop_background.py)
- **ENH-2517**: Real-subprocess SIGINT integration test + SIGKILL documentation (new test_fsm_signal_integration.py + docs/reference/API.md + AUTOMATIC_HARNESSING_GUIDE.md)

### Execution Pattern

Partially ordered:
- **ENH-2515** (persistence flush+fsync) and **ENH-2516** (signal-handler archive) are independent and can ship in parallel.
- **ENH-2517** (integration test + docs) is blocked by both ENH-2515 and ENH-2516.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-07_

**Readiness Score**: 79/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 72/100 → MODERATE

### Concerns
- Issue premise is partially inaccurate: `register_loop_signal_handlers` (`scripts/little_loops/cli/loop/_helpers.py:146`) and `_loop_signal_handler` (line 78) already exist and are wired into `run.py:494` and `lifecycle.py:560`. First SIGINT already triggers `executor.request_shutdown()` → graceful `_finish("interrupted")` → `PersistentExecutor._finalize_run()` → `archive_run()` (`scripts/little_loops/fsm/persistence.py:852`). The real remaining gaps are: (a) second-SIGINT force-exit path (`_loop_signal_handler` line 97: `sys.exit(1)` bypasses the archive); (b) SIGKILL data loss in the kernel write buffer.
- `append_event` (`scripts/little_loops/fsm/persistence.py:425`) already opens/closes the file per call, which flushes Python's user-space buffer. The remaining durability gap is kernel-level buffering — no explicit `flush()` or `os.fsync` after each write. "Incremental append" framing overstates the change vs. the current behavior; the meaningful delta is per-event `flush()`/`fsync()` and second-signal archive.
- "Either (or both)" with two approaches (signal-flush vs incremental append) is presented without picking one; the issue notes incremental append is more robust but does not declare it the chosen strategy.

### Outcome Risk Factors
- **Moderate breadth across 5+ change sites**: `fsm/persistence.py` (flush/fsync), `cli/loop/_helpers.py` (second-signal archive before force-exit), `cli/loop/run.py` (already wires signal handlers — likely no change), 2 new pytest files, and 2 doc updates. Each site is local, but coordination across the persistence layer and the signal-handling layer is non-trivial.
- **Tests are co-deliverables**: The new pytest for the SIGINT path (subprocess + signal send + assert archive) is non-trivial to write and must be developed alongside the implementation to verify the contract. Implement the test infrastructure before committing to the persistence-layer change.
- **Open decision: second-SIGINT behavior change** — current handler does `sys.exit(1)` immediately. Fix must decide between (a) archive-then-exit (slower shutdown, but preserves the audit trail) and (b) keep force-exit and rely solely on incremental fsync (faster shutdown, but lost events if SIGKILL fires before next fsync). Resolve before starting.
- **Open decision: flush() vs fsync()** — `flush()` empties Python's buffer to the kernel (fast, but kernel may buffer further); `fsync()` forces the kernel to flush to disk (slow per call, ~1-10ms on SSD, but survives SIGKILL). The chosen strategy affects performance during high-event-rate loops. Resolve before starting.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-07_ (re-check after Selected: tags resolved prior ambiguity)

**Readiness Score**: 89/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 70/100 → MODERATE

### Concerns
- Both signal-flush and incremental append are now "Selected:" in the issue — implementation must execute both, which means coordinating a persistence-layer durability change AND a signal-handler archive change in the same delivery.
- The new pytest for real-subprocess SIGINT is net-new ground; `scripts/tests/test_hooks_integration.py:56-130` is the closest template but does not exercise signal delivery. Subprocess timing, PID-file race conditions, and `tmp_path` cleanup introduce flakiness risk.
- A new public method on `PersistentExecutor` (e.g. `archive_run_only()` or `finalize_run(terminated_by)`) must be extracted from the post-block at `scripts/little_loops/fsm/persistence.py:825-852` so `_loop_signal_handler` can invoke archive without re-entering `executor.run()`. API surface is well-precedented by `cmd_stop`'s `persistence.save_state(state)` direct call (`scripts/little_loops/cli/loop/lifecycle.py:375`).
- The second-SIGINT branch (`_loop_signal_handler` line 97) currently does `sys.exit(1)` immediately; modifying it to call the archive path first introduces signal-handler reentrancy concerns — must NOT mutate executor state and must NOT print to stderr after invoking archive.

### Outcome Risk Factors
- **Multi-site coordination across persistence + signal-handling layers** — 5+ change sites: `fsm/persistence.py` flush/fsync at 4 sister writers (line 425 append_event, 696 usage.jsonl, 710 messages.jsonl, 776 meta-eval.jsonl), `_helpers.py:97` second-signal branch modification, `persistence.py:825-852` method extraction, 2 new pytest files (`test_fsm_persistence.py` additions + `test_fsm_signal_integration.py` net-new), and 2 doc updates (`docs/reference/API.md`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`). Per-site changes are local; coordination is non-trivial.
- **Signal-handler reentrancy risk** — the modified `_loop_signal_handler` runs in a constrained context. Mitigation: invoke archive via a new signal-handler-safe `PersistentExecutor` method; do NOT mutate `_shutdown_requested`; do NOT print to stderr after invoking archive (the existing `print(colorize(...))` at line 96 is fine because it runs before the archive call).
- **`os.fsync()` performance overhead** — per-event `os.fsync()` on `events.jsonl` is ~1-10ms per call on SSD. High-event-rate loops may see noticeable slowdown. Mitigation: consider batching fsync at fixed intervals if performance degrades; benchmark before commit.
- **Subprocess-test flakiness** — real-subprocess SIGINT test (Implementation Step 5) introduces timing-dependent failure modes. Mitigation: poll `.loops/running/<loop>.pid` with a bounded timeout, hard-kill if subprocess exceeds deadline, isolate test in a fresh `tmp_path`.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-07_ (re-check after `--auto`; verified frontmatter and Codebase Research Findings against current source)

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 73/100 → MODERATE

### Concerns
- No new concerns raised. Re-verification confirmed every file:line cited in the issue body — `persistence.py:425` (`append_event`, no `flush`/`fsync`), `_helpers.py:78-97` (two-strike pattern, second-signal `sys.exit(1)` bypasses archive), `_helpers.py:146` (handler registration already wired at `run.py:494` and `lifecycle.py:560`), and the four sister write sites (lines 425, 696, 710, 776). The Selected: tags at issue lines 125 and 132 fully resolve the prior "either (or both)" ambiguity — implementation must execute both the second-signal archive call AND the per-event `flush()`/`fsync()` upgrade.

### Outcome Risk Factors
- **Moderate breadth across 5+ change sites**: `fsm/persistence.py` (`append_event` line 425, sister writers 696, 710, 776), `_helpers.py` second-signal branch (line 97), `persistence.py:825-852` method extraction, 2 new pytest files (`test_fsm_persistence.py` additions + net-new `test_fsm_signal_integration.py`), and 2 doc updates (`docs/reference/API.md`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`). Per-site changes are local; coordination is non-trivial — recommend extracting the `PersistentExecutor.archive_run_only()` API first, then doing the persistence-layer flush/fsync sweep in the same commit, then tests as co-deliverables.
- **`os.fsync()` introduces the first kernel-level durability primitive in the codebase**: zero matches for `os.fsync` in `scripts/little_loops/` (verified). Per-event `os.fsync()` on `events.jsonl` is ~1-10ms on SSD; high-event-rate loops may see noticeable slowdown. Mitigation: consider batching fsync at fixed intervals if performance degrades; benchmark before commit. Add an inline comment at the `append_event` call site flagging the durability semantic for future readers (issue Codebase Research Findings already flagged this).
- **Net-new subprocess + signal delivery test ground**: real-subprocess SIGINT test (Implementation Step 5) does NOT have a sibling in `scripts/tests/`. `test_hooks_integration.py:56-130` is the closest template but does not exercise signal delivery. Implement the test infrastructure (`subprocess.Popen` + `os.kill(pid, SIGINT)` + poll `.loops/running/<loop>.pid`) before committing to the persistence-layer change — tests are co-deliverables.
- **Signal-handler reentrancy**: the modified `_loop_signal_handler` second-SIGINT branch will call the new `PersistentExecutor.archive_run_only()` method (or equivalent). Mitigation: invoke archive inside `try/except OSError` (mirror `_signal_process_group` at `lifecycle.py:116`); do NOT mutate `_shutdown_requested` (already `True`); do NOT print to stderr after invoking archive (the existing `print(colorize(...))` at line 96 runs before the archive call, so it is fine).
- **Performance / scope decisions remain open**: should `flush()` + `fsync()` apply to all four sister writers (events.jsonl, usage.jsonl, messages.jsonl, meta-eval.jsonl) or only events.jsonl? Implementation Step 2 lists all four sites, but the audit-trail deliverable is events.jsonl + state.json — usage.jsonl and messages.jsonl fsync is a heavier cost for an arguably weaker audit guarantee. Resolve during implementation planning.

## Confidence Check Notes

_Added by `/ll:confidence-check --auto` on 2026-07-07_ (re-check; verified every cited `file:line` against current source — no source drift since third pass)

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Concerns
- No new concerns raised. Re-verification confirmed every `file:line` cited in the issue body — `persistence.py:425` (`append_event`, no `flush`/`fsync`), `_helpers.py:78-97` (two-strike pattern, second-signal `sys.exit(1)` bypasses archive), `_helpers.py:146` (handler registration already wired at `run.py:494` and `lifecycle.py:560`), and the four sister write sites (lines 425, 696, 710, 776). The `Selected:` tags at issue lines 125 and 132 fully resolve the top-level approach — implementation must execute both the second-signal archive call AND the per-event `flush()`/`fsync()` upgrade.
- Stale-run reconciliation (`_reconcile_stale_running` at `persistence.py:160`, `_reconcile_stale_runs` at `persistence.py:523`) is the existing deferred-archive path: a killed run's `events.jsonl`/`state.json` land in `.history/` only when the **next** `ll-loop run` reconciles `.running/`. For the BUG-2501 audit case (audit-loop-run called immediately after kill, before any new `ll-loop run`), the reconciliation path does not help — ENH-2514 closes the immediate-availability gap.

### Outcome Risk Factors
- **Moderate breadth across 5+ change sites** (`scripts/little_loops/fsm/persistence.py` flush/fsync at 4 sister writers — line 425 `append_event`, 696 usage.jsonl, 710 messages.jsonl, 776 meta-eval.jsonl; `cli/loop/_helpers.py` second-signal branch at line 97; `fsm/persistence.py:825-852` method extraction; new `scripts/tests/test_fsm_signal_integration.py`; 2 doc updates). Per-site changes are local; coordination across the persistence + signal-handling layers is non-trivial — recommend extracting `PersistentExecutor.archive_run_only()` first, then sweeping the persistence-layer flush/fsync in the same commit.
- **First `os.fsync()` in the codebase** (verified: 0 matches in `scripts/little_loops/`): per-event cost ~1-10ms on SSD; high-event-rate loops may see noticeable slowdown. Mitigation: benchmark before commit; add an inline comment at the `append_event` call site flagging the kernel-cache → disk semantic for future readers (issue Codebase Research Findings already flagged this).
- **Net-new subprocess + signal-delivery test ground**: real-subprocess SIGINT test (Implementation Step 5) requires new test infrastructure in `scripts/tests/`. The spawn-and-poll template at `test_hooks_integration.py:56-130` covers subprocess execution but does not exercise signal delivery. Subprocess timing, PID-file race conditions, and `tmp_path` cleanup introduce flakiness risk. Tests are co-deliverables — develop the test scaffolding before committing to the persistence-layer change.
- **Signal-handler reentrancy**: the modified `_loop_signal_handler` second-SIGINT branch invokes the new `PersistentExecutor.archive_run_only()` method (or equivalent) from a constrained execution context. Mitigation: wrap archive in `try/except OSError` (mirror `_signal_process_group` at `lifecycle.py:116`); do NOT mutate `_shutdown_requested`; do NOT print to stderr after invoking archive (the existing `print(colorize(...))` at line 96 runs before the archive call, so it is fine).
- **Fsync-scope vs. performance trade-off, open at implementation time**: should `flush()` + `fsync()` apply to all four sister writers (events.jsonl, usage.jsonl, messages.jsonl, meta-eval.jsonl) or only events.jsonl + meta-eval.jsonl? Implementation Step 2 lists all four sites, but the audit-trail deliverable is events.jsonl + state.json — usage/messages fsync is a heavier per-event cost for an arguably weaker audit guarantee. Decide during implementation planning; current recommendation is all four for parity.

## Session Log
- `/ll:confidence-check` - 2026-07-07T09:43:10 - `19694ae1-d537-4229-96cc-689eb0791628.jsonl`
- `/ll:refine-issue` - 2026-07-07T09:36:54 - `64931d69-1a24-44a0-a0f4-4a5bb5bd90f9.jsonl`
- `/ll:confidence-check` - 2026-07-07T09:25:25 - `deb3fc62-9850-4309-9d58-b827d3961ba1.jsonl`
- `/ll:refine-issue` - 2026-07-07T09:18:04 - `b1b08ba5-7ccd-4163-b87c-339df31cd9a2.jsonl`
- `/ll:confidence-check` - 2026-07-07T09:05:09 - `05b624e2-d755-4061-baec-2d49fe96b44c.jsonl`
- `/ll:decide-issue` - 2026-07-07T08:57:04 - `78b8d486-e38a-4eae-8eb8-308816fc8f04.jsonl`
- `/ll:refine-issue` - 2026-07-07T08:50:00 - `6ad3c113-46df-48d7-8ef5-f2d05275bb47.jsonl`
- `/ll:format-issue` - 2026-07-07T08:26:30 - `3e01502f-d330-4d73-abee-b4b3e4e3bc6b.jsonl`
- `/ll:confidence-check` - 2026-07-07T08:30:00 - in progress
- `/ll:issue-size-review` - 2026-07-07T06:36:33Z - `fc70cacc-0621-41d5-a7b3-89f8f15d4569.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-07-07
- **Decomposed into**: ENH-2515, ENH-2516, ENH-2517

Work for ENH-2514 is now carried by its child issues; this parent was closed by rn-decompose.
