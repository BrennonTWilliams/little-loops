---
id: BUG-3375
type: BUG
title: autodev cascades Errno 2 into clean terminal exit and silently abandons queue
  when worktree vanishes
priority: P2
status: done
discovered_by: claude-code-review
discovered_date: '2026-09-01'
completed_at: '2026-09-01T23:48:53Z'
relates_to:
- BUG-3373
- ENH-3374
confidence_score: 90
outcome_confidence: 69
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# BUG-3375: autodev cascades Errno 2 into clean terminal exit and silently abandons queue when worktree vanishes

## Summary

When the shared worktree a sub-loop is running in disappears mid-run, the
FSM has no notion of "my working directory is gone": every subsequent shell
action fails with `[Errno 2] No such file or directory` at `Popen`
(`cwd=worktree`), each failure is routed through the loop's ordinary
`on_error` edges, and the loop walks — erroring state by erroring state —
to whatever terminal the error edges happen to land on. In the BUG-3373
incident, `refine-to-ready-issue` and then `autodev` cascaded ~12 such
errors in under a second, both landed on their generic `failed` terminal
(`failure_terminal: true`), the remaining queued issue (ENH-1722) was never
dequeued, and the run's only verdict was a generic `incomplete-abandoned`.
The defect is not that the exit was "clean" — it is that the exit is
*indistinguishable* from an ordinary autodev failure and the cause
("the worktree vanished") is lost before any consumer can see it.

## Current Behavior

From `.loops/.history/2026-09-01T031623-sprint-refine-and-implement/events.jsonl`
(`03:57:14.937`–`03:57:15.369`): `check_decision_mid_refine`,
`check_wire_done`, `normalize_structure`, `check_verify_verdict`, … then
autodev's `skip_inflight`, `dequeue_next`, `finalize_done` each raise
`action_error` `[Errno 2] No such file or directory: PosixPath('...')`,
each routes onward via `on_error`, and both loops reach `loop_complete` at
their `failed` terminal (`final_state: failed`, `terminated_by: terminal`,
`failure_terminal: true` — events.jsonl lines 571 and 585). In the parent
`auto-refine-and-implement`, that surfaces as `delegate` → `on_failure` →
`delegate_failed`'s `terminal)` arm → `finalize`, i.e. the exact same path
as a genuine autodev `failed` outcome. The operator-facing result is an
`incomplete-abandoned` verdict indistinguishable from an ordinary partial
drain; the abandoned issue is reported only as a count.

## Expected Behavior

A vanished working directory is an unrecoverable infrastructure failure,
not a per-state error to be routed around. When an action fails because the
executor's `working_dir` no longer exists, the executor should:

1. detect it (a `FileNotFoundError` from `Popen` whose `cwd` no longer
   exists, confirmed by an explicit `working_dir` existence check),
2. abort the loop immediately with a distinct infrastructure-failure
   terminal (analogous to the existing infra-retry classification), rather
   than dispatching further states that can only fail the same way, and
3. surface the cause explicitly in events and the finalize verdict (e.g.
   `verdict=infra-worktree-vanished`, naming the missing path), so the
   operator sees "worktree deleted mid-run", not a generic abandonment.

## Motivation

The silent-clean-exit behavior is what turned the BUG-3373 deletion into an
invisible batch truncation: one issue killed mid-refine, one abandoned
untouched, and a verdict that reads like a routine timeout. Whatever the
upstream deleter turns out to be (BUG-3373) and however cleanup is hardened
(ENH-3374), the executor should fail loudly and immediately when the ground
disappears from under it — both for operators and so future incidents are
diagnosable from the verdict instead of a full events.jsonl replay.

## Proposed Solution

In `scripts/little_loops/fsm/executor.py`:

1. **Primary detector — pre-dispatch existence check in `run()`'s main
   loop.** At the **top of each main-loop iteration, before the terminal-state
   check** (`executor.py:665`, `if state_config.terminal:`) — NOT next to
   `_check_host_guard` at `executor.py:743`, which runs *after* the terminal
   check returns `_finish("terminal")`. If the check sat at 743, a vanish
   during the last non-terminal action whose `on_error`/`on_failure` routes
   straight to an action-less `terminal: true` state would finish as
   `terminated_by="terminal"` and the abort would never fire. Resolve the
   directory to check as: `self.working_dir` when set, otherwise the
   process cwd via `os.getcwd()`. If `Path(self.working_dir).exists()` is
   `False`, or `os.getcwd()` raises `FileNotFoundError` (which it does on
   macOS and Linux once the cwd is unlinked), short-circuit to
   `self._finish("workdir_vanished",
   error=f"Working directory vanished mid-run: {path}")` —
   **always pass `error=`**; downstream outcome derivation keys on it (see
   step 2b). **The `os.getcwd()` fallback is required, not optional
   (added 2026-09-01):** top-level executors never set `working_dir` —
   `PersistentExecutor` (`fsm/persistence.py`) and `cli/loop/lifecycle.py`
   construct `FSMExecutor` without it, and the only `working_dir=` in
   `cli/loop/` is `testing.py:260` — so a `self.working_dir is not None`
   guard alone would skip every `ll-loop run` (including ll-parallel workers
   running inside a worktree — the `worker_pool.py` subprocess runs
   `ll-loop run` with `cwd=worktree_path`). `ll-loop resume` is NOT such a
   case: it runs from the project root with `working_dir=None`, and the
   worktree path is not persisted in `LoopState`, so nothing in a resume
   references the vanished dir (corrected 2026-09-01, round 4). Only
   `loop:` children with an attached `worktree:` carry a non-`None`
   `working_dir`. **The fallback only works if step 1c lands with it** —
   see below. Accepted edge cases: (a) a loop whose own final
   action legitimately removes its working dir will now abort as
   `workdir_vanished` instead of finishing `terminal`; (b) the check also
   fires on iteration one, so a `working_dir` that *never* existed reports
   as `workdir_vanished` too — acceptable (same operator action), name it in
   the test (`test_missing_working_dir_at_start_aborts_as_workdir_vanished`).
   This is one `stat` per state and covers **every** action type. It must be the primary detector
   because the Popen-site approach alone cannot work: `DefaultActionRunner`'s
   prompt-mode branch (`runners.py:232-272`) wraps `run_claude_command` in a
   bare `except Exception` and returns `ActionResult(exit_code=1,
   stderr="Action failed: ...")`, so a vanished cwd under a `/ll:*` prompt
   state never raises out to the executor — it silently routes via
   `on_failure`/`on_error`. Prompt states are the majority in the affected
   loops, so instrumenting only `_run_subprocess`/the shell branch would
   leave the cascade intact.
1b. **Dropped (decided 2026-09-01).** Popen-site `FileNotFoundError`
   catching (`executor.py:2559`, `runners.py:298`) is out of scope. The
   pre-dispatch check alone satisfies every test criterion in step 4, and
   1b would add two more code sites plus the `test_fsm_runners.py` Popen
   test — the fanout that dragged outcome confidence down. The
   `exc.filename == str(working_dir)` discriminator is kept in Decision
   Rules for a future follow-up only; do not add the runners test.
