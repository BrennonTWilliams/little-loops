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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- `_diff_stall_fingerprint`'s own `Path.cwd()` call at `fsm/evaluators.py:638` (used to resolve the `run_dir` exclusion pathspec relative to the git toplevel) also needs the threaded `cwd`/`working_dir` value — not just the three `_run_git` call sites named above — or a worktree child's exclusion pathspec still resolves against the wrong tree even after `_run_git` itself is fixed.
- Out of scope: `_stall_state_paths`' own `Path.cwd()` fallback (`fsm/evaluators.py:601`, used only when `state_dir` is `None`) governs where state/snapshot files are written, not the git fingerprint content, and does not need a `cwd` parameter for this issue.

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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

Findings from codebase-locator and codebase-pattern-finder, organized below.

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `_run_git` (:612), `_diff_stall_fingerprint` (:628), `evaluate_diff_stall` (:667), and the `evaluate()` `diff_stall` dispatch branch (:2105-2112) all need a `cwd`/`working_dir` parameter threaded through; `_diff_stall_fingerprint` also calls `Path.cwd()` directly at :638 to resolve the `run_dir` exclusion pathspec — a second ambient-cwd dependency in the same function, not just the three `_run_git` call sites.
- `scripts/little_loops/fsm/interpolation.py` — `InterpolationContext` (:110-146) has no `working_dir` field today; the new field is declared here.
- `scripts/little_loops/fsm/executor.py` — `_build_context()` (:3881-3900) is the single site that constructs `InterpolationContext` and would need to pass `self.working_dir` into the new field. `self.working_dir` already resolves to `child_working_dir` for `worktree:` children (:1208-1294) — no other executor-side change is needed.

### Dependent Files (Callers/Importers)
- `scripts/tests/test_fsm_evaluators.py:14` (imports `fsm.evaluators`) — `TestDiffStallEvaluator` calls `evaluate_diff_stall` directly (:1877, :1998, :2003, :2013-2016, :2021, :2044) via a `_check()` pass-through wrapper (:1874-1877) that forwards `**kw`, so a new `cwd=` kwarg flows through without a wrapper-signature change; dispatcher-level tests (`test_dispatch_diff_stall_bare_context` :2048, `test_dispatch_diff_stall_uses_run_dir_and_names` :2055-2064) go through `evaluate(config, "", 0, InterpolationContext(...))` instead.
- `scripts/tests/test_fsm_interpolation.py` — exercises every existing `InterpolationContext` field individually; a new `working_dir` field needs the same per-field coverage.
- `scripts/little_loops/fsm/executor.py:41` (imports `fsm.evaluators`) — the sole `evaluate(...)` call site is inside `FSMExecutor._evaluate` (~:3212), fed by `ctx = self._build_context()`.

### Conventions in Force
- Both existing stall evaluators already accept executor-derived state as additive, default-`None` parameters (`evaluate_diff_stall`'s `state_dir: Path | None = None` and `evaluate_action_stall`'s matching `state_dir`/`context: InterpolationContext | None = None`, `evaluators.py:667`, `:920`) — evidence that a new `cwd`/`working_dir` parameter following the same default-`None` shape is consistent with how this pair of evaluators already extends.
- `self.working_dir` already propagates through nested/child `FSMExecutor` instances via a constructor parameter defaulting to `None` (`None` = "no override, inherit process cwd"), and is consumed as an explicit `cwd=` argument to `subprocess.Popen`/`subprocess.run` at existing call sites (`executor.py:3047`, `:1808`) — the channel this bug needs extended into the evaluator layer already exists end-to-end for actions; only the evaluator path lacks it.
- `cwd=` is passed to `subprocess.run`/`Popen` both as a bare `Path` and as an explicit `str(Path)` conversion, inconsistently even within `executor.py` itself (`_run_subprocess_direct` at :3047 passes `self.working_dir` unconverted; `_prepatch_git` at :1808 passes `cwd=str(repo_root)`) — no single enforced convention; either form is acceptable for the new `_run_git` `cwd` parameter.
- `evaluate()`'s dispatcher branches for `diff_stall`/`action_stall` currently read `run_dir` out of `context.context["run_dir"]` (the FSM's user `context:` dict) rather than a dedicated `InterpolationContext` field, while `loop_name`/`state_name` *are* dedicated fields read directly off `context` (`evaluators.py:2105-2112`, `:2140`) — two existing precedents for how a value reaches the dispatcher; this issue's own Program Design already specifies the dedicated-field route (`InterpolationContext.working_dir`), consistent with the `loop_name`/`state_name` precedent rather than the `context.context` dict precedent.

