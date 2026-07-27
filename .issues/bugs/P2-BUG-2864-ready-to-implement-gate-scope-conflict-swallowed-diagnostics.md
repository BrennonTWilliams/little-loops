---
id: BUG-2864
type: BUG
title: ready-to-implement-gate scope conflict + swallowed diagnostics cause spurious
  gate_blocked deferrals
priority: P2
status: done
captured_at: '2026-07-27T18:31:32Z'
completed_at: '2026-07-27T19:11:35Z'
discovered_date: 2026-07-27
discovered_by: capture-issue
labels:
- learning-gate
- fsm-concurrency
- autodev
- ll-loop
relates_to:
- BUG-2833
- BUG-1359
- ENH-2834
confidence_score: 98
outcome_confidence: 89
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 22
---

# BUG-2864: ready-to-implement-gate scope conflict + swallowed diagnostics cause spurious gate_blocked deferrals

## Summary

`autodev` deferred ENH-2863 with `deferred_reason: gate_blocked` ("unproven external-API deps") even though nothing was actually wrong with the `codegraph` learning-test target — its proof already existed on disk minutes before the block was recorded. The real cause is a scope-lock false conflict in the nested `ll-loop run ready-to-implement-gate` subprocess that `run_learning_gate_for_issue`'s targets-branch shells out to, combined with that branch discarding the subprocess's diagnostic output and collapsing every non-zero exit to `"blocked"`.

## Steps to Reproduce

1. Start any loop that holds a narrow scope lock and runs for several minutes —
   e.g. `ll-loop run prompt-across-issues ...` (scoped to its own
   `${context.run_dir}` per `prompt-across-issues.yaml:34-35`). Leave it running.
2. Concurrently, run `ll-auto` (or `ll-loop run autodev`) on an issue that has a
   non-empty `learning_tests_required` registry, so
   `run_learning_gate_for_issue()` takes the ENH-2834 targets-branch.
3. The nested `ll-loop run ready-to-implement-gate` subprocess resolves its scope
   to the default `["."]`, which `_paths_overlap()` reports as overlapping the
   unrelated loop's `run_dir`. `LockManager.acquire()` returns `False` and
   `cli/loop/run.py:427-431` exits `1` before any run directory is created.
4. Observe: `LEARNING_GATE_BLOCKED <ID>` is printed, the issue is deferred with
   `deferred_reason: gate_blocked`, and `.loops/runs/` contains no
   `ready-to-implement-gate` run for that timestamp — `/ll:explore-api` never ran.

Observed in `autodev-20260727T123139` (ENH-2863); the two `prompt-across-issues`
loops were active `12:33:49`/`12:34:06` → `12:52`/`12:54`, and the gate fired at
`12:47:21`.

## Current Behavior

1. `run_learning_gate_for_issue()` (`scripts/little_loops/learning_tests/gate.py:111-125`, added by ENH-2834) runs, for a non-empty `targets` list:
   ```python
   cmd = ["ll-loop", "run", "ready-to-implement-gate", "--context", f"targets={...}"]
   proc = subprocess.run(cmd, capture_output=True, text=True, cwd=working_dir)
   return "passed" if proc.returncode == 0 else "blocked"
   ```
   `proc.stdout` / `proc.stderr` are captured but never logged or inspected — any failure reason is silently discarded, and every non-zero exit collapses to `"blocked"`.

   The exit code already carries the information needed to discriminate: a
   `failure: true` terminal exits `FAILURE_TERMINAL_EXIT_CODE` (`= 2`,
   `scripts/little_loops/fsm/types.py:25`, emitted by
   `scripts/little_loops/cli/loop/_helpers.py:1926`), while a scope-lock conflict
   exits `1` (`cli/loop/run.py:427-431`). The targets-branch ignores the
   distinction.

2. `ready-to-implement-gate.yaml` declares no `scope:` field. `LockManager.acquire()` (`scripts/little_loops/fsm/concurrency.py:162-164`) treats an empty/missing scope as `["."]` — the whole repository. `_paths_overlap()` (`concurrency.py:398-423`) treats path containment as overlap, so a `["."]` scope conflicts with *every other* currently-running scoped loop lock in the repo, not just its own parent.

