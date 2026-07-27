---
id: BUG-2864
type: BUG
title: "ready-to-implement-gate scope conflict + swallowed diagnostics cause spurious gate_blocked deferrals"
priority: P2
status: open
captured_at: '2026-07-27T18:31:32Z'
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
---

# BUG-2864: ready-to-implement-gate scope conflict + swallowed diagnostics cause spurious gate_blocked deferrals

## Summary

`autodev` deferred ENH-2863 with `deferred_reason: gate_blocked` ("unproven external-API deps") even though nothing was actually wrong with the `codegraph` learning-test target — its proof already existed on disk minutes before the block was recorded. The real cause is a scope-lock false conflict in the nested `ll-loop run ready-to-implement-gate` subprocess that `run_learning_gate_for_issue`'s targets-branch shells out to, combined with that branch discarding the subprocess's diagnostic output and collapsing every non-zero exit to `"blocked"`.

## Current Behavior

1. `run_learning_gate_for_issue()` (`scripts/little_loops/learning_tests/gate.py:111-125`, added by ENH-2834) runs, for a non-empty `targets` list:
   ```python
   cmd = ["ll-loop", "run", "ready-to-implement-gate", "--context", f"targets={...}"]
   proc = subprocess.run(cmd, capture_output=True, text=True, cwd=working_dir)
   return "passed" if proc.returncode == 0 else "blocked"
   ```
   `proc.stdout` / `proc.stderr` are captured but never logged or inspected — any failure reason is silently discarded.

2. `ready-to-implement-gate.yaml` declares no `scope:` field. `LockManager.acquire()` (`scripts/little_loops/fsm/concurrency.py:162-164`) treats an empty/missing scope as `["."]` — the whole repository. `_paths_overlap()` (`concurrency.py:398-423`) treats path containment as overlap, so a `["."]` scope conflicts with *every other* currently-running scoped loop lock in the repo, not just its own parent.

3. The `find_conflict()` ancestor carve-out (`concurrency.py:259`, added for BUG-1359) only exempts locks held by an actual process ancestor of the caller. It correctly exempts the parent `autodev` process's own lock, but cannot exempt unrelated sibling loops running concurrently elsewhere in the repo.

4. In the observed run (`autodev-20260727T123139`), two unrelated `prompt-across-issues` loops were active from `12:33:49`/`12:34:06` through `12:52`/`12:54` (each correctly scoped to its own `${context.run_dir}`, per `prompt-across-issues.yaml:34-35`). When the nested `ll-loop run ready-to-implement-gate` fired at `12:47:21`, its default `.`-scope overlapped with those unrelated locks, `LockManager.acquire()` returned `False`, and `cli/loop/run.py:427-431` (`elif conflict: ... return 1`) exited 1 — **before** `run_dir.mkdir()` at `run.py:570`, so no run directory was ever created and `/ll:explore-api` was never invoked.

5. `run_learning_gate_for_issue()` saw the non-zero exit, returned `"blocked"`, and `issue_manager.py` printed `LEARNING_GATE_BLOCKED ENH-2863` — indistinguishable from a genuine "target refuted after retries" outcome. `autodev`'s `mark_gate_blocked` state then deferred the issue via `ll-issues set-status ENH-2863 deferred --by automation --reason gate_blocked`, pointing at the wrong remedy (re-running `/ll:explore-api`) for what was actually a lock collision.

This is a second occurrence of the discrimination gap BUG-2833 fixed in the (older) `proof-first-task` fallback branch of the same function — ENH-2834's newer targets-branch reintroduced the same "any non-zero exit means blocked" collapse, and additionally reuses the CLI shell-out-to-`ll-loop run` pattern that BUG-1359 already demonstrated is unsafe for nested loop invocations (that fix moved `outer-loop-eval` to the native `_execute_sub_loop()` path specifically to avoid this class of bug; the targets-branch here still shells out).

## Expected Behavior

