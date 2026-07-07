---
id: ENH-2522
title: Distinguish user-stop, OS-signal, and OOM in loop termination taxonomy
type: ENH
priority: P3
status: open
discovered_date: 2026-07-07
captured_at: "2026-07-07T16:45:00Z"
discovered_by: capture-issue
labels:
  - enhancement
  - audit
  - diagnostic
  - loop-taxonomy
  - captured
---

# ENH-2522: Distinguish user-stop, OS-signal, and OOM in loop termination taxonomy

## Summary

`ExecutionResult.terminated_by` collapses three distinct failure causes —
user-initiated `ll-loop stop`, kernel/OS signal (SIGKILL, OOM-killer), and
host-pressure abort — into a single `"interrupted"` enum value. This makes
post-run diagnostics blind to the cause: a `.loops/diagnostics/general-task-
20260707T152654Z.md` audit misattributed a 70-minute user-initiated stop with
14/26 DoD checkmarks (genuine progress, just user-stopped) to a kernel OOM
kill, because the runner's `terminated_by: "interrupted"` was the only signal
the loop-specialist agent could read, and its failure-mode taxonomy has no
canonical bucket for either case.

Add `user_stopped` and `system_signal` to the `terminated_by` enum, wire
`cmd_stop` to leave a sentinel that flips the runner's termination tag, and
extend the loop-specialist taxonomy so the next diagnostic classifies
correctly out of the box.

## Motivation

- **The current contract is a heap.** `fsm/types.py:37` lists eight
  `terminated_by` values (`terminal`, `max_steps`, `max_iterations_reached`,
  `timeout`, `interrupted`, `error`, `handoff`, `cycle_detected`) and every
  non-terminal, non-budget-exhaustion, non-handler path collapses onto
  `interrupted`. Three structurally different causes (clean user stop, host
  signal, OS kill) share one label and one logging path — the audit can't
  separate them.
- **The diagnostic that bit us had no way to be right.** `cmd_stop` writes
  `state.status = "interrupted"` directly to disk (lifecycle.py:374, 384)
  *before* sending SIGTERM, with no record of the cause. The runner's
  `loop_complete` event (which would carry the real `terminated_by`) lands
  only on the graceful path; if the LLM subprocess eats SIGTERM and SIGKILL
  arrives first, `state.json` ends up with `status: interrupted` plus
  `last_result.exit_code: -9` — exactly the fingerprint the specialist
  mis-classified as OOM.
- **The taxonomy gap multiplied the error.** `agents/loop-specialist.md:53-66`
  lists eight canonical failure modes; kernel-signal / OOM / user-stop is
  none of them. The specialist silently invented "oom-sigkill" and
  "do-work-timeout-retry" labels in this run's `.md` artifact because there
  was no canonical bucket and no canonical "before claiming OOM, verify the
  user-stop sentinel is absent" rule to fall back on.
- **The fix is small and the failure is recurring.** Three values in an
  enum, one sentinel-write in `cmd_stop`, one runner-side check in
  `request_shutdown()`, one check-table row in the specialist agent, one
  regression test. Without it, the next 90-minute loop that the user
  `ll-loop stop`s will produce another false-OOM diagnostic.

## Current Behavior

- `ExecutionResult.terminated_by` (`fsm/types.py:37`) accepts only
  `terminal | max_steps | max_iterations_reached | timeout | interrupted |
   error | handoff | cycle_detected`. `cmd_stop` SIGTERMs the process group,
  waits 10 s, escalates to SIGKILL (lifecycle.py:104, 112); the runner's
  signal handler (`cli/loop/_helpers.py:156-172`) calls
  `executor.request_shutdown()`, which the run loop honors via
  `_finish("interrupted")` (executor.py:347-348).
- `cmd_stop` writes `state.status = "interrupted"` directly on disk
  (`cli/loop/lifecycle.py:374, 384`) without emitting a `loop_complete`
  event tagged with the cause. If SIGKILL arrives before the runner's
  `_finish()` runs, `state.json` ends with `last_result.exit_code: -9` and
  no cause-of-death metadata anywhere on disk.
- `agents/loop-specialist.md:53-66` lists eight failure modes that cover
  semantic and structural loop bugs but none cover host signals, kernel
  kills, or explicit user stops. The eight modes: `ambiguous-output`,
  `infinite-cycle`, `premature-termination`, `feature-stubbing`, `drift`,
  `self-evaluation bias`, `evaluator-trivial`,
  `over-escaped-shell-pid-corruption`.