3. The `find_conflict()` ancestor carve-out (`concurrency.py:259`, added for BUG-1359) only exempts locks held by an actual process ancestor of the caller. It correctly exempts the parent `autodev` process's own lock, but cannot exempt unrelated sibling loops running concurrently elsewhere in the repo.

4. In the observed run (`autodev-20260727T123139`), two unrelated `prompt-across-issues` loops were active from `12:33:49`/`12:34:06` through `12:52`/`12:54` (each correctly scoped to its own `${context.run_dir}`, per `prompt-across-issues.yaml:34-35`). When the nested `ll-loop run ready-to-implement-gate` fired at `12:47:21`, its default `.`-scope overlapped with those unrelated locks, `LockManager.acquire()` returned `False`, and `cli/loop/run.py:427-431` (`elif conflict: ... return 1`) exited 1 — **before** `run_dir.mkdir()` at `run.py:570`, so no run directory was ever created and `/ll:explore-api` was never invoked.

5. `run_learning_gate_for_issue()` saw the non-zero exit, returned `"blocked"`, and `issue_manager.py` printed `LEARNING_GATE_BLOCKED ENH-2863` — indistinguishable from a genuine "target refuted after retries" outcome. `autodev`'s `mark_gate_blocked` state then deferred the issue via `ll-issues set-status ENH-2863 deferred --by automation --reason gate_blocked`, pointing at the wrong remedy (re-running `/ll:explore-api`) for what was actually a lock collision.

6. `proof-first-task.yaml` likewise declares no `scope:` (confirmed — `proof-first-task.yaml:1-14`), so the *fallback* branch's `ll-loop run proof-first-task` subprocess is exposed to exactly the same false conflict. Both loops need the fix.

This is a second occurrence of the discrimination gap BUG-2833 fixed in the (older) `proof-first-task` fallback branch of the same function — ENH-2834's newer targets-branch reintroduced the same "any non-zero exit means blocked" collapse. `scripts/little_loops/parallel/worker_pool.py:105-111` already performs the correct `FAILURE_TERMINAL_EXIT_CODE` check against this very gate, so the targets-branch is the outlier among the gate's subprocess callers, not the norm.

## Expected Behavior

- `ready-to-implement-gate.yaml` should declare a narrow lock scope (e.g. `scope: ["${context.run_dir}"]`, matching the pattern used by `autodev.yaml` and `prompt-across-issues.yaml`) so it never collides with unrelated concurrent loops purely by virtue of defaulting to whole-repo scope.
- `run_learning_gate_for_issue()`'s targets-branch should not silently discard `proc.stdout`/`proc.stderr` on a non-zero exit — at minimum log it so a lock conflict is visible in `ll-auto`'s output instead of being indistinguishable from a genuine refuted-target block.
- A scope-lock conflict (or any other infra failure) should surface a *distinct verdict* from a genuine refuted-target block, so `autodev` doesn't stamp `deferred_reason: gate_blocked` for what is actually infrastructure contention. Exit code `1` vs `FAILURE_TERMINAL_EXIT_CODE` already carries this signal — the branch just has to read it.

## Root Cause

Three compounding issues, same shape as BUG-1359's three-part root cause:

1. **Missing `scope:` on `ready-to-implement-gate.yaml` (and `proof-first-task.yaml`)** defaults the lock to the entire repo, guaranteeing conflicts with any other concurrently running scoped loop. This is the primary cause.
2. **Undifferentiated verdict** in `run_learning_gate_for_issue()`'s targets-branch — `"passed" if proc.returncode == 0 else "blocked"` throws away the exit-code distinction between `1` (infra/lock failure) and `FAILURE_TERMINAL_EXIT_CODE` (genuine `blocked` terminal), so a lock conflict and a refuted target are indistinguishable to `autodev`. Discarding `proc.stdout`/`proc.stderr` compounds it by leaving no forensic trail.

**Not a root cause (scoped out):** the CLI shell-out itself. BUG-1359 moved `outer-loop-eval` to the native `_execute_sub_loop()` path (which bypasses `LockManager` entirely), and `proof-first-task.yaml:gate_direct` already invokes `ready-to-implement-gate` natively via `loop:`. Only the Python caller in `gate.py` shells out. Migrating it to the executor is a substantially larger change and is unnecessary once the scope is narrowed — noted here so the fix isn't over-scoped.

## Proposed Solution

