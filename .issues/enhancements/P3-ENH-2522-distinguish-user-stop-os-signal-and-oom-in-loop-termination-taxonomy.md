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
- `scripts/little_loops/fsm/persistence.py` — extend `archive_run_only()` and the post-block in `run()` to map the two new values (lines 826-905); add `user_stopped` to `RESUMABLE_STATUSES` (line 46)
- `scripts/little_loops/cli/loop/lifecycle.py` — write sentinel in `cmd_stop` before SIGTERM; replace `state.status = "interrupted"` writes (lines 374, 384) with `state.status = "user_stopped"` and `state.terminated_by = "user_stopped"`; update `f"Marked {stem} as interrupted"` log message at line 386
- `scripts/little_loops/cli/loop/_helpers.py` — pass `marker_path` to `register_loop_signal_handlers()` so `request_shutdown()` can read it; add `user_stopped: 1, system_signal: 1` to `EXIT_CODES` (lines 29–37) so the new failure bucket yields the correct shell exit code
- `scripts/little_loops/cli/loop/info.py` — extend `_STATUS_COLORS` (line 88), `display_status` paused branch (line 107), and multi-instance status rendering (line 119) to handle the new statuses
- `scripts/little_loops/cli/logs.py` — extend `scan-failures` outcome buckets at lines 1755–1761 to recognize `user_stopped` and `system_signal`
- `scripts/little_loops/generate_schemas.py` — update the `loop_complete.terminated_by` description string (line 407–408) to enumerate the new values so the regenerated schema reflects them
- `agents/loop-specialist.md` — append `kernel-signal` and `user-stopped` rows to the failure-mode taxonomy (lines 53-66); add the pre-attribution checklist rule
- `docs/reference/schemas/loop_complete.json` — regenerate via `ll-generate-schemas` to include the two new values
- `docs/reference/API.md` — note the new enum members under `#little_loopstypes`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — re-exports `RESUMABLE_STATUSES`, `PersistentExecutor` (lines 47, 50, 127, 129, 209–210); confirm export surface covers new enum values
- `scripts/little_loops/cli/loop/__init__.py` — dispatches `cmd_status`/`cmd_stop`/`cmd_resume`/`cmd_history` (lines 32, 37, 879–885); dispatchers inherit the new status taxonomy automatically
- `scripts/little_loops/cli/loop/run.py` — defines `cmd_history` (line 599); handles `loop_complete` event with `terminated_by` (lines 379–384); calls `register_loop_signal_handlers` (lines 22, 494); registers PID file for `cmd_stop` SIGTERM (line 301)
- `scripts/little_loops/cli/loop/testing.py` — consumes `terminated_by` at line 275; new values flow through
- `scripts/little_loops/cli/logs.py` — `loop_complete`/`terminated_by` handling for `ll-logs scan-failures` outcome buckets (lines 1755–1761)
- `scripts/little_loops/cli/auto.py` — reads `terminated_by` for `ll-auto` orchestration; new values appear in run summaries
- `scripts/little_loops/cli/sprint/run.py` — references `PersistentExecutor` and `terminated_by`
- `scripts/little_loops/cli/parallel.py` — text reference to `terminated_by="stall_detected"` at line 985 (unaffected, but in the same surface)
- `scripts/little_loops/observability/schema.py` — `LoopComplete` event schema referencing `terminated_by` (lines 115–117); confirm generated schema enumerates new values
- `scripts/little_loops/session_store.py` — handles `loop_complete` event (lines 408–409, 462–468); SQLite import path picks up new values transparently
- `scripts/little_loops/transport.py` — `loop_complete` references (lines 137, 1353); transport-level consumers downstream
- `scripts/little_loops/events.py` — `loop_complete` event-type registration
- `scripts/little_loops/generate_schemas.py` — generates `loop_complete` schema with `terminated_by` field (lines 398, 406, 411, 414); update the description string at line 407–408 to enumerate new values
- `scripts/little_loops/fsm/fsm-loop-schema.json` — embedded JSON schema referencing `terminated_by` in description strings (lines 249, 307, 327); descriptions only — no enum constraint at the YAML-block level
- `scripts/little_loops/issue_manager.py`, `scripts/little_loops/cli_args.py`, `scripts/little_loops/extension.py`, `scripts/little_loops/config/automation.py`, `scripts/little_loops/hooks/pre_compact_handoff.py`, `scripts/little_loops/init/tui.py`, `scripts/little_loops/parallel/worker_pool.py`, `scripts/little_loops/subprocess_utils.py`, `scripts/little_loops/fsm/cost_graph.py` — all carry text references to `terminated_by` that pick up the new enum values transparently