- BUG-685 (related but distinct: `returncode or 0` masks killed process as
  success) and P3-BUG-639 (`ll-loop stop` continues multiple iterations
  after stop) both touch `cmd_stop` mechanics but neither addresses the
  audit-trail gap.

## Expected Behavior

- `ExecutionResult.terminated_by` (and the corresponding `LoopState.status`)
  distinguishes three new values:
  - `user_stopped` — the user ran `ll-loop stop`. A sentinel file
    (`.loops/runs/<run>/user-stop.marker`) was present when the runner's
    signal handler called `request_shutdown()`.
  - `system_signal` — the runner's last action finished with
    `exit_code <= -1` (POSIX-process killed by signal N) and the
    `user-stop.marker` sentinel is *absent* — i.e. the kill came from
    outside the runner (kernel OOM, parent killed, host pressure abort
    pushed past the SIGTERM grace window, etc.).
  - `interrupted` — preserved for Ctrl-C / `KeyboardInterrupt` paths and
    for any future cause that doesn't carry a sentinel. Behavior
    unchanged for existing callers.
- `cmd_stop` writes `.loops/runs/<run>/user-stop.marker` *before* sending
  SIGTERM. The runner's signal handler reads the sentinel on
  `_finish()` and routes the `terminated_by` value accordingly. If the
  runner is SIGKILLed before `_finish()` runs, `ll-loop stop` recovers on
  exit by reading the sentinel from disk and atomically flipping
  `state.status` from "running" to "user_stopped" (not "interrupted").
- The `agents/loop-specialist.md:53-66` failure-mode taxonomy gains two
  rows: `kernel-signal` (`exit_code <= -1`, no sentinel — investigate OS /
  parent / OOM) and `user-stopped` (sentinel present — re-run is the
  remediation). The specialist's pre-attribution checklist gains a rule:
  "before classifying as `kernel-signal`, verify the `user-stop.marker`
  sentinel is absent from the run_dir AND `state.json` was last written
  by a non-`cmd_stop` PID."
- A regression test in
  `scripts/tests/test_cli_loop_lifecycle.py` invokes `cmd_stop` against a
  stub loop with a slow LLM subprocess and asserts:
  (1) `.loops/runs/<run>/user-stop.marker` is non-empty,
  (2) post-run `state.json` shows `terminated_by == "user_stopped"` and
  `status == "user_stopped"`,
  (3) the post-run `events.jsonl` ends with a `loop_complete` event whose
  payload has `terminated_by: "user_stopped"`.

## Proposed Solution

### 1. Enum extension (`fsm/types.py`, `fsm/persistence.py`)

Add to `ExecutionResult.terminated_by` (`fsm/types.py:37`):

```python
terminated_by: str  # "terminal", "max_steps", "max_iterations_reached",
                    # "timeout", "interrupted", "user_stopped",
                    # "system_signal", "error", "handoff", "cycle_detected"
```

Update `fsm/persistence.py:843-905` (`archive_run_only` and the post-block
of `run()`) to map the new values to terminal statuses:

```python
final_status = "completed" if terminated_by == "terminal" else "failed"
if terminated_by in ("max_steps", "max_iterations_reached"):
    final_status = "failed"  # unchanged
if terminated_by in ("user_stopped", "system_signal"):
    final_status = "failed"  # distinct sub-kind, same terminal bucket
if terminated_by == "interrupted":
    final_status = "interrupted"  # unchanged Ctrl-C path
```

The two new values stay co-equal with `interrupted` (same terminal bucket,
`failed`) but the `loop_complete` payload distinguishes them so audit
tooling can read the cause.

### 2. Runner-side routing (`fsm/executor.py:_finish`)

Add a `request_shutdown(reason="interrupted", *, marker_path=None)` overload
on `PersistentExecutor`. When the signal handler (`cli/loop/_helpers.py`)
calls `request_shutdown()`, it reads the `user-stop.marker` if
`marker_path` was provided at registration and selects `terminated_by`
accordingly. The `_finish()` calls at executor.py:348 and 623 currently
hard-code `"interrupted"`; route them through a helper:

```python
def _finish_for_shutdown(self, error=None):
    sentinel = self._user_stop_marker_path  # Path | None
    if sentinel is not None and sentinel.exists():
        return self._finish("user_stopped", error=error)
    last_exit = self.last_result_exit_code  # -9 on SIGKILL
    if last_exit is not None and last_exit <= -1:
        return self._finish("system_signal", error=error)
    return self._finish("interrupted", error=error)
```