1. Add `scope: ["${context.run_dir}"]` to `ready-to-implement-gate.yaml` and `proof-first-task.yaml` (mirrors `autodev.yaml:26-27` / `prompt-across-issues.yaml:34-35`). Verified safe: `cli/loop/run.py:189-198` seeds `run_dir` into `fsm.context` *before* `resolve_scope()` at `run.py:363`, so the template resolves at acquire time even though the directory itself isn't created until `run.py:570`.

2. Make the targets-branch discriminate on the exit code, mirroring `worker_pool.py:105-111`. `ready-to-implement-gate` has exactly one failure terminal (`blocked`), so — unlike the `proof-first-task` fallback branch — no `list_run_history()` lookup is needed:

   ```python
   if proc.returncode == 0:
       return "passed"
   if proc.returncode == FAILURE_TERMINAL_EXIT_CODE:
       return "blocked"
   # Infra failure (scope-lock conflict, crash, missing binary) — not a
   # refuted target. Log the captured output so the reason is recoverable.
   logger.error(
       "ready-to-implement-gate failed with exit %d (not a refuted target)\n"
       "stdout: %s\nstderr: %s",
       proc.returncode, proc.stdout, proc.stderr,
   )
   return "impl_failed"
   ```

   This converts the misdiagnosis into a *correct* verdict; the logging is supplementary forensics, not the fix.

3. **Do not add `--queue`.** On a false conflict it makes things worse — the gate blocks until `wait_for_scope` times out instead of failing fast, and BUG-1359 documents its deadlock risk against an ancestor's lock. Step 1 removes the conflict; step 2 reports it honestly if one somehow recurs.

## Implementation Steps