1c. **Make the abort path sink-tolerant (rewritten 2026-09-01, round 5) —
   required for the `working_dir=None` fallback to be deliverable.** The
   round-4 version of this step ("resolve `LoopPersistence.loops_dir` to
   absolute") rested on a false premise and is withdrawn: `cmd_run` already
   resolves `loops_dir` absolute before constructing `PersistentExecutor`
   (`cli/loop/run.py:103`, BUG-2386), so `LoopPersistence.__init__`'s
   relative default (`persistence.py:491`) is never hit on the `ll-loop run`
   path. Do **not** add `.resolve()` there. The real problem is that
   absolute paths do not help either: in the ll-parallel-worker case the
   worker runs `ll-loop run` with `cwd=worktree_path`, `BRConfig(Path.cwd())`
   yields the default `.loops`, so the sink resolves to `<worktree>/.loops`
   and the events file, state file, `run_dir` (`lifecycle.py:671`), and lock
   dir all vanish *with* the worktree. After the vanish,
   `_finish("workdir_vanished")` → `_emit("loop_complete")` →
   `_append_jsonl` (`persistence.py:208-224`, unguarded `open(path, "a")`)
   raises `FileNotFoundError`; that escapes `_finish`, hits `run()`'s outer
   `except Exception` (`executor.py:911`), which calls `_finish("error")`,
   which raises again and propagates out of `run()` as a traceback.
   `PersistentExecutor.run`'s `save_state`/`archive_run`
   (`persistence.py:1253-1255`) and `cmd_run`'s `lock_manager.release`
   (`run.py:664`) fail the same way. Fix — guard the abort path, not the
   paths: (i) in `run()`, wrap the `workdir_vanished` `_finish` call in
   `try/except OSError`; on failure write
   `workdir_vanished: <path>` to stderr and return an `ExecutionResult`
   constructed directly (`terminated_by="workdir_vanished"`, `error=<msg>`,
   `failure_terminal=False`) so the abort never degrades into an `"error"`
   traceback; (ii) in `PersistentExecutor.run`, when
   `result.terminated_by == "workdir_vanished"`, wrap `save_state`/
   `archive_run` in `try/except OSError` (log, do not raise); (iii) in
   `cmd_run`, wrap `lock_manager.release` the same way. **Deliverable for
   the top-level-in-worktree case is therefore: exit code 1, stderr names
   the missing path, no traceback.** `events.jsonl`/`state.json` cannot be
   written because they lived in the deleted tree — that is accepted, not a
   gap. The incident topology (in-process `loop:` child with `working_dir`
   set, parent's sink in the project root) is unaffected: the child's
   `loop_complete` reaches the parent's persistence normally, and the child
   `run_dir` is already anchored absolute at `executor.py:1055-1063`.
2. On that classification, stop routing via the state's `on_error` edge:
   terminate the loop with a distinct failure terminal, emitting a new
   event (e.g. `workdir_vanished`) carrying the missing path and current
   state. Follow the established event-registration procedure
   (CONTRIBUTING.md § "Event Schema Maintenance": EVENT-SCHEMA.md →
   `SCHEMA_DEFINITIONS` in `generate_schemas.py` → regenerate → commit
   `.json` → `DESVariant` in `observability/schema.py`; update the
   `test_generate_schemas.py` count literals and
   `test_des_schema.py`/`test_des_audit.py` expectations).
2b. **`failure_terminal` is `False` for this abort — plan accordingly.**
   `_finish()` (`executor.py:3838-3841`) computes `failure_terminal =
   terminated_by == "terminal" and <state in failure states>`, so
   `workdir_vanished` behaves like `host_pressure_abort`/`stall_detected`:
   `failure_terminal=False`. Consequences (each verified 2026-09-01):
   - `cli/loop/_helpers.py` exit code is **not** `FAILURE_TERMINAL_EXIT_CODE`
     (2); it falls to `EXIT_CODES.get(terminated_by, 1)` → 1. Add an explicit
     `"workdir_vanished": 1` entry to `EXIT_CODES` (lines 69-82) so the
     mapping is deliberate, not a default. (`host_pressure_abort`,
     `host_budget_exceeded`, `cost_ceiling_exceeded` are also absent and
     reach 1 via the default; adding them in the same edit is optional and
     behavior-neutral.)
   - `cli/logs.py::_derive_loop_outcome()` already returns `"error"` because
     its first line is `if "error" in event: return "error"` and `_finish`
     writes `error` into the `loop_complete` payload whenever `error=` is
     passed. The explicit `workdir_vanished → "error"` branch is
     belt-and-suspenders; keep it, and add a test asserting the
     `loop_complete` event carries `error`.
   - `fsm/persistence.py::map_final_status()` default fallback → `"failed"`
     — correct, no change.
3. **Parent routing: treat it like `error`, not the `on_no` catch-all.** In
   `_execute_sub_loop` (`executor.py:1176-1181`) extend the
   `terminated_by == "error"` branch to
   `terminated_by in ("error", "workdir_vanished")`. That branch captures
   `child_result.error` (which names the missing path) into
   `${captured.<state>.error}`, sets the capture verdict to `"error"`, and
   routes `on_error` when declared (falling back to `on_no`). The else-branch
   (`1191-1196`) would instead route `on_no` with verdict `"no"` and drop the
   error string — but the child never *concluded* "no"; it died. Every
   consumer YAML already wires `on_error` as "child died" (e.g. autodev's
   `on_error: check_decide_rate_limited`), so this lands in the right place.
   Update the verdict-derivation block at `1163-1169` to match. In the
   incident the loop with the intact cwd was the *immediate* parent,
   `auto-refine-and-implement` — its `delegate` state attaches the worktree
   for the `autodev` child (`sub_loop_worktree_attached`, events.jsonl line
   20, `run_id …-auto-refine-and-implement`) while itself running from the
   project root. `sprint-refine-and-implement` sits one level further up and
   never touched the worktree. When a parent *shares* the vanished dir
   (e.g. `refine-to-ready-issue`'s `loop:` children), its own pre-dispatch
   check (step 1) aborts it at the next dispatch regardless of routing.
3b. **Name the cause in the sprint verdict** (this is Expected Behavior #3;
   without it the run still finalizes as `incomplete-abandoned`). Because
   step 3 routes `workdir_vanished` via `on_error`, and
   `auto-refine-and-implement.yaml`'s `delegate` declares
   `on_error: record_error` (NOT `delegate_failed` — pinned by
   `test_builtin_loops.py::test_delegate_crash_routes_to_record_error`),
   the marker must be written in **`record_error`** (lines ~600-608), not
   in `delegate_failed`'s `case` — a `workdir_vanished)` arm there would be
   unreachable. In `record_error`, branch on
   `${captured.delegate.terminated_by?}`: when it is `workdir_vanished`,
   write `${context.run_dir}/infra-workdir-vanished` containing
   `${captured.delegate.error?}` (the missing path) in addition to the
   existing `auto-refine-and-implement-errored.txt` append; then `next:
   finalize` as today. **Three guards on those references (updated
   2026-09-01, round 5):** use the optional `?` form on both —
   `record_error` is also reached for plain `error` aborts, where
   `_execute_sub_loop` only sets `captured.<state>.error` when
   `child_result.error` is truthy, and an unresolved `${...}` raises inside a
   state that has no `on_error` edge; and add **two** MR-11 markers, one per
   variable, each on its own comment line preceding the action body:
   `# ll-lint: mr11-ok(captured.delegate.terminated_by) BUG-3375 -
   executor-controlled enum, not user input` and
   `# ll-lint: mr11-ok(captured.delegate.error) BUG-3375 - executor-written
   path string, not user input`. `fsm/validation/shell_safety.py` (MR-11)
   is not a key allowlist — it flags **every** `${captured.*}` in a shell
   action, and a marker exempts only the single variable it names.
   `delegate_failed` (YAML lines ~366-368) is the precedent: its
   `captured.delegate.terminated_by` marker sits on its own comment line
   above the `case`. Run `ll-loop validate auto-refine-and-implement` after
   editing. Have the finalize
   state (lines ~1102-1125) emit `verdict=infra-worktree-vanished` when that
   marker is present, taking precedence over `incomplete-abandoned`. Keep
   the abandoned count in the JSON so the truncation is still quantified.
   **Also add the new verdict to finalize's routing arm (added
   2026-09-01):** the bottom of `finalize` routes the FSM terminal via
   `case "$VERDICT" in phantom|incomplete-abandoned) exit 1 ;; *) exit 0`
   (lines ~1145-1148). Without `infra-worktree-vanished` in the exit-1 arm
   the run exits 0 → `on_yes: done` → renders green, which is the exact
   mis-signal this issue exists to remove. Extend the arm, and add the
   verdict to `finalize_incomplete`'s explanatory message (line ~1160) and
   the `incomplete` terminal's comment.
3c. **Scope boundary — fail fast, no re-dispatch (decided 2026-09-01).**
   `record_error` → `finalize` skips `recheck_set`, so the run does not
   attempt to re-drain the abandoned queue. A re-dispatch *could* recover it
   (each `delegate` dispatch creates a fresh timestamped worktree,
   `executor.py:1035`), but while BUG-3373's deleter is unidentified a retry
   risks re-triggering the deletion in a loop. Recovery-by-redispatch is a
   deliberate non-goal of this issue; revisit once BUG-3373 is closed.
4. Tests in `scripts/tests/test_fsm_executor.py`: delete the executor's
   working dir mid-run (after the first state) and assert the loop
   terminates with `terminated_by="workdir_vanished"`,
   `failure_terminal=False`, `error` naming the path, the new event emitted,
   and **zero `action_error` events after the first post-vanish route** —
   pin the cascade shape, not just "at most one further dispatch". Add a
   second test where the state after the vanish is an action-less
   `terminal: true` state, proving the check fires before the terminal
   check (step 1 placement). Add a sub-loop test asserting the parent
   routes `on_error` and captures `error`/`verdict="error"` (step 3). Add
   the iteration-one missing-dir test from step 1 edge case (b). Add a
   `working_dir=None` variant that deletes the process cwd (chdir into a
   temp dir, `rmtree` it mid-run) to pin the `os.getcwd()` fallback. **That
   variant must run through `PersistentExecutor` with `loops_dir` *inside*
   the deleted cwd (e.g. `tmp_path / ".loops"`, mirroring the worker case),
   not a bare `FSMExecutor` with an in-memory callback (rewritten
   2026-09-01, round 5)** — assert `run()` returns (no exception) with
   `terminated_by == "workdir_vanished"`, `error` naming the path, and that
   stderr (capsys) contains the path. Do **not** assert `loop_complete`
   landed in `events.jsonl` — the sink is gone with the tree (step 1c). A
   `loops_dir` placed *outside* the deleted cwd would pass without step 1c's
   guards and proves nothing; this in-tree variant is the only test that
   proves step 1c.
   **Nesting note (added 2026-09-01):** in the incident topology the abort
   fires in the grandchild (`refine-to-ready-issue`); `autodev` then routes
   its `refine` state's `on_error` once, and its own pre-dispatch check
   aborts it on the *next* iteration. The "zero `action_error`" assertion
   holds per executor, but one `route` event per nesting level is expected
   — do not assert that the parent emits no `route` after the child abort.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- **Correction**: `_run_subprocess_direct` (named in step 1 above) does not exist anywhere in the repository — confirmed by a repo-wide, unfiltered grep with zero hits outside this issue file. The two actual subprocess-launch sites needing the fix are `FSMExecutor._run_subprocess` (`executor.py:2543`, Popen at `2559-2566`) for `mcp_tool` actions, and `DefaultActionRunner.run()`'s shell branch (`runners.py:117`, Popen at `298-306`) for ordinary shell actions — both need equivalent FileNotFoundError/vanished-cwd handling. See Integration Map and Program Design below for the full call path and the existing abort-pattern this should follow.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/logs.py::_derive_loop_outcome()` (lines 1968-1987) — add an explicit branch mapping `workdir_vanished` to `"error"` (decided: an infrastructure loss is not a loop-logic failure and must not inflate the `"failed"` bucket in fleet rollups). **Correction 2026-09-01**: this is belt-and-suspenders, not load-bearing — the function's first line `if "error" in event: return "error"` already classifies the run as `"error"` because `_finish(..., error=...)` writes `error` into `loop_complete`. The "misclassified as converged" risk only materializes if the abort omits `error=`, which Proposed Solution step 1 forbids.
- Add `"workdir_vanished": 1` to `EXIT_CODES` in `scripts/little_loops/cli/loop/_helpers.py` (lines 69-82). `failure_terminal` is `False` for this abort (see Proposed Solution 2b), so `FAILURE_TERMINAL_EXIT_CODE` does not apply; today the value would only reach 1 via the `.get(..., 1)` default.
- Extend the `terminated_by == "error"` branch of `_execute_sub_loop` (`executor.py:1176-1181`) and the verdict-derivation block (`1163-1169`) to include `workdir_vanished` (Proposed Solution step 3).
- Add the `workdir_vanished` marker branch to `auto-refine-and-implement.yaml`'s **`record_error`** state (not `delegate_failed` — unreachable via `on_error`, see Proposed Solution 3b) and a matching `infra-worktree-vanished` verdict in its finalize state — **including the `exit 1` routing arm** (`phantom|incomplete-abandoned) exit 1`), the `finalize_incomplete` message, `${captured.delegate.error?}` (optional form), and **two** MR-11 `# ll-lint: mr11-ok(...)` annotations, one for `captured.delegate.terminated_by` and one for `captured.delegate.error` (updated round 5).
- ~~Add a Popen-raises-`FileNotFoundError` test to `scripts/tests/test_fsm_runners.py`~~ — dropped with step 1b (2026-09-01); no runners.py change, no runners test.
- Bump the four `== 58` count literals in `scripts/tests/test_generate_schemas.py` (lines 21, 114, 121, 250) to `59`
- Add a `workdir_vanished` row to `docs/guides/LOOPS_GUIDE.md`'s `terminated_by` exit-reasons table (lines 907-921)
- Regenerate `docs/reference/schemas/workdir_vanished.json` via `ll-generate-schemas`. `docs/observability/des-audit.md` is **hand-maintained** despite its "DO NOT EDIT - generated" header (verified 2026-09-01: `ll-verify-des-audit` / `cli/verify_des_audit.py` is audit-only with no write flag, and no other writer exists in the repo) — add the `workdir_vanished` row by hand and bump "Total variants: 83" to 84

## Integration Map

### Codebase Research Findings

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — the **only** executor change is the pre-dispatch existence check at the top of `run()`'s main loop, before the terminal check at `665` (Proposed Solution step 1), plus the `_execute_sub_loop` branch extensions (step 3). `_run_subprocess` (Popen at `2559-2566`) and `_run_action_or_route` (`3344-3372`) are **not** modified — step 1b was dropped 2026-09-01
  > ⚠ Superseded — this bullet originally named `_run_subprocess_direct` (which does not exist) and then the Popen-site changes of step 1b; both corrected, the second in round 4
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor.run` (`1253-1255`): wrap `save_state`/`archive_run` in `try/except OSError` when `result.terminated_by == "workdir_vanished"` (Proposed Solution step 1c, rewritten round 5). **No change to `LoopPersistence.__init__`** — the round-4 `.resolve()` plan is withdrawn; `cmd_run` already resolves `loops_dir` (`run.py:103`)
- `scripts/little_loops/cli/loop/run.py` — `lock_manager.release` (`664`): same `OSError` guard for the `workdir_vanished` result (step 1c)
- `scripts/little_loops/fsm/runners.py` — **no change** (step 1b dropped 2026-09-01); listed for context only. Its shell branch (Popen at `298-306`) is one raising site; its prompt-mode branch (`232-272`) converts **any** launch failure into `ActionResult(exit_code=1)` and never raises, which is why the pre-dispatch check in `run()` is the required primary detector rather than Popen-site catching
- `scripts/little_loops/fsm/types.py` — `ExecutionResult.terminated_by` docstring (lines 35-41) enumerates existing abort kinds; add the new value there
- `scripts/little_loops/generate_schemas.py` — `SCHEMA_DEFINITIONS`; register the new event following the `"stall_detected"` entry (lines 383-395) as the pattern
- `scripts/little_loops/observability/schema.py` — new `DESVariant` subclass following `StallDetectedVariant`/`HostPressureAbortVariant` (lines 207-211, 406-410), registered in the `DES_VARIANTS` tuple

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/logs.py` — `_derive_loop_outcome()` (lines 1968-1987) is a closed if/elif chain (`max_steps`/`max_iterations_reached` → `"max-steps"`, `cycle_detected` → `"stalled"`, `interrupted`/`handoff`/`timeout`/`user_stopped` → `"interrupted"`, `system_signal` → `"signal"`) with no branch for the new value [Agent 2 finding]. **Corrected 2026-09-01**: the chain is preceded by `if "error" in event: return "error"`, so a `workdir_vanished` abort that passes `error=` is already bucketed `"error"`; the explicit branch is defensive only.
- `scripts/little_loops/cli/loop/_helpers.py` — `EXIT_CODES` (lines 69-82) needs an explicit `"workdir_vanished": 1` entry; see Proposed Solution 2b.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `record_error` (lines ~600-608), the finalize verdict block (~1102-1125), **and finalize's `case "$VERDICT"` exit-routing arm (~1145-1148)** need the `workdir_vanished` marker branch / `infra-worktree-vanished` verdict; see Proposed Solution 3b. `delegate_failed` (342-379) is untouched — it is only reached via `on_failure`, which `workdir_vanished` never takes.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `delegate_failed` state (lines 342-379) already reads `${captured.delegate.terminated_by}` in a `case` statement; its `*` branch currently folds all non-`terminal` `terminated_by` values into `recheck_set`. **Revised 2026-09-01**: `delegate` declares `on_error: record_error`, so with step 3's error-branch routing this state is never reached for `workdir_vanished`; the marker goes in `record_error` instead (Proposed Solution 3b). Without that, the run still finalizes `incomplete-abandoned` and Expected Behavior #3 is unmet
- `scripts/little_loops/fsm/executor.py::_execute_sub_loop` (lines 914-1196) — captures `child_result.terminated_by`/`failure_terminal` for any parent loop observing a sub-loop's outcome (lines 1147-1196). **Decided 2026-09-01**: `workdir_vanished` joins the `error` branch (1176-1181), not the else-branch — see Proposed Solution step 3

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (lines 1036-1041) — `case "${captured.confidence_check.failure_terminal?}:${captured.confidence_check.terminated_by?}" in True:*|*:error|*:timeout|*:max_steps)`. **Corrected 2026-09-01**: the `True:*` arm does NOT catch this — `failure_terminal` is `False` for a non-`terminal` abort (Proposed Solution 2b), so the value is `False:workdir_vanished` and matches no arm. Moot in practice: `confidence_check` is a `loop:` child sharing the parent's `working_dir`, so the parent's own pre-dispatch check aborts it before this state can run. No change needed, but not for the reason originally stated. This is one of the loops the BUG-3373/BUG-3375 incident itself ran (`sprint-refine-and-implement` → `refine-to-ready-issue`) [Agent 1/2 finding]
- `scripts/little_loops/fsm/persistence.py::map_final_status()` (lines 132-168) — canonical `(terminated_by, failure_terminal)` → persisted `LoopState.status` mapper; its default fallback already returns `"failed"` for any unrecognized `terminated_by`, so `workdir_vanished` is auto-covered with no code change [Agent 1/2 finding; re-verified 2026-09-01]
- `scripts/little_loops/cli/loop/_helpers.py` — `EXIT_CODES` dict (lines 69-82) and `_is_success()` (1917-1920). **Corrected 2026-09-01**: `failure_terminal` is `False` here, so `FAILURE_TERMINAL_EXIT_CODE` does NOT apply; the exit code reaches 1 only via `EXIT_CODES.get(..., 1)`. Add an explicit `"workdir_vanished": 1` entry [Agent 2 finding, corrected]
- `scripts/little_loops/cli/loop/info.py`, `scripts/little_loops/cli/loop/audit.py`, `scripts/little_loops/cli/loop/testing.py` — all pass `terminated_by` through verbatim (f-string/dict field); display correctly for any new string value with no change needed [Agent 1/2 finding]
- `scripts/little_loops/testing.py` — imports `ExecutionResult, FSMExecutor`; wraps `FSMExecutor` in a `PersistentExecutor`-style class whose `.run()`/`.resume()` return `ExecutionResult` [Agent 1 finding]
- `scripts/little_loops/extension.py` — imports `FSMExecutor, RouteContext, RouteDecision`; type-annotates executor fields [Agent 1 finding]
- `scripts/little_loops/cli/loop/lifecycle.py` — indirect consumer via `persistence.py`'s `map_final_status` (instantiates `PersistentExecutor`, line 728) [Agent 1 finding]
- `scripts/little_loops/history_reader.py::_WASTED_RUN_PREDICATE` (lines 1011-1017) — SQL `IN (...)` list with an `OR lr.failure_terminal = 1` arm auto-covers the new terminal for `waste_attribution()` token-waste rollups, no change needed [Agent 2 finding]
- `scripts/little_loops/parallel/worker_pool.py`, `scripts/little_loops/learning_tests/gate.py`, `scripts/little_loops/cli/queue.py` — branch on the exit code of a `ll-loop run <subloop>` subprocess, not on the `terminated_by` string. **Corrected 2026-09-01**: a workdir-vanished sub-loop exits 1 (not `FAILURE_TERMINAL_EXIT_CODE`=2, since `failure_terminal` is `False`), so it lands in the generic non-zero bucket alongside `max_steps`/`timeout`/`stall_detected`, NOT the `"blocked"`/`"terminal failure"` bucket. No change needed but these are affected consumers [Agent 2 finding, corrected]

### Conventions in Force
- Every distinct infra-abort kind in this codebase follows a `_pending_*` flag set deep in the call stack, checked in `run()`'s main loop, short-circuiting to `self._finish(<new terminated_by>, error=...)` — evidence: `_check_host_guard`/`HOST_PRESSURE_ABORT_EVENT` (`executor.py:3527-3601`, `744-748`), `_check_cost_ceiling`/cost-ceiling event (`3603-3683`, `825-834`), the stall detector/`STALL_DETECTED_EVENT` (`774-784`)
- Every new FSM-emitted event needs a module-level `*_EVENT` constant (`executor.py:90-130`), a `DESVariant` subclass in `observability/schema.py` registered in `DES_VARIANTS`, and a `SCHEMA_DEFINITIONS` entry in `generate_schemas.py` — evidence: `StallDetectedVariant` (`schema.py:207-211`) + `"stall_detected"` (`generate_schemas.py:383-395`)
- The retryable-infra-blip convention (`FailureType.INFRA_RETRY`/`classify_failure`, `issue_lifecycle.py:141-156`) is a separate, incompatible pattern — it operates on a completed `ActionResult`'s text/exit-code and retries in place; it does not apply to a Popen launch failure, which never produces an `ActionResult`

### Tests
- `scripts/tests/test_fsm_executor.py` — existing `_run_subprocess` patch-target tests (lines 717-839, 5349-5396) are the location for the new "delete working dir mid-run" test this issue's own Proposed Solution names
- `scripts/tests/test_generate_schemas.py`, `scripts/tests/test_des_schema.py`, `scripts/tests/test_des_audit.py` — count-literal/expectation updates required by the event-registration procedure (CONTRIBUTING.md § Event Schema Maintenance)
- `scripts/tests/test_builtin_loops.py` — structural/lint coverage over the built-in loop YAMLs (autodev, auto-refine-and-implement) that would exercise the new terminal wiring

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_runners.py` — **no test added** (step 1b dropped 2026-09-01). Kept for reference: `TestDefaultActionRunnerShellPath` (lines 226-460) never makes `Popen` raise, so if 1b is ever revived, a `side_effect=FileNotFoundError(...)` test belongs there [Agent 3 finding, descoped]
- `scripts/tests/test_generate_schemas.py` — the hardcoded `assert len(SCHEMA_DEFINITIONS) == 58` / `len(files) == 58` / `len(list(output_dir.glob("*.json"))) == 58` (×2) at lines 21, 114, 121, 250 all need bumping to `59`; `scripts/tests/test_des_schema.py` is set-relational (`>=`/set-difference) and self-adjusts with no literal to bump; `scripts/tests/test_des_audit.py` exercises `main_verify_des_audit()` generically and requires no manual update, only that the new `_emit("workdir_vanished", ...)` call site gets a matching registered `DESVariant` [Agent 2/3 finding]
- ~~`scripts/tests/test_fsm_persistence.py` — `LoopPersistence` relative-`loops_dir` `.resolve()` test~~ — dropped with the round-4 step 1c (round 5). Replaced by the in-tree `PersistentExecutor` cwd-deletion variant in Proposed Solution step 4, which asserts a clean `workdir_vanished` return with `loops_dir` inside the deleted cwd
- `scripts/tests/test_cli_loop_lifecycle.py` — mocks `PersistentExecutor`/`map_final_status` routing via `mock_result.terminated_by = "..."`/`failure_terminal = ...` (e.g. lines 669-870); add a `workdir_vanished` case (with `failure_terminal=False`) asserting status `"failed"` AND exit code 1 — this pins both the `map_final_status` fallback and the `EXIT_CODES` entry [Agent 1 finding, strengthened 2026-09-01]
- `scripts/tests/test_ll_logs.py` (exercises `_derive_loop_outcome`) — add a case with `terminated_by="workdir_vanished"` and an `error` key asserting `"error"`, plus one *without* `error` proving the explicit branch still yields `"error"`
- `scripts/tests/test_builtin_loops.py` — add a structural assertion that `auto-refine-and-implement.yaml`'s `record_error` action references `workdir_vanished` and `infra-workdir-vanished`, and that its finalize emits `infra-worktree-vanished`, so the YAML wiring in Proposed Solution 3b cannot silently regress. Sit it next to `test_delegate_crash_routes_to_record_error` (line ~4333), which already pins `delegate.on_error == record_error` — the routing assumption 3b depends on
- `scripts/tests/test_builtin_loops.py` finalize harness (~lines 4780-4840; the helper that seeds `autodev-*.txt` ledgers under a temp `run_dir`, runs the interpolated `finalize` action under `bash -c`, and asserts `expected_rc = 1 if summary["verdict"] in ("phantom", "incomplete-abandoned") else 0` at line ~4835) — **must change (added 2026-09-01)**: add `infra-worktree-vanished` to that `expected_rc` tuple (or the harness will fail the moment the exit-1 arm is extended), add a `marker`/`workdir_vanished` kwarg that seeds `run_dir/infra-workdir-vanished`, and add a case with both the marker and a non-empty `queue` asserting `verdict == "infra-worktree-vanished"`, `abandoned` still counted, and `returncode == 1`. This is the real-bash execution test of the precedence rule; the structural assertion above only proves the strings exist
- `scripts/tests/test_host_guard.py::TestExecutorPressureGate.test_abort_on_pressure` (lines 360-374) and `scripts/tests/test_cost_ceiling_enforcement.py::TestCostCeilingBreachAborts.test_breach_aborts_with_terminated_by` — closest existing `_pending_*`-abort-convention test shapes (assert `result.terminated_by == "<value>"` plus an event name present in captured events); useful as the E2E-level pattern to follow, though neither mocks `Popen` directly since neither originates from a Popen call [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` § "`terminated_by` exit reasons" (lines 907-921) — add a `workdir_vanished` row to the existing Markdown table alongside `host_pressure_abort`/`host_budget_exceeded` [Agent 2 finding]
- `docs/reference/API.md` § `ExecutionResult` (lines 6162, 6172) — closed pipe-union type comment for `terminated_by`; add `workdir_vanished` there (note: this union is already stale relative to `LOOPS_GUIDE.md`, missing `host_pressure_abort`/`host_budget_exceeded`/`cost_ceiling_exceeded`/`user_stopped`/`system_signal` — pre-existing drift, not introduced by this fix) [Agent 2 finding]
- `docs/observability/des-audit.md` — header claims it is generated (`<!-- DO NOT EDIT - generated by ll-verify-des-audit -->`, currently "Total variants: 83") but it is hand-maintained: `ll-verify-des-audit` / `scripts/little_loops/cli/verify_des_audit.py` is audit-only with no write flag and no other writer exists (verified 2026-09-01). Add the `workdir_vanished` row and bump the count to 84 by hand [Agent 2 finding, resolved]
- `docs/reference/schemas/workdir_vanished.json` — new generated JSON-Schema artifact via `ll-generate-schemas`, joining the existing 58-file set referenced by `test_generate_schemas.py` [Agent 2 finding]

## Program Design

### Codebase Research Findings

### Types
- No new data type/shape is introduced. `ExecutionResult.terminated_by: str` (`scripts/little_loops/fsm/types.py`, docstring lines 35-41) already enumerates the extension point for distinct abort kinds (`"cycle_detected"`, `"stall_detected"`, `"host_pressure_abort"`, `"host_budget_exceeded"`); the fix adds one more literal to that same string space (e.g. `"workdir_vanished"`).

### Signatures
- `FSMExecutor._run_subprocess(cmd: list[str], timeout: int) -> ActionResult` (`executor.py:2543`) — Popen call at `2559-2566`, `cwd=self.working_dir`, currently unguarded (full signature also takes `on_output_line`, `idle_timeout`, omitted here for brevity)
- `DefaultActionRunner.run(action: str, timeout: int, is_slash_command: bool, working_dir: Path | None = None) -> ActionResult` (`runners.py:117`) — shell-branch Popen call at `298-306`, `cwd=working_dir`, currently unguarded (full signature has additional kwargs, omitted here for brevity)
- `FSMExecutor._run_action_or_route(state: StateConfig, ctx: InterpolationContext) -> tuple[ActionResult | None, str | None]` (`executor.py:3344`) — the generic `except Exception as exc:` handler (line 3361) that currently intercepts both failure sites identically

### Call Path
`_execute_state` → `_run_action_or_route` → `_run_action` (`executor.py:2180`) → { `_run_subprocess` (mcp_tool actions) | `self.action_runner.run()` → `DefaultActionRunner.run()` shell branch (ordinary shell actions) } → `subprocess.Popen(cwd=...)` raises `FileNotFoundError` → caught generically by `_run_action_or_route` → routes via `state.on_error` → cascades until a `terminal: true` state → `run()` calls `_finish("terminal", ...)`. Established distinct-abort precedent to follow: `_check_host_guard`/`_check_cost_ceiling`/the stall detector each set a `_pending_*` flag checked in `run()`'s main loop (lines 744-834), short-circuiting straight to `self._finish(<new_terminated_by>, error=...)` before further states dispatch. **This fix deliberately does NOT add a `_pending_*` flag (clarified 2026-09-01, round 4):** nothing deeper in the stack detects the condition, so the pre-dispatch check in step 1 calls `_finish("workdir_vanished", error=...)` directly from the main loop. It shares the precedents' *placement* (main-loop short-circuit before dispatch), not their flag mechanism.

### Decision Rules
- **Primary trigger (pre-dispatch)**: at the top of each `run()` main-loop iteration, **before the `if state_config.terminal:` check at `executor.py:665`**, `(self.working_dir is not None and not Path(self.working_dir).exists()) or (self.working_dir is None and os.getcwd() raises FileNotFoundError)` → `_finish("workdir_vanished", error=<path>)`. The `None` arm is load-bearing: top-level `ll-loop run`/`resume` executors have `working_dir=None` (only `loop:` children with `worktree:` set it). Action-type-agnostic; this is what catches prompt-mode states, whose launch failures are swallowed into `ActionResult(exit_code=1)` by `runners.py:232-272` and never raise. Placement before the terminal check matters: action-less terminal states return `_finish("terminal")` at 665 and never reach the `_check_host_guard` block at 743.
- **`failure_terminal` stays `False`**: `_finish` only sets it for `terminated_by == "terminal"`. Consumers keyed on `failure_terminal` (`FAILURE_TERMINAL_EXIT_CODE`, the `True:*` case arm in `refine-to-ready-issue.yaml`) do not fire; consumers keyed on `terminated_by` or `error` do. Add `"workdir_vanished": 1` to `EXIT_CODES` explicitly.
- **Parent routing**: `_execute_sub_loop` treats `workdir_vanished` like `error` — `on_error` when declared (else `on_no`), `${captured.<state>.error}` set to the child's message, capture verdict `"error"`. Rationale: the child did not conclude "no"; it died, and only the `error` branch preserves the missing path for the parent.
- **Recovery**: none. `record_error` → `finalize` bypasses `recheck_set`; re-dispatching `delegate` into a fresh worktree is a non-goal until BUG-3373 identifies the deleter (Proposed Solution 3c).
- **Secondary trigger (DROPPED — reference only, see step 1b)**: a `FileNotFoundError` at `executor.py:2559` or `runners.py:298` is a vanished-cwd failure iff `exc.filename == str(working_dir)`. Verified 2026-09-01: CPython sets `.filename` to the cwd when the child's `chdir` fails (both `shell=True` and `shell=False`) and to the executable name when the command is missing — so `filename` discriminates precisely, whereas a post-hoc `exists()` check is racy and errno alone is ambiguous. Escape hatch: if `working_dir` is `None` or `exc.filename` names something other than the cwd, the failure is NOT reclassified — it falls through to the existing generic `action_error`/`on_error` path unchanged.
- **Outcome bucket**: `_derive_loop_outcome()` maps `workdir_vanished` → `"error"`, not `"failed"` (see Wiring Phase). `FailureType.INFRA_RETRY`/`classify_failure` (`issue_lifecycle.py:141-159`) is a different, incompatible convention — it operates on a completed `ActionResult`'s stderr/exit-code text and retries in place, and cannot apply here since a Popen launch failure never produces an `ActionResult`.

## Impact

Without this, any mid-run loss of a worktree (BUG-3373's actor, manual
deletion, disk issues) converts into a plausible-looking partial-drain
verdict; queued issues are abandoned with no signal. Affects all sub-loop
based automation (`autodev`, `auto-refine-and-implement`,
`sprint-refine-and-implement`, `refine-to-ready-issue`).

## Related Key Documentation

- `docs/reference/EVENT-SCHEMA.md`
- `CONTRIBUTING.md` § Event Schema Maintenance
- `docs/reference/DEFERRAL_CODES.md`

## Resolution

- **Action**: fix
- **Completed**: 2026-09-01
- **Status**: Completed

### Changes Made

- `scripts/little_loops/fsm/executor.py`: pre-dispatch working-directory
  existence check at the top of `run()`'s main loop (before the terminal
  check), with an `os.getcwd()` fallback for `working_dir=None` executors;
  aborts via `_finish("workdir_vanished", error=...)`, guarded by
  `try/except OSError` so a vanished persistence sink degrades to a clean
  `ExecutionResult` instead of an unhandled traceback. `_execute_sub_loop`'s
  verdict-derivation and routing now join `workdir_vanished` to the `error`
  branch.
- `scripts/little_loops/fsm/persistence.py`: `PersistentExecutor.run()` wraps
  `save_state`/`archive_run` in `try/except OSError` when
  `terminated_by == "workdir_vanished"`.
- `scripts/little_loops/cli/loop/run.py`: `lock_manager.release` wrapped the
  same way in `cmd_run`'s `finally` block.
- `scripts/little_loops/cli/loop/_helpers.py`: added an explicit
  `"workdir_vanished": 1` entry to `EXIT_CODES`.
- `scripts/little_loops/cli/logs.py`: `_derive_loop_outcome()` gained a
  defensive `workdir_vanished → "error"` branch (belt-and-suspenders; the
  `"error" in event` branch already covers it).
- `scripts/little_loops/fsm/types.py`, `generate_schemas.py`,
  `observability/schema.py`: registered the new `workdir_vanished` event
  (`WorkdirVanishedVariant`, `SCHEMA_DEFINITIONS` entry) per the Event Schema
  Maintenance procedure; regenerated
  `docs/reference/schemas/workdir_vanished.json`.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml`: `record_error`
  drops an `infra-workdir-vanished` marker when
  `${captured.delegate.terminated_by?}` is `workdir_vanished`; `finalize`
  derives `verdict=infra-worktree-vanished` from that marker (taking
  precedence over `incomplete-abandoned`) and added it to the exit-1 routing
  arm and the `finalize_incomplete` message.
- Docs: `docs/guides/LOOPS_GUIDE.md`, `docs/reference/API.md`,
  `docs/observability/des-audit.md` updated for the new `terminated_by`
  value / event.
- Tests: `test_fsm_executor.py` (6 new tests — mid-run vanish, action-less
  terminal state, iteration-one missing dir, `os.getcwd()` fallback, sub-loop
  routing, `PersistentExecutor` clean-abort), `test_cli_loop_lifecycle.py`,
  `test_ll_logs.py`, `test_builtin_loops.py` (structural + finalize-harness
  precedence test), `test_generate_schemas.py` (count bump + enumerated set).

### Verification Results

- Tests: PASS (`python -m pytest scripts/tests/` — 22340 passed, 42 skipped,
  2 pre-existing unrelated failures on `main` before this change: an
  evidence-verification gate and a decision-rules corpus differential test,
  both triggered by an unrelated FEAT-3372 issue file, confirmed via
  `git stash`)
- Lint: PASS (`ruff check`, `ruff format --diff` clean on all touched files)
- Types: PASS (`mypy` clean on all touched modules)
- `ll-loop validate auto-refine-and-implement`: valid, no new MR-11 warnings

## Status

**Open** | Created: 2026-09-01 | Priority: P2

## Steps to Reproduce

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

Observed as part of the same incident BUG-3373 documents (`ll-loop run sprint-refine-and-implement EPIC-1463`, 2026-09-01). All timestamps from `.loops/.history/2026-09-01T031623-sprint-refine-and-implement/events.jsonl` (UTC):

1. `03:54:58`–`03:57:14` — the shared epic worktree is deleted mid-run (see BUG-3373 for the deleter); a `/ll:refine-issue FEAT-2122 --auto` subprocess is using it as cwd at the time.
2. `03:57:14.937`–`03:57:15.369` — with the cwd now vanished, `refine-to-ready-issue` states (`check_decision_mid_refine`, `check_wire_done`, `normalize_structure`, `check_verify_verdict`, …) each raise `[Errno 2] No such file or directory` at their `Popen(cwd=...)` call, each is caught generically and routed via `on_error`; then the parent `autodev` loop's `skip_inflight`, `dequeue_next`, `finalize_done` states do the same in sequence — roughly 12 such errors in well under a second.
3. `03:57:15.369` — `autodev` reaches `loop_complete` at its generic `failed` terminal (`final_state: failed`, `terminated_by: terminal`, `failure_terminal: true`) — the same terminal any ordinary autodev failure lands on; nothing ties it to the vanished-cwd cause.
4. `03:57:15.371` — `sub_loop_worktree_detached` fires in `auto-refine-and-implement` (a no-op teardown against the already-deleted path); `delegate` routes `on_failure` → `delegate_failed` → `finalize`, and the run finalizes as `incomplete-abandoned`, with the queued issue (ENH-1722) never dequeued and no signal in the verdict naming "worktree vanished" as the cause.

Reproducing without a real incident requires deleting (or renaming) an `FSMExecutor.working_dir` mid-run — e.g. in a test, spin up an executor against a temp directory, remove that directory after the first state dispatches, and assert on the resulting cascade (see this issue's Proposed Solution step 4 for the corresponding test approach).

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- **File**: `scripts/little_loops/fsm/executor.py` (also `scripts/little_loops/fsm/runners.py`)
- **Anchor**: `_run_action_or_route()` (`executor.py:3344-3372`) — the generic exception-to-`on_error` funnel
- **Cause**: Two subprocess-launch sites call `subprocess.Popen(..., cwd=<working dir>)` with no guard around the call itself: `FSMExecutor._run_subprocess` (`executor.py:2543`, Popen at `2559-2566`, used for `mcp_tool` actions) and `DefaultActionRunner.run()`'s shell branch (`runners.py:298-306`, used for ordinary shell actions). When the cwd (a shared worktree) has vanished, Popen raises `FileNotFoundError` uncaught at either site. It propagates up through `_run_action` (`executor.py:2180`) and is caught by `_run_action_or_route`'s bare `except Exception as exc:` (`executor.py:3361`) — the same generic handler used for every other action exception, with no `FileNotFoundError`/`OSError`-specific branch anywhere between either Popen call and this handler. If the failing state declares `on_error`, the handler emits a generic `action_error` event and routes to `on_error` with no distinction for a vanished-cwd cause. Because the cwd stays vanished, every subsequently-reached `on_error`-linked state fails the same way and re-routes the same way, cascading state-by-state until the FSM lands on some `terminal: true` state; `_finish()` (`executor.py:3835-3930`) reports `terminated_by="terminal"` with `failure_terminal` determined solely by whether that landing state happens to be declared `failure: true` in the loop YAML — nothing about the original Popen failure is preserved. Contrast: `DefaultActionRunner.run()`'s prompt-mode branch (`runners.py:232-272`) already converts a launch failure into a normal `ActionResult(exit_code=1, ...)` instead of raising — the shell branch has no equivalent conversion.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-01_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 69/100 → PROCEED (re-scored b6373c410; the body previously still read 64, corrected round 4)

### Outcome Risk Factors
- Broad enumeration across ~15+ touchpoints (executor.py, runners.py, types.py, generate_schemas.py, schema.py, logs.py, plus doc/test wiring) with no single verification grep or automated completeness test tying the full fanout together — Criterion D scored 10/25 (sites enumerated, no verification command) rather than 25/25
- Several dependent-file consumers were reasoned through individually as "no code change needed" (map_final_status default fallback, EXIT_CODES via FAILURE_TERMINAL_EXIT_CODE, etc.) rather than exercised by a test asserting that reasoning holds — mitigate by adding the `workdir_vanished` case to `test_cli_loop_lifecycle.py` already suggested in the Wiring Phase notes to close this gap for at least one consumer

## Session Log
- `/ll:manage-issue` - 2026-09-01T23:48:37 - `8acc57aa-edd5-4430-8650-0d238b555b28.jsonl`
- `/ll:confidence-check` - 2026-09-01T23:00:58 - `d205b9bc-a0cb-4b8a-88a1-5ab0188c6d97.jsonl`
- Manual review 2026-09-01 (pre-implementation, round 5): two fixes. (1) Step 1c rewritten — its premise was wrong (`cmd_run` already resolves `loops_dir` at `run.py:103`, BUG-2386) and absolute paths would not help anyway, since a worker's `.loops`, `run_dir`, and lock dir live *inside* the vanished worktree. Replaced with `OSError` guards on the `workdir_vanished` abort path (`run()` `_finish` call, `PersistentExecutor.run` `save_state`/`archive_run`, `cmd_run` `lock_manager.release`); deliverable for that case is now "exit 1, stderr names the path, no traceback". Step 4's persistence variant now requires `loops_dir` inside the deleted cwd and no longer asserts `events.jsonl` contents; the `test_fsm_persistence.py` `.resolve()` test is dropped. (2) `record_error` needs two MR-11 markers (one per `${captured.delegate.*}` variable), following `delegate_failed`'s precedent. Also noted: place the step 1 check immediately after `state_config = self.fsm.states[...]` (`executor.py:645`), ahead of the retry-tracking block.
- `/ll:confidence-check` - 2026-09-01T22:40:47 - `c86491ed-c494-4931-ae71-56c1f8ef7cbb.jsonl`
- Manual review 2026-09-01 (pre-implementation, round 4): one real gap and three stale-text fixes. (1) The `working_dir=None`/`os.getcwd()` fallback from round 3 was undeliverable as written: `LoopPersistence` paths are cwd-relative (`persistence.py:491`) and `append_event` is unguarded, so `_finish("workdir_vanished")` would itself raise from the event sink and escape `run()` as a traceback. Added step 1c (resolve `loops_dir` absolute at construction) plus a persistence-backed cwd-deletion test. (2) Dropped the wrong "`ll-loop resume` of a run whose worktree is gone" example (resume runs from project root; worktree path is not persisted). (3) Rewrote Integration Map's first executor bullet, which still described the dropped step 1b Popen-site changes, and Program Design's Call Path, which still called for a `_pending_*` flag. (4) Confidence notes body said 64, frontmatter 69. All other cited line numbers re-verified against main.
- Manual review 2026-09-01 (pre-implementation, round 3): three gaps closed. (1) finalize's `case "$VERDICT"` exit-1 arm and the `test_builtin_loops.py` finalize harness's `expected_rc` tuple must include `infra-worktree-vanished`, else the run exits 0 → green `done`. (2) The pre-dispatch check must fall back to `os.getcwd()` when `working_dir is None` — top-level `ll-loop run`/`resume` executors never set it, so the `is not None` guard alone would skip them. (3) `record_error`'s marker line needs `${captured.delegate.error?}` (optional) and an MR-11 `mr11-ok` annotation. Added the nesting note for test 4 (one `route` per level is expected) and a `working_dir=None` cwd-deletion test. Re-verified all cited line numbers against main today.
- Manual review 2026-09-01 (pre-implementation, round 2): corrected Summary/Current Behavior/repro — both sub-loops ended at their `failed` terminal with `failure_terminal: true` (events.jsonl 571, 585), not a "clean" terminal; the defect is indistinguishability, not a clean exit. Named `auto-refine-and-implement` (not `sprint-refine-and-implement`) as the worktree-attaching parent. Fixed step 3/3b contradiction: `delegate.on_error` is `record_error`, so the marker moves there and `delegate_failed` is untouched. Dropped step 1b and the runners.py test. Added 3c (no re-dispatch recovery, scope boundary), the iteration-one missing-dir edge case, and the optional `EXIT_CODES` completeness note.
- `/ll:confidence-check` - 2026-09-01T22:06:07 - `e7481ca4-ea29-4d74-85c9-acbd0706ed86.jsonl`
- Manual review 2026-09-01 (pre-implementation): corrected four wiring claims that assumed `failure_terminal=True` (`_finish` only sets it for `terminated_by="terminal"`): exit code is 1 via a new explicit `EXIT_CODES` entry, not `FAILURE_TERMINAL_EXIT_CODE`; `refine-to-ready-issue.yaml`'s `True:*` arm does not match; worker_pool/queue/gate see the generic non-zero bucket. Noted `_derive_loop_outcome` already returns `"error"` via the `error` key. Moved the pre-dispatch check ahead of the terminal-state check (`executor.py:665`). Decided parent routing joins the `error` branch of `_execute_sub_loop`, and added step 3b (`delegate_failed` arm + `infra-worktree-vanished` verdict) to satisfy Expected Behavior #3. Strengthened test criteria.
- `/ll:confidence-check` - 2026-09-01T21:40:51 - `4b16ef85-c362-493d-849c-c846475b72fa.jsonl`
- Manual review 2026-09-01: pre-dispatch existence check made the primary detector (prompt-mode branch swallows launch failures, so Popen-site catching alone misses most states); `exc.filename == cwd` discriminator documented; sub-loop propagation rule stated (none needed); `des-audit.md` confirmed hand-maintained; `_derive_loop_outcome` bucket decided as `"error"`.
- `/ll:format-issue` - 2026-09-01T21:22:14 - `1d545f12-483a-4164-8eb9-869bb2218b10.jsonl`
- `/ll:confidence-check` - 2026-09-01T21:18:13 - `af7d0948-35ab-4cf4-ba66-d9d4fed80c50.jsonl`
- `/ll:wire-issue` - 2026-09-01T21:11:04 - `27ab64ec-faa5-4f8f-b9db-d62e91a3f572.jsonl`
- `/ll:refine-issue` - 2026-09-01T20:49:16 - `87c7efdc-d115-415c-a741-428b9e0191a6.jsonl`
