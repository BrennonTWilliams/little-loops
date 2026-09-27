---
id: BUG-3634
type: BUG
title: diff_stall evaluator fingerprints main tree instead of worktree child_working_dir
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T05:28:45Z'
---

# BUG-3634: diff_stall evaluator fingerprints main tree instead of worktree child_working_dir

## Summary

`evaluate_diff_stall`'s git commands run with no `cwd=`, so a `diff_stall`
evaluator state inside a `worktree:` child FSM fingerprints the main tree
instead of the worktree where the child loop's actual edits land.

## Current Behavior

`evaluate_diff_stall` (`little_loops.fsm.evaluators`) runs its git commands
(`git ls-files`, `git hash-object`, `git rev-parse --show-toplevel`) with no
`cwd=` argument, so it always fingerprints the process's current working
directory — the main tree. A `diff_stall` state that lives inside a
`worktree:` child FSM (`executor.py` `child_working_dir`, ~:1232) fingerprints
the wrong tree: the main checkout, not the worktree where the child loop's
actual edits land.

## Expected Behavior

The evaluator fingerprints the worktree's own working directory when it runs
inside a `worktree:` child. `evaluate()` (`fsm/evaluators.py`) needs the
executor's resolved working directory threaded through to
`evaluate_diff_stall`/`_diff_stall_fingerprint`, and every `subprocess.run`
call inside the fingerprint helper needs a `cwd=` argument.

## Motivation

Discovered during BUG-3627 (diff_stall content-fingerprint rewrite). Explicitly
scoped out of that issue: "today the git commands run with no `cwd=`, so a
diff_stall state inside a `worktree:` child (`executor.py` ~:1232,
`child_working_dir`) fingerprints the main tree instead of the worktree...
the evaluator needs the executor's working dir threaded through to
`evaluate()`."

## Acceptance Criteria

- `_run_git`, `_diff_stall_fingerprint`, and `evaluate_diff_stall` accept a
  `cwd`/`working_dir` parameter and every `subprocess.run` call inside the
  fingerprint path uses it.
- `evaluate()`'s `diff_stall` branch (`fsm/evaluators.py` ~:2105) and
  `InterpolationContext` thread the executor's resolved working directory
  (`self.working_dir` / `child_working_dir`, `executor.py` ~:1208) through to
  `evaluate_diff_stall`.
- A `diff_stall` state inside a `worktree:` child fingerprints the worktree's
  working tree, not the main checkout.
- Non-worktree `diff_stall` behavior is unchanged: with no working-dir
  override, the fingerprint still resolves against `Path.cwd()`.
- A test in `scripts/tests/test_fsm_evaluators.py` covers a `cwd` argument
  producing a fingerprint from a directory other than `Path.cwd()`.

## Steps to Reproduce

1. Define a loop with a `worktree:` block whose child FSM has a `diff_stall`
   evaluator state.
2. Run the loop so the child executes inside the worktree
   (`child_working_dir` set at `executor.py` ~:1208/1248).
3. Make an edit only inside the worktree checkout, leaving the main tree
   untouched.
4. Observe: `diff_stall` fingerprints the main tree (`Path.cwd()`) instead of
   the worktree, so the worktree edit is invisible to the fingerprint and the
   state is reported as stalled despite real progress.

## Program Design

### Types

- `InterpolationContext.working_dir: Path | None` (new field, `fsm/interpolation.py`)

### Signatures

- `_run_git(args: list[str], stdin: str | None = None, cwd: Path | None = None) -> str`
- `_diff_stall_fingerprint(scope: list[str] | None, run_dir: Path | None, cwd: Path | None = None) -> str`
- `evaluate_diff_stall(scope: list[str] | None = None, max_stall: int = 1, state_dir: Path | None = None, state_key: str = "", cwd: Path | None = None) -> EvaluationResult`

### Call Path

`Executor._evaluate` -> `evaluate()` (`fsm/evaluators.py` diff_stall branch, ~:2105) -> `evaluate_diff_stall()` -> `_diff_stall_fingerprint()` -> `_run_git()`

## Impact

- **Priority**: P4 - correctness bug, but narrow blast radius: only affects
  loops that put a `diff_stall` evaluator inside a `worktree:` child FSM.
- **Effort**: Small - thread one `cwd`/`working_dir` parameter through three
  existing functions and add `cwd=` to their `subprocess.run` calls.
- **Risk**: Low - additive, default-`None` parameter; non-worktree callers
  keep today's `Path.cwd()` behavior unchanged.
- **Breaking Change**: No.

## Related

- BUG-3627 — diff_stall content fingerprint (this gap is out of scope there).

## Status

**Open** | Created: 2026-09-27 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-09-27T06:06:19 - `5a2b9f7a-3ce6-4168-b70d-09170927290e.jsonl`