### Callers / consumers that need explicit code edits (not just doc updates)
- `scripts/little_loops/cli/loop/info.py` — three branches render `state.status` and treat `"interrupted"` specially:
  - line 88 `_STATUS_COLORS` dict (`"running": "32", "interrupted": "33", ...`): add color entries for `user_stopped` and `system_signal`
  - line 107 `display_status = "paused" if state.status == "interrupted" else state.status`: extend branch so `user_stopped` still displays as `"paused"` (resumable); `system_signal` displays distinctly
  - line 119 multi-instance status rendering: same branching concern as line 107
  - lines 567–575 `status_colors` dict in `_list_archived_runs`: new values fall through to default and read as `"failed"` (acceptable per proposed mapping, but verify)
- `scripts/little_loops/cli/loop/_helpers.py` — `EXIT_CODES: dict[str, int]` at lines 29–37 (`{"terminal": 0, "interrupted": 0, ...}`): add `user_stopped: 1, system_signal: 1` so the new failure bucket yields the correct shell exit code (otherwise `.get()` falls through to default and exits 0)
- `scripts/little_loops/cli/loop/_helpers.py:1590` — `_is_success = result.terminated_by in ("terminal", "interrupted", "handoff")`: new keys fall into the failed-color branch automatically (no code change required); add a comment clarifying the bucket
- `scripts/little_loops/fsm/persistence.py:46` — `RESUMABLE_STATUSES = frozenset({"running", "awaiting_continuation", "interrupted"})`: add `user_stopped` so `cmd_stop`-stopped loops remain resumable; **do not** add `system_signal` (runner died mid-state, resume is unsafe)
- `scripts/little_loops/fsm/persistence.py:847-860` and mirror at lines 897-905 — extend the `terminated_by` → `state.status` mapping in both `archive_run_only()` and the post-block of `run()` to keep them consistent. Add `user_stopped → "failed"`, `system_signal → "failed"` (matches issue §1)
- `scripts/little_loops/cli/loop/lifecycle.py:386` — `logger.success(f"Marked {stem} as interrupted")`: update to `"as user_stopped"` to match the new status write

### Similar Patterns
- BUG-685 (`returncode or 0` masks killed process as success) — same surface area (`exit_code` interpretation), different fix; should be referenced but not closed
- BUG-639 (`ll-loop stop` continues multiple iterations) — historical, fixed; the new sentinel would not regress it
- ENH-2493 (`harness_events` table) — orthogonal: persists *executor* outcomes, not termination causes. The diagnostic problem this ENH addresses complements ENH-2493 (one tells you "what ran," the other tells you "why it stopped")

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**New tests to write** (per Acceptance Criteria §5):
- `scripts/tests/test_cli_loop_lifecycle.py` — `test_user_stop_marker_writes_user_stopped_terminated_by`, `test_kernel_signal_classified_as_system_signal` (mirror `_SPIN_LOOP_YAML` + `_spawn_loop` pattern from `scripts/tests/test_fsm_signal_integration.py:51-165`)
- `scripts/tests/test_fsm_executor.py` — `test_request_shutdown_with_marker_writes_user_stopped`, `test_request_shutdown_without_marker_and_signal_exit_code_writes_system_signal` (mirror `TestSignalHandling` class at line 2846)