1. Add the missing `scope: ["${context.run_dir}"]` field to both `ready-to-implement-gate.yaml` and `proof-first-task.yaml`.
2. Update `run_learning_gate_for_issue()`'s targets-branch to discriminate on `FAILURE_TERMINAL_EXIT_CODE` (returning `"impl_failed"` for any other non-zero exit) and log the captured `proc.stdout`/`proc.stderr` on the infra path. Also rewrite the function's docstring (lines 74-78) — its "no `impl_failed`-equivalent terminal" rationale becomes stale once this branch gains the discrimination.
3. Add a direct unit test on `run_learning_gate_for_issue`: with `targets` non-empty and a mocked `subprocess.run` returning exit `1`, assert the verdict is **not** `"blocked"`; with exit `2`, assert it **is** `"blocked"`. This is the actual regression guard, and mirrors the test BUG-2833 added for the fallback branch. Update `test_unproven_target_yields_blocked_without_history_lookup` (`test_learning_tests_gate.py:216-230`) in place — its `mock_history.assert_not_called()` assertion stays correct, but the expected verdict on `returncode=1` flips from `"blocked"` to `"impl_failed"`.
4. Verify at the concurrency layer: reproduce a scope collision (two loops with disjoint `${context.run_dir}` scopes plus one defaulted to `["."]`) and confirm the narrowed scope stops `ready-to-implement-gate` from spuriously conflicting. Mirror `test_concurrency.py`'s `TestMultiInstanceSameName` pair (`test_autodev_with_run_dir_scopes_both_acquire_concurrently` / `test_autodev_with_dot_scope_still_conflicts`) for `ready-to-implement-gate`/`proof-first-task`, and add `test_scope_declared` methods to `TestReadyToImplementGateLoop`/`TestProofFirstTaskLoop` in `test_builtin_loops.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — add `scope:`
- `scripts/little_loops/loops/proof-first-task.yaml` — add `scope:` (confirmed missing, same gap)
- `scripts/little_loops/learning_tests/gate.py` — exit-code discrimination + diagnostics logging in the targets-branch (~line 111-125)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` (`process_issue_inplace`, ~line 874-899) — consumes `run_learning_gate_for_issue()`'s verdict
- `scripts/little_loops/loops/autodev.yaml` (`check_learning_gate` / `mark_gate_blocked` states) — routes on the `LEARNING_GATE_BLOCKED` marker
- `scripts/little_loops/loops/rn-implement.yaml`, `rn-remediate.yaml` — also call the learning gate

### Similar Patterns
- `scripts/little_loops/parallel/worker_pool.py:105-111` — **the reference implementation**: already checks `FAILURE_TERMINAL_EXIT_CODE` against this same gate. Copy this shape into the targets-branch.
- `scripts/little_loops/learning_tests/gate.py:144-149` (fallback branch) — BUG-2833's discrimination fix; the targets-branch is the regression against it.
- `scripts/little_loops/fsm/concurrency.py` (`LockManager.find_conflict`) — ancestor carve-out pattern that any other nested-loop-via-subprocess caller should also audit for whole-repo-default scope gaps

### Tests
- `scripts/tests/test_learning_tests_gate.py` (or equivalent) — exit-code discrimination on the targets-branch: exit `1` → not `"blocked"`, exit `2` → `"blocked"` (the primary regression guard)
- FSM concurrency tests covering `ready-to-implement-gate`'s and `proof-first-task`'s scope

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_concurrency.py` — `TestMultiInstanceSameName` (lines ~605-667) is the exact pattern to mirror for the "verify at the concurrency layer" step: `test_autodev_with_run_dir_scopes_both_acquire_concurrently` (two instances with disjoint `${context.run_dir}` scopes both acquire) paired with `test_autodev_with_dot_scope_still_conflicts` (both instances with `["."]` scope conflict). Add an analogous pair substituting `"ready-to-implement-gate"` / `"proof-first-task"` for `"autodev"` — no existing test in this file references either loop by name today.
- `scripts/tests/test_builtin_loops.py` — `TestReadyToImplementGateLoop` (`LOOP_FILE` at line ~8583) and `TestProofFirstTaskLoop` (`LOOP_FILE` at line ~8789) currently assert only `prove`/`done`/`blocked` state shape, with no assertion on the new `scope:` field. Add a `test_scope_declared` method to each, copying the assertion body already used for `prompt-across-issues.yaml` (lines ~2476-2489) and `autodev.yaml` (lines ~5894-5904): `scope` is a list containing `"${context.run_dir}"`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`gate.py` has no logger today.** `scripts/little_loops/learning_tests/gate.py` currently has no `import logging` / module-level `logger` at all (confirmed absent from lines 1-22). The proposed fix's `logger.error(...)` call (step 2 of Proposed Solution) needs `import logging` plus `logger = logging.getLogger(__name__)` added at module top first. Sibling modules establish the convention to copy: `scripts/little_loops/learning_tests/extractor.py:31` and `scripts/little_loops/parallel/worker_pool.py:31` (`logger = logging.getLogger(__name__)`).
- **`worker_pool.py` line numbers**: the reference discrimination pattern actually spans lines **103-119** (function-local `FAILURE_TERMINAL_EXIT_CODE` import at line 105, the `== FAILURE_TERMINAL_EXIT_CODE` check at 111, the fallthrough `!= 0` check at 116), not 105-111 as stated elsewhere in this issue — the fallthrough branch (generic non-zero, logged via `logger.warning`) is the part to mirror for the new `"impl_failed"` path.
- **Existing test needs updating, not just a new test added.** `scripts/tests/test_learning_tests_gate.py:216-230` — `test_unproven_target_yields_blocked_without_history_lookup` currently asserts the *old* behavior (`returncode=1` → `"blocked"`). Once the fix lands, this exact input should assert `"impl_failed"` instead; leaving it unchanged will make it a false-negative regression test rather than a genuine coverage gap. `TestRunLearningGateForIssueTerminalDiscrimination` (same file, lines 107-174, the already-fixed fallback-branch tests) is the correct pattern to mirror for the new targets-branch assertions, including the `_ok_result`/`_failed_result`-style mock helpers (lines 112-119, one for `returncode=1`, one for `returncode=FAILURE_TERMINAL_EXIT_CODE`).
- **`"impl_failed"` is already a fully-wired verdict** — no new downstream handling is needed. `scripts/little_loops/issue_manager.py:899-916` already routes `"impl_failed"` to an `IMPLEMENT_FAILED` marker (added by BUG-2833 for the fallback branch), distinct from the `"blocked"` → `LEARNING_GATE_BLOCKED` marker at lines 884-891. Reusing `"impl_failed"` in the targets-branch plugs into this existing routing rather than requiring new autodev.yaml wiring.
- Additional test files touching this surface, not currently listed: `scripts/tests/test_builtin_loops.py` (loop-level tests including `ready-to-implement-gate`) and `scripts/tests/test_cli_learning_tests.py` (CLI integration).