### Tests
- `scripts/tests/test_fsm_evaluators.py::TestDiffStallEvaluator` (:1843) — `repo` fixture (:1846-1867) uses `monkeypatch.chdir(repo)` for every existing test, since no `cwd` parameter exists today to pass explicitly instead; a new test passing `cwd=` explicitly (per this issue's Acceptance Criteria) can point at a directory other than the fixture's `monkeypatch`-chdir'd one to prove the parameter is honored.
- `scripts/tests/test_fsm_executor.py:6964+` — the ENH-2609/BUG-3112 `worktree:` per-state tests (`test_worktree_attach_runs_child_inside_and_detaches` :7008-7050, `test_shell_action_in_worktree_resolves_main_repo_history_db` :7197-7231) are the existing precedent for asserting a worktree-child action runs with the worktree as `cwd`; none of them cover a `diff_stall` evaluator inside a worktree child today.

## Program Design

### Types

- `InterpolationContext.working_dir: Path | None` (new field, `fsm/interpolation.py`)

### Signatures

- `_run_git(args: list[str], stdin: str | None = None, cwd: Path | None = None) -> str`
- `_diff_stall_fingerprint(scope: list[str] | None, run_dir: Path | None, cwd: Path | None = None) -> str`
- `evaluate_diff_stall(scope: list[str] | None = None, max_stall: int = 1, state_dir: Path | None = None, state_key: str = "", cwd: Path | None = None) -> EvaluationResult`

### Call Path

`Executor._evaluate` -> `evaluate()` (`fsm/evaluators.py` diff_stall branch, ~:2105) -> `evaluate_diff_stall()` -> `_diff_stall_fingerprint()` -> `_run_git()`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

Findings from codebase-analyzer, organized below.

### Confirmed Anchors (code graph + analyzer verified)
- `_run_git` — `fsm/evaluators.py:612-625`; single `subprocess.run(["git", *args], capture_output=True, text=True, timeout=30, input=stdin)` call at :616-618, no `cwd=` today.
- `_diff_stall_fingerprint` — `fsm/evaluators.py:628-664`; calls `_run_git` at :636, :650, :661, and independently calls `Path.cwd()` at :638 to resolve the `run_dir` exclusion pathspec relative to the git toplevel — a fourth cwd-touching site in this function, not just the three `_run_git` calls named in the Acceptance Criteria.
- `evaluate_diff_stall` — `fsm/evaluators.py:667-753`; calls `_diff_stall_fingerprint(scope, state_dir)` at :707.
- `evaluate()` `diff_stall` dispatch branch — `fsm/evaluators.py:2105-2112` (confirms the issue's `~:2105` estimate exactly).
- `InterpolationContext` — `fsm/interpolation.py:110-146`; current fields `context, captured, prev, result, state_name, iteration, loop_name, started_at, elapsed_ms, messages, messages_summary, param` — no `working_dir` field.
- `FSMExecutor._build_context()` — `fsm/executor.py:3881-3900` — the single site that constructs `InterpolationContext`; does not currently pass `self.working_dir`. This is the concrete injection point the issue's "threaded through to evaluate()" language refers to but does not cite by name.
- `self.working_dir` / `child_working_dir` — `fsm/executor.py:307` (attribute), `:1208` (`child_working_dir = self.working_dir` default), `:1248` (worktree override `child_working_dir = worktree_path`), `:1294` (passed to child `FSMExecutor(working_dir=child_working_dir)`).

### Isolation Check
`cli/loop/evidence.py:_run_git` (:495-507, `repo_root: Path` positional, returns `tuple[int, str]`, already passes `cwd=str(repo_root)`) and `hooks/pre_done.py:_run_git` (:49-63, `root: Path` positional + `*args`, returns `str | None`, already passes `cwd=root`) are separately-defined functions with incompatible signatures — neither imports from `fsm/evaluators.py`. Changing `fsm/evaluators.py`'s `_run_git` signature has no effect on either.

### Error Handling to Preserve
`_diff_stall_fingerprint`'s existing edge cases (non-git dir raises `_GitFingerprintError`, git timeout raises `_GitFingerprintError`, no-commit repo, `run_dir` outside repo caught via `ValueError` at :641-642, dangling untracked symlinks via `os.path.islink` at :655-656) must keep passing once `cwd=` is threaded through — covered today by `TestDiffStallEvaluator` (`scripts/tests/test_fsm_evaluators.py:1843`), all of which currently rely on `monkeypatch.chdir()` rather than an explicit `cwd` parameter.

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
- `/ll:refine-issue` - 2026-09-27T06:18:36 - `d1ce99b0-6533-4a9f-af3f-f35128797a41.jsonl`
- `/ll:format-issue` - 2026-09-27T06:06:19 - `5a2b9f7a-3ce6-4168-b70d-09170927290e.jsonl`