Then call `_finish_for_shutdown()` from the two existing call sites
(executor.py:348 in `run()`, executor.py:623 in `_execute_state()`).

### 3. `cmd_stop` sentinel (`cli/loop/lifecycle.py:316`)

At the top of `cmd_stop`, before `_kill_with_timeout`:

```python
import time as _time
_marker = state.run_dir / "user-stop.marker"  # resolved from state
if _marker.parent.is_dir():
    _marker.write_text(
        f"requested_by={os.getlogin() if hasattr(os, 'getlogin') else 'unknown'}\n"
        f"requested_at={_time.time()}\n"
    )
```

The marker lands *before* SIGTERM, so even if SIGKILL races, the next
`ll-loop status` or re-attach sees it. After the kill returns, replace the
`state.status = "interrupted"` write at lifecycle.py:374/384 with a
`state.terminated_by = "user_stopped"` write (and `state.status =
"user_stopped"`).

### 4. Taxonomy extension (`agents/loop-specialist.md:53-66`)

Append two rows to the failure-mode taxonomy table:

| Mode | Signal | Typical fix |
|------|--------|-------------|
| **kernel-signal** | `last_result.exit_code <= -1` (POSIX process killed by signal N: -9 = SIGKILL, -11 = SIGSEGV, -6 = SIGABRT) with no `user-stop.marker` sentinel in the run_dir. Often interleaves with host-pressure / OOM kill; check `dmesg`-equivalent or host memory before defaulting to "needs more memory." | Reduce per-step memory footprint; split the work into smaller `general-task` invocations; raise `host_guard.max_cumulative_subproc_mb` ceiling; rerun. |
| **user-stopped** | `state.status == "user_stopped"` or `.loops/runs/<run>/user-stop.marker` exists. The user ran `ll-loop stop` (typically mid-iteration); the loop got SIGTERM with 10 s grace then SIGKILL. | Re-run with the same `--input`; `resume_check` will land on the first unchecked DoD criterion. No YAML change required. |

Add a rule to the operating guidelines:

> Before classifying `exit_code == -9` as `kernel-signal`, verify (a)
> `.loops/runs/<run>/user-stop.marker` is absent from the run_dir, and
> (b) the last `state.json` write was authored by a PID *outside* the
> current cmd_stop process. If either check fails, classify as
> `user-stopped` instead.

### 5. Tests (`scripts/tests/test_cli_loop_lifecycle.py`)

```python
def test_user_stop_marker_writes_user_stopped_terminated_by(tmp_path):
    """cmd_stop must write user-stop.marker AND land state on 'user_stopped',
    not 'interrupted', so downstream diagnostics read the cause correctly."""
    # Spawn a stub runner that blocks in subprocess.communicate()
    # with a deliberately slow LLM stub (sleep 30s).
    # Invoke cmd_stop via the CLI runner.
    # Wait for kill (≤12s grace + ~3s kill).
    # Assert: marker file exists with non-empty body,
    #         state.status == "user_stopped",
    #         events.jsonl ends with {"event": "loop_complete",
    #                                "payload": {"terminated_by": "user_stopped"}}.
```

Plus a complementary test for `system_signal`: a stub runner that
deliberately exits with `exit_code == -9` mid-action (no sentinel), and
the post-run `state.json` should show `terminated_by == "system_signal"`.

### 6. Schema / docs