- `ready-to-implement-gate.yaml` should declare a narrow lock scope (e.g. `scope: ["${context.run_dir}"]`, matching the pattern used by `autodev.yaml` and `prompt-across-issues.yaml`) so it never collides with unrelated concurrent loops purely by virtue of defaulting to whole-repo scope.
- `run_learning_gate_for_issue()`'s targets-branch should not silently discard `proc.stdout`/`proc.stderr` on a non-zero exit — at minimum log it so a lock conflict is visible in `ll-auto`'s output instead of being indistinguishable from a genuine refuted-target block.
- Ideally, a transient scope-lock conflict should not immediately fail the gate and defer the issue at all — either retry/queue (mirroring `--queue`'s wait-for-scope semantics) or surface a distinct verdict so `autodev` doesn't stamp `deferred_reason: gate_blocked` for what is actually infrastructure contention.

## Root Cause

Three compounding issues, same shape as BUG-1359's three-part root cause:

1. **Missing `scope:` on `ready-to-implement-gate.yaml`** defaults the lock to the entire repo, guaranteeing conflicts with any other concurrently running scoped loop.
2. **CLI shell-out (`subprocess.run(["ll-loop","run",...])`) instead of the native sub-loop path** — the same anti-pattern BUG-1359 fixed for `outer-loop-eval`; going through `cmd_run()` → `LockManager.acquire()` re-exposes the process to scope conflicts that the native `_execute_sub_loop()` path is immune to.
3. **Discarded subprocess diagnostics + undifferentiated verdict** in `run_learning_gate_for_issue()`'s targets-branch — `proc.stdout`/`proc.stderr` are captured then thrown away, and `"passed" if proc.returncode == 0 else "blocked"` cannot distinguish a lock conflict, a crash, or a genuine refuted-target block.

## Proposed Solution

1. Add `scope: ["${context.run_dir}"]` to `ready-to-implement-gate.yaml` (mirrors `autodev.yaml:26-27` / `prompt-across-issues.yaml:34-35`).
2. In `run_learning_gate_for_issue()`'s targets-branch (`scripts/little_loops/learning_tests/gate.py:111-125`), log `proc.stdout`/`proc.stderr` when `proc.returncode != 0` so the actual failure reason is visible instead of collapsing to a generic "unproven external-API deps" message.
3. Consider passing `--queue` (or checking for the specific "Scope conflict with running loop" message and retrying) so a transient lock contention window doesn't immediately deposit the issue into `deferred` state with a misleading reason code.

## Implementation Steps

1. Add the missing `scope:` field to `ready-to-implement-gate.yaml`; check `proof-first-task.yaml` for the same gap.
2. Update `run_learning_gate_for_issue()`'s targets-branch to log captured subprocess output on non-zero exit.
3. Evaluate whether to add `--queue` (or equivalent retry) to the targets-branch subprocess invocation, weighing against BUG-1359's warning that `--queue` can deadlock a child against its own parent's lock when scopes genuinely overlap by ancestry (should be a non-issue once step 1 narrows the scope, but verify).
4. Verify: reproduce a concurrent-loop scope collision in a test (two loops with disjoint `${context.run_dir}` scopes plus one defaulted to `["."]`) and confirm the fix stops `ready-to-implement-gate` from spuriously conflicting.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — add `scope:`
- `scripts/little_loops/loops/proof-first-task.yaml` — check for the same missing-scope gap
- `scripts/little_loops/learning_tests/gate.py` — log subprocess diagnostics in the targets-branch (~line 111-125)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` (`process_issue_inplace`, ~line 874-899) — consumes `run_learning_gate_for_issue()`'s verdict
- `scripts/little_loops/loops/autodev.yaml` (`check_learning_gate` / `mark_gate_blocked` states) — routes on the `LEARNING_GATE_BLOCKED` marker
- `scripts/little_loops/loops/rn-implement.yaml`, `rn-remediate.yaml` — also call the learning gate

### Similar Patterns
- `scripts/little_loops/fsm/concurrency.py` (`LockManager.find_conflict`) — ancestor carve-out pattern that any other nested-loop-via-subprocess caller should also audit for whole-repo-default scope gaps

### Tests
- `scripts/tests/test_learning_tests_gate.py` (or equivalent) — add a case covering a scope conflict on the targets-branch
- FSM concurrency tests covering `ready-to-implement-gate`'s scope

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — silent misdiagnosis of a working dependency as unproven, causing incorrect automated `deferred` status and pointing operators at the wrong remedy; requires two unrelated loops running concurrently to trigger, so not on every run, but reproducible and already observed in production (`autodev-20260727T123139`).
- **Effort**: Small — one YAML field, one logging addition, optional retry/queue tweak.
- **Risk**: Low — scope narrowing is a strict improvement (matches sibling loops' existing pattern); logging addition is additive.

## Session Log
- `/ll:capture-issue` - 2026-07-27T18:31:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dcfb128-c63e-4435-9921-1c0faca51cab.jsonl`

---
## Status
- [ ] Open