_Wiring pass added by `/ll:wire-issue`:_
- **`gate.py`'s own docstring goes stale once the fix lands.** `run_learning_gate_for_issue()`'s docstring (lines 74-78, in the same file being edited) currently states as design rationale that `ready-to-implement-gate` has "no `impl_failed`-equivalent terminal to conflate it with (structurally eliminates BUG-2833's discrimination need for this branch)." That claim becomes false once the targets-branch starts returning `"impl_failed"` for infra failures — leaving it unrewritten actively misdescribes the new behavior to future readers of the function it's attached to. Update this paragraph as part of Implementation Step 2, not as a separate file.
- **No `list_run_history()` lookup is needed or should be added to the targets-branch.** Confirmed by reading current `gate.py`: `ready-to-implement-gate` truly has only one failure terminal (`blocked`), so unlike the fallback branch (lines 141-150, which does call `list_run_history` against `"proof-first-task"`), the fix is exit-code discrimination alone — no new import or history-lookup call in the targets-branch. `test_unproven_target_yields_blocked_without_history_lookup`'s existing `mock_history.assert_not_called()` assertion (line ~229) stays correct after the fix; only the expected verdict string on `returncode=1` changes from `"blocked"` to `"impl_failed"`.
- **No downstream file needs modification.** Traced `issue_manager.py`'s `"impl_failed"` routing (lines 899-916, added by BUG-2833), `autodev.yaml`'s marker-based routing, and `docs/guides/LEARNING_TESTS_GUIDE.md` / `docs/guides/LOOPS_REFERENCE.md` — all already handle or describe the existing `impl_failed` verdict/marker generically and require no edits for this fix. `scope:` is an already-schema-supported FSM field (used identically by `autodev.yaml`, `prompt-across-issues.yaml`, etc.) with no `ll-loop validate` rule affected by adding it.

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — silent misdiagnosis of a working dependency as unproven, causing incorrect automated `deferred` status and pointing operators at the wrong remedy; requires two unrelated loops running concurrently to trigger, so not on every run, but reproducible and already observed in production (`autodev-20260727T123139`).
- **Effort**: Small — one YAML field, one logging addition, optional retry/queue tweak.
- **Risk**: Low — scope narrowing is a strict improvement (matches sibling loops' existing pattern); logging addition is additive.

## Resolution

Fixed all three root-cause items from the Proposed Solution:

1. Added `scope: ["${context.run_dir}"]` to `ready-to-implement-gate.yaml` and
   `proof-first-task.yaml`, matching `autodev.yaml`/`prompt-across-issues.yaml`.
2. `run_learning_gate_for_issue()`'s targets-branch now discriminates the exit
   code (`0` → `"passed"`, `FAILURE_TERMINAL_EXIT_CODE` → `"blocked"`, any
   other non-zero → `"impl_failed"` with the captured stdout/stderr logged via
   a new module logger), mirroring `worker_pool.py`'s reference pattern.
3. Updated the function's stale docstring paragraph describing the old
   "no impl_failed-equivalent terminal" rationale.

Added regression coverage: exit-code discrimination unit tests in
`test_learning_tests_gate.py`, `scope:` structural assertions in
`test_builtin_loops.py` for both loops, and a mirrored
`TestMultiInstanceSameName` concurrency pair (`ready-to-implement-gate`
run_dir-scopes-acquire / dot-scope-still-conflicts) in `test_concurrency.py`.

Full suite: 16529 passed, 42 skipped, 1 pre-existing unrelated failure
(`test_prose_dep_sweep_gate.py` — EPIC-2861 prose drift, confirmed present
on `main` before this change via `git stash`).

## Session Log
- `/ll:ready-issue` - 2026-07-27T19:04:23 - `3e6a394a-a182-43ca-9486-59ac42200912.jsonl`
- `/ll:wire-issue` - 2026-07-27T19:01:55 - `96d436de-65b9-44ae-bd06-c3c03cf32bc1.jsonl`
- `/ll:refine-issue` - 2026-07-27T18:54:57 - `b53512c1-6b4b-4d63-9711-15a3e88f6d93.jsonl`
- `/ll:capture-issue` - 2026-07-27T18:31:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dcfb128-c63e-4435-9921-1c0faca51cab.jsonl`

---
## Status
- [ ] Open