**Existing tests that will break and must be updated**:
- `scripts/tests/test_fsm_executor.py:3099` — `test_sigkill_on_next_state_triggers_shutdown`: uses `exit_code=-9`, now routes to `system_signal` via `_finish_for_shutdown` (the test was *describing* the misclassification the issue fixes). Either rename it to assert `system_signal` or split the assertion to keep the routing test and add a new `system_signal` payload assertion.
- `scripts/tests/test_fsm_persistence.py:869, 929` — `test_archive_run_only_saves_state_and_archives` and `test_archive_run_only_always_writes_state_and_archives` use `terminated_by="interrupted_force"`. Unaffected if `interrupted_force` mapping is left as `interrupted` (it's a distinct value from `user_stopped`/`system_signal`); verify the issue's proposed mapping keeps `interrupted_force` in the `interrupted` bucket.
- `scripts/tests/test_fsm_persistence.py:900` — `test_archive_run_only_maps_terminated_by_to_status` parametrized case table: add `("user_stopped", "failed")` and `("system_signal", "failed")` rows. If §1 of the proposed solution also re-maps `max_steps`/`max_iterations_reached` from `interrupted` to `failed`, update those rows too (currently lines 1157, 1182, 1185, 1212, 1216 in `test_final_status_*` rely on the existing `interrupted` mapping).
- `scripts/tests/test_cli_loop_lifecycle.py:135, 166, 200, 235` — `TestCmdStop.*`: flip `mock_state.status == "interrupted"` assertions to `"user_stopped"`; add a sentinel-existence assertion for `.loops/runs/<run>/user-stop.marker`.
- `scripts/tests/test_cli_loop_lifecycle.py:2209, 2232` — `TestCmdStopMultiInstance.test_stop_terminates_all_running_instances` and `test_stop_skips_non_running_instances`: same flip.
- `scripts/tests/test_cli_loop_lifecycle.py:2425, 2450, 2495` — `TestReconcileStaleRunning.*`: reconcile currently flips `running → interrupted`; verify whether it should also handle a `user_stopped` reconciliation case (e.g. process died before `_finish()` but sentinel was written).
- `scripts/tests/test_cli_loop_background.py:136, 158` — `TestLoopSignalHandler.test_second_signal_archives_before_exit` and `test_second_signal_swallows_archive_oserror` assert `archive_run_only.assert_called_once_with(terminated_by="interrupted_force")`. Unaffected if second-SIGINT force-exit path keeps `interrupted_force` distinct from the new values; verify the issue's proposal preserves this distinction.
- `scripts/tests/test_ll_loop_display.py:2815, 2829` — `test_zero_exit_code_for_graceful_termination` and `test_exit_codes_dict_matches_expected_mapping`: extend parametrize / dict to include `user_stopped` and `system_signal` (both should map to exit 1 per the `EXIT_CODES` extension in `_helpers.py`).
- `scripts/tests/test_cli_loop_lifecycle.py:1151` — `TestCmdResumeExitCodes.test_zero_exit_for_graceful_termination`: same parametrize extension.

**Schema regeneration test**:
- `scripts/tests/test_generate_schemas.py` — verify the regenerated `loop_complete.json` schema includes the two new values in the `terminated_by` description string.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md:606` — append `user_stopped`, `system_signal` to the inline enumeration of `loop_complete.terminated_by` values (also corrects a stale `"signal"` reference predating BUG-2474)
- `docs/reference/API.md:3479-3482` — extend the SIGINT/SIGTERM signal-handling table; the SIGTERM/graceful row should now also document the `cmd_stop` → `user_stopped` path
- `docs/reference/COMMANDS.md:766` — replace the legacy `loop_complete.terminated_by == "signal"` rule with one that recognizes both `system_signal` (genuine SIGKILL/OOM) and `user_stopped` (`ll-loop stop`) as distinct sub-classes
- `docs/reference/CLI.md:700-702` — reflect `user-stop.marker` sentinel-write semantics in the `ll-loop stop` description so users debugging "why does my state say user_stopped" can find the answer
- `docs/development/TROUBLESHOOTING.md` — add a "Loop exited with -9" debug-path section per the Related Key Documentation table; the file currently has no such entry
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:1144-1170` — sidebar distinguishing the `cmd_stop` sentinel-write path from raw SIGKILL
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — if the loop-specialist failure-mode taxonomy is cross-referenced, update the list to include `kernel-signal` and `user-stopped`
- `skills/audit-loop-run/SKILL.md:57` — extend the filterable-status list to include `user_stopped` and `system_signal` so `ll-audit-loop-run` filters match the new taxonomy
- `docs/reference/API.md` — extend `ExecutionResult.terminated_by` enum (already listed in primary-files)

### Configuration
- N/A — no config schema change; existing `fsm.*` keys are unaffected

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation, beyond the primary-file list in §1–§6 of Proposed Solution:_

6. **Display branches** — Update `scripts/little_loops/cli/loop/info.py`:
   - `_STATUS_COLORS` (line 88): add `user_stopped` (suggest `33` = yellow, matches `interrupted`) and `system_signal` (suggest `31` = red) entries.
   - `display_status` (line 107) and multi-instance branch (line 119): treat `user_stopped` as `"paused"` (still resumable) and `system_signal` as its own display label.
7. **Exit codes** — Update `scripts/little_loops/cli/loop/_helpers.py:29-37`: add `user_stopped: 1, system_signal: 1` to `EXIT_CODES` so the new failure bucket yields a non-zero shell exit; without this, the new status would silently exit 0.
8. **Resumability** — Update `scripts/little_loops/fsm/persistence.py:46`: add `user_stopped` to `RESUMABLE_STATUSES`. Do NOT add `system_signal` (runner died mid-state; resume is unsafe).
9. **Persistence mapping** — Extend the `terminated_by → state.status` mapping in BOTH `archive_run_only()` (lines 847–860) and the post-block of `run()` (lines 897–905) to keep them consistent: `user_stopped → "failed"`, `system_signal → "failed"`.
10. **Log-scan categorization** — Update `scripts/little_loops/cli/logs.py:1755-1761`: extend the `scan-failures` outcome buckets so `user_stopped` and `system_signal` classify correctly (recommend: `user_stopped → "interrupted"` category since it's a clean interrupt; `system_signal → "signal"` new category, or fall through to `fail/error/abort`).
11. **Log message** — Update `scripts/little_loops/cli/loop/lifecycle.py:386`: change `f"Marked {stem} as interrupted"` to `f"Marked {stem} as user_stopped"` to match the new status write.
12. **Schema generator** — Update `scripts/little_loops/generate_schemas.py:407-408`: extend the `loop_complete.terminated_by` description string to enumerate the new values, then re-run `ll-generate-schemas`.
13. **Reconcile path** — Update `scripts/little_loops/cli/loop/lifecycle.py` reconcile-stale-running path: confirm whether a `state.status == "running"` + sentinel-present reconciliation should flip to `user_stopped` (rather than `interrupted`).
14. **Documentation pass** — Update:
    - `docs/reference/EVENT-SCHEMA.md:606` (terminated_by enumeration)
    - `docs/reference/API.md:3479-3482` (signal-handling table)
    - `docs/reference/COMMANDS.md:766` (replace stale `"signal"` reference)
    - `docs/reference/CLI.md:700-702` (`ll-loop stop` description with sentinel semantics)
    - `docs/development/TROUBLESHOOTING.md` (new "Loop exited with -9" debug section)
    - `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:1144-1170` (sidebar distinguishing cmd_stop sentinel from raw SIGKILL)
    - `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` if loop-specialist failure-mode taxonomy is cross-referenced
    - `skills/audit-loop-run/SKILL.md:57` (filterable-status list)
15. **Test updates** — Apply the test fixes listed in `### Tests` above: flip `TestCmdStop.*` assertions to `user_stopped`, extend `archive_run_only` mapping table, extend `EXIT_CODES` parametrized tests, and split or rename `test_sigkill_on_next_state_triggers_shutdown` (its current assertion encodes the misclassification this issue fixes).

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

### Wiring-specific Acceptance Criteria (added by `/ll:wire-issue`)

- `cli/loop/info.py:_STATUS_COLORS` (line 88) and the `paused`-branch
  fallbacks at lines 107 and 119 render `user_stopped` as `"paused"` and
  `system_signal` with a distinct color, so `ll-loop list` and
  `ll-loop status` outputs distinguish the two new statuses visually.
- `cli/loop/_helpers.py:EXIT_CODES` (lines 29–37) maps
  `user_stopped: 1` and `system_signal: 1`; `python -c "import subprocess;
  subprocess.run(['ll-loop','run',...])` exits non-zero when the runner
  terminates with either new value.
- `fsm/persistence.py:RESUMABLE_STATUSES` (line 46) includes
  `user_stopped`; `cmd_resume` accepts a `user_stopped` instance and
  does NOT accept a `system_signal` instance (resumable filter
  unchanged for kernel-signal runs).
- The `terminated_by → state.status` mapping in BOTH `archive_run_only()`
  and `run()`'s post-block map `user_stopped → "failed"` and
  `system_signal → "failed"`; `test_archive_run_only_maps_terminated_by_to_status`
  parametrized table covers both new rows.
- `cli/logs.py` `ll-logs scan-failures` categorizes a
  `loop_complete` event with `terminated_by == "user_stopped"` as
  `"interrupted"` (or a new `"user-stopped"` bucket) and one with
  `terminated_by == "system_signal"` as a `signal` (or `fail/error/abort`
  fallback) bucket; the categorization is deterministic for repeated runs.
- `cmd_stop`'s `logger.success` line reflects the new status label
  (`"as user_stopped"`), so the CLI log matches the on-disk state.
- `generate_schemas.py:407-408` enumerates the new values in the
  `loop_complete.terminated_by` description string; re-running
  `ll-generate-schemas` produces a `loop_complete.json` whose description
  matches the runtime-emitted values.
- All wiring-touched tests pass under
  `python -m pytest scripts/tests/`; in particular the rewired
  `TestCmdStop.*`, `TestCmdResumeExitCodes.*`, and
  `test_exit_codes_dict_matches_expected_mapping` cases must not regress.

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
- `/ll:wire-issue` - 2026-07-07T17:12:17 - `ffe21b52-2e1e-4691-95aa-75f05b4442b5.jsonl`
- `/ll:capture-issue` - 2026-07-07T16:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:wire-issue` - 2026-07-07T17:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