Bump the `loop_complete` payload schema in
`docs/reference/schemas/loop_complete.json` (regenerate via
`ll-generate-schemas`) to declare the two new values in `terminated_by`.
Update `docs/reference/API.md#fsm` with the new enum members.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/types.py` — extend `terminated_by` docstring/enum list (line 37)
- `scripts/little_loops/fsm/executor.py` — add `_finish_for_shutdown()`; route the two existing `_finish("interrupted")` calls through it (lines 348, 623)
- `scripts/little_loops/fsm/persistence.py` — extend `archive_run_only()` and the post-block in `run()` to map the two new values (lines 826-905)
- `scripts/little_loops/cli/loop/lifecycle.py` — write sentinel in `cmd_stop` before SIGTERM; replace `state.status = "interrupted"` writes (lines 374, 384) with `state.status = "user_stopped"` and `state.terminated_by = "user_stopped"`
- `scripts/little_loops/cli/loop/_helpers.py` — pass `marker_path` to `register_loop_signal_handlers()` so `request_shutdown()` can read it
- `agents/loop-specialist.md` — append `kernel-signal` and `user-stopped` rows to the failure-mode taxonomy (lines 53-66); add the pre-attribution checklist rule
- `docs/reference/schemas/loop_complete.json` — regenerate via `ll-generate-schemas` to include the two new values
- `docs/reference/API.md` — note the new enum members under `#little_loopstypes`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — every `_finish()` callsite reads the new enum values
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume` and `cmd_status` read `state.status` and `state.terminated_by`; confirm `user_stopped` is in `RESUMABLE_STATUSES`
- `scripts/little_loops/cli/loop/info.py` — `cmd_history`/`cmd_status` rendering if they branch on `terminated_by`
- Any loop YAML that logs `terminated_by` mid-flight (rare; mostly the FSM emits it once)

### Similar Patterns
- BUG-685 (`returncode or 0` masks killed process as success) — same surface area (`exit_code` interpretation), different fix; should be referenced but not closed
- BUG-639 (`ll-loop stop` continues multiple iterations) — historical, fixed; the new sentinel would not regress it
- ENH-2493 (`harness_events` table) — orthogonal: persists *executor* outcomes, not termination causes. The diagnostic problem this ENH addresses complements ENH-2493 (one tells you "what ran," the other tells you "why it stopped")

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py` — `test_user_stop_marker_writes_user_stopped_terminated_by`, `test_kernel_signal_classified_as_system_signal`
- `scripts/tests/test_fsm_executor.py` — `test_request_shutdown_with_marker_writes_user_stopped`, `test_request_shutdown_without_marker_and_signal_exit_code_writes_system_signal`

### Documentation
- `docs/reference/API.md` — extend `ExecutionResult.terminated_by` enum
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — note the new diag-friendly values in the "Reading Loop Output" section if any

### Configuration
- N/A — no config schema change; existing `fsm.*` keys are unaffected

## Acceptance Criteria

- `ExecutionResult.terminated_by` accepts `"user_stopped"` and
  `"system_signal"`; rejecting either (or aliasing them to `"interrupted"`)
  fails the test suite.
- `cmd_stop` writes `.loops/runs/<run>/user-stop.marker` *before* SIGTERM
  and the file is observable on disk even if the runner is SIGKILLed
  before its `_finish()` runs.
- Post-run `state.json` from `cmd_stop` shows `terminated_by == "user_stopped"`
  and `status == "user_stopped"`.
- Post-run `events.jsonl` from `cmd_stop` ends with a `loop_complete` event
  carrying `payload.terminated_by == "user_stopped"` (when the graceful
  path wins) — or `state.json` carries `terminated_by == "user_stopped"`
  via `cmd_stop`'s atomic flip (when SIGKILL raced past `_finish()`).
- A run that ends with `exit_code == -9` *without* a sentinel is tagged
  `"system_signal"`, not `"user_stopped"` or `"interrupted"`.
- The loop-specialist agent's diagnostic artifact for a user-stopped run
  classifies the termination as `user-stopped` and recommends re-run
  rather than as `kernel-signal` recommending more memory.
- The two regression tests pass under
  `python -m pytest scripts/tests/`.
- `ll-generate-schemas` emits an updated `loop_complete.json` that
  includes the two new enum values.

## Sources

- `.loops/diagnostics/general-task-20260707T152654Z.md` (2026-07-07) —
  the misattributed OOM diagnostic this ENH is designed to prevent
- `autodev-bug2501-kill-analysis.md` (referenced in ENH-2504 sources) —
  sibling pattern of diagnostic gaps caused by missing audit detail
- BUG-685 — `returncode or 0` masks killed process as success; same
  signal-exit-code surface, different mechanism
- BUG-639 — historical `ll-loop stop` continues multiple iterations; the
  sentinel approach in this ENH is a more durable remediation

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/API.md` | `ExecutionResult.terminated_by` enum; `LoopState.status` values |
| `docs/ARCHITECTURE.md` | FSM event taxonomy (`loop_complete` payload shape) |
| `docs/development/TROUBLESHOOTING.md` | "Loop exited with -9" debug path should reference the new diagnostic route |
| `agents/loop-specialist.md` | The taxonomy this ENH extends |

## Status

**Open** | Created: 2026-07-07 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-07T16:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
