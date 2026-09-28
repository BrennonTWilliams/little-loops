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
executor's resolved working directory threaded through (as a new
`working_dir=None` keyword argument) to
`evaluate_diff_stall`/`_diff_stall_fingerprint`; every `subprocess.run` call
inside the fingerprint helper needs a `cwd=` argument, and every filesystem
probe on a git-listed path must resolve against that same directory.

## Motivation

Discovered during BUG-3627 (diff_stall content-fingerprint rewrite). Explicitly
scoped out of that issue: "today the git commands run with no `cwd=`, so a
diff_stall state inside a `worktree:` child (`executor.py` ~:1232,
`child_working_dir`) fingerprints the main tree instead of the worktree...
the evaluator needs the executor's working dir threaded through to
`evaluate()`."

## Acceptance Criteria

- `_run_git`, `_diff_stall_fingerprint`, and `evaluate_diff_stall` accept a
  `cwd` parameter and every `subprocess.run` call inside the fingerprint path
  uses it.
- The `os.path.islink` / `os.readlink` / `os.path.isfile` probes inside
  `_diff_stall_fingerprint` resolve each git-listed path against `cwd` (e.g.
  `(cwd or Path.cwd()) / path`), not the process cwd. `git ls-files` output is
  relative to git's cwd, so without this the listing comes from the worktree
  but symlink/file-type detection runs against the main tree.
- The `run_dir` exclusion in `_diff_stall_fingerprint` keeps resolving against
  the **process** cwd (`Path.cwd() / run_dir`), with a comment explaining why:
  the exclusion exists to hide the evaluator's own snapshot files, which
  `_stall_state_paths(state_dir=Path(run_dir))` writes relative to the process
  cwd (the executor never chdirs). Do **not** thread `cwd` into this call.
- `evaluate()` gains a `working_dir: Path | None = None` keyword argument; its
  `diff_stall` branch passes it to `evaluate_diff_stall(cwd=...)`.
  `FSMExecutor._evaluate` passes `self.working_dir` (which is already
  `child_working_dir` inside a `worktree:` child).
- When `cwd` does not exist (e.g. a torn-down worktree), `_run_git` raises
  `_GitFingerprintError` with a message naming the missing working directory,
  not the misleading "git not found in PATH" (`subprocess.run` raises
  `FileNotFoundError` for a missing `cwd` too — distinguish via a pre-check or
  `exc.filename`).
- A `diff_stall` state inside a `worktree:` child fingerprints the worktree's
  working tree, not the main checkout.
- Non-worktree `diff_stall` behavior is unchanged: with no working-dir
  override, the fingerprint still resolves against `Path.cwd()`.
- A test in `scripts/tests/test_fsm_evaluators.py` covers a `cwd` argument
  producing a fingerprint from a directory other than `Path.cwd()`, including
  a symlink in the `cwd` tree (proves the `os.path` probes honor `cwd`).
- A test in `scripts/tests/test_fsm_evaluators.py` covers a nonexistent `cwd`
  yielding `verdict="error"` with a working-directory message.
- A dispatcher-level test calls `evaluate(config, "", 0, ctx, working_dir=X)`
  and proves `X` reaches `evaluate_diff_stall`.
- An executor-level test in `scripts/tests/test_fsm_executor.py` drives
  `FSMExecutor(fsm, working_dir=X).run()` with a `diff_stall` state and
  asserts the fingerprint tracks edits in `X`, not the process cwd (modelled
  on `TestExecutorWorkingDir::test_shell_action_in_worktree_resolves_main_repo_history_db`).
  This is the only test that proves the executor → `evaluate()` wiring.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- ~~`_diff_stall_fingerprint`'s own `Path.cwd()` call at `fsm/evaluators.py:638` also needs the threaded `cwd`/`working_dir` value.~~ **Corrected in review (2026-09-27):** keep `Path.cwd()` there. The `run_dir` exclusion exists to hide the evaluator's own snapshot files, which `_stall_state_paths` writes relative to the *process* cwd (the executor never chdirs). In a `worktree:` child `run_dir` is already made absolute (`FSMExecutor` worktree-attach block, `child_fsm.context["run_dir"] = str(Path(...).resolve())`), so threading `cwd` there is a no-op; for a top-level executor with `working_dir` set and a relative `run_dir` it would point the exclusion at the wrong directory. See Acceptance Criteria.
- Out of scope: `_stall_state_paths`' own `Path.cwd()` fallback (`fsm/evaluators.py:601`, used only when `state_dir` is `None`) governs where state/snapshot files are written, not the git fingerprint content, and does not need a `cwd` parameter for this issue.

## Steps to Reproduce

**Latent — no built-in loop triggers this today.** The only built-in loop with
a `worktree:` state is `auto-refine-and-implement` (its `delegate` state runs
`autodev` in an epic worktree), and the `autodev` chain uses no `diff_stall`
evaluator. Reproduce with a purpose-built loop (or the executor-level test in
the Acceptance Criteria); don't hunt for a live repro in built-in loops.

1. Define a loop with a `worktree:` block whose child FSM has a `diff_stall`
   evaluator state.
2. Run the loop so the child executes inside the worktree
   (`child_working_dir` set in `FSMExecutor`'s per-state worktree-attach
   block, ENH-2609).
3. Make an edit only inside the worktree checkout, leaving the main tree
   untouched.
4. Observe: `diff_stall` fingerprints the main tree (`Path.cwd()`) instead of
   the worktree, so the worktree edit is invisible to the fingerprint and the
   state is reported as stalled despite real progress.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

Findings from codebase-locator and codebase-pattern-finder, organized below.

_Line numbers below were refreshed 2026-09-27 against a working tree carrying
~339 uncommitted, unrelated lines in `fsm/executor.py`; they will drift again.
Anchor on function names. When committing, stage only this issue's hunks in
`executor.py`._

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `_run_git` (:612), `_diff_stall_fingerprint` (:628), `evaluate_diff_stall` (:667) take a new `cwd` parameter; `evaluate()` (:1935) takes a new `working_dir: Path | None = None` keyword argument and its `diff_stall` dispatch branch (~:2107) passes it through. `_diff_stall_fingerprint`'s `Path.cwd()` at :638 (the `run_dir` exclusion) stays as-is, with a comment — see Acceptance Criteria.
- `scripts/little_loops/fsm/evaluators.py:654-658` — inside `_diff_stall_fingerprint`, `os.path.islink(path)` / `os.readlink(path)` / `os.path.isfile(path)` resolve the relative paths returned by `git ls-files` against the process cwd; join `cwd` onto `path` (e.g. `(cwd or Path.cwd()) / path`). Keep the relative `path` string for the hash input and the `hash-object --stdin-paths` list (git resolves those against its own `cwd`).
- `scripts/little_loops/fsm/evaluators.py` `_run_git` — distinguish a missing `cwd` from a missing `git` binary in the `FileNotFoundError` handler.
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._evaluate` (`evaluate(` call ~:3282) passes `working_dir=self.working_dir`. `self.working_dir` already resolves to `child_working_dir` for `worktree:` children (worktree-attach block ~:1243-1329) — no other executor-side change is needed.

_Design note (review 2026-09-27):_ the earlier plan added an
`InterpolationContext.working_dir` field set in `_build_context()`. Replaced
with an `evaluate()` keyword argument: `InterpolationContext` holds the values
that `${...}` references resolve against, and `working_dir` would not be one of
them (unlike `loop_name`/`state_name`, which are). The keyword argument touches
one call site, needs no `fsm/interpolation.py` change, no
`test_fsm_interpolation.py` coverage, and no `InterpolationContext` doc update.

### Dependent Files (Callers/Importers)
- `scripts/tests/test_fsm_evaluators.py:14` (imports `fsm.evaluators`) — `TestDiffStallEvaluator` calls `evaluate_diff_stall` directly (:1877, :1998, :2003, :2013-2016, :2021, :2044) via a `_check()` pass-through wrapper (:1874-1877) that forwards `**kw`, so a new `cwd=` kwarg flows through without a wrapper-signature change; dispatcher-level tests (`test_dispatch_diff_stall_bare_context` :2048, `test_dispatch_diff_stall_uses_run_dir_and_names` :2055-2064) go through `evaluate(config, "", 0, InterpolationContext(...))` instead.
- `scripts/little_loops/fsm/executor.py:41` (imports `fsm.evaluators`) — the sole executor `evaluate(...)` call site is inside `FSMExecutor._evaluate` (~:3282).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/testing.py:119` — `ll-loop test`'s single-state runner calls `evaluate(...)` directly, outside `FSMExecutor`. This CLI path has no worktree wrapper and always evaluates at the process's own cwd; the new keyword argument defaults to `None`, so no change is required.
- `scripts/tests/test_fsm_evaluators.py::test_dispatch_diff_stall_bare_context` (:2048) and `::test_dispatch_diff_stall_uses_run_dir_and_names` (:2055) — existing dispatcher-level tests; neither passes `working_dir=` today.

### Documentation
- `docs/reference/API.md:6303` — the `evaluate()` signature block; add the `working_dir: Path | None = None` keyword argument.

### Conventions in Force
- Both existing stall evaluators already accept executor-derived state as additive, default-`None` parameters (`evaluate_diff_stall`'s `state_dir: Path | None = None` and `evaluate_action_stall`'s matching `state_dir`/`context: InterpolationContext | None = None`, `evaluators.py:667`, `:920`) — evidence that a new `cwd`/`working_dir` parameter following the same default-`None` shape is consistent with how this pair of evaluators already extends.
- `self.working_dir` already propagates through nested/child `FSMExecutor` instances via a constructor parameter defaulting to `None` (`None` = "no override, inherit process cwd"), and is consumed as an explicit `cwd=` argument to `subprocess.Popen`/`subprocess.run` at existing call sites (`executor.py:3047`, `:1808`) — the channel this bug needs extended into the evaluator layer already exists end-to-end for actions; only the evaluator path lacks it.
- `cwd=` is passed to `subprocess.run`/`Popen` both as a bare `Path` and as an explicit `str(Path)` conversion, inconsistently even within `executor.py` itself (`_run_subprocess_direct` at :3047 passes `self.working_dir` unconverted; `_prepatch_git` at :1808 passes `cwd=str(repo_root)`) — no single enforced convention; either form is acceptable for the new `_run_git` `cwd` parameter.
- `evaluate()`'s dispatcher branches for `diff_stall`/`action_stall` currently read `run_dir` out of `context.context["run_dir"]` (the FSM's user `context:` dict), while `loop_name`/`state_name` are dedicated `InterpolationContext` fields (`evaluators.py:2105-2112`, `:2140`). Both are `${...}`-resolvable values. `working_dir` is not, so it reaches the dispatcher through a third route: an explicit `evaluate()` keyword argument, matching how `model` is already passed (`evaluate(config, output, exit_code, context, model=None)`).

### Tests
- `scripts/tests/test_fsm_evaluators.py::TestDiffStallEvaluator` (:1843) — `repo` fixture (:1846-1867) uses `monkeypatch.chdir(repo)` for every existing test, since no `cwd` parameter exists today to pass explicitly instead; a new test passing `cwd=` explicitly (per this issue's Acceptance Criteria) can point at a directory other than the fixture's `monkeypatch`-chdir'd one to prove the parameter is honored.
- `scripts/tests/test_fsm_executor.py:6964+` — the ENH-2609/BUG-3112 `worktree:` per-state tests (`test_worktree_attach_runs_child_inside_and_detaches` :7008-7050, `test_shell_action_in_worktree_resolves_main_repo_history_db` :7197-7231) are the existing precedent for asserting a worktree-child action runs with the worktree as `cwd`; none of them cover a `diff_stall` evaluator inside a worktree child today.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_evaluators.py::test_dispatch_diff_stall_bare_context` (:2048) and `::test_dispatch_diff_stall_uses_run_dir_and_names` (:2055) — extend one with a sibling case calling `evaluate(config, "", 0, ctx, working_dir=<dir>)` to prove the dispatcher threads it into `evaluate_diff_stall`'s new `cwd` param.
- `scripts/tests/test_fsm_executor.py::TestExecutorWorkingDir::test_shell_action_in_worktree_resolves_main_repo_history_db` (:7197) is the closer end-to-end template for the required executor-level test than `test_worktree_attach_runs_child_inside_and_detaches` (:7008): it drives `FSMExecutor(fsm, working_dir=X).run()` directly with a single evaluate state and no `setup_worktree`/`cleanup_worktree` mocking, matching this fix's actual mechanism (`_evaluate` passing `self.working_dir`) without needing sub-loop worktree-attach machinery.

## Program Design

### Types

- No new types. (`InterpolationContext` is unchanged — see the design note under Files to Modify.)

### Signatures

- `evaluate(config: EvaluateConfig, output: str, exit_code: int, context: InterpolationContext, model: str | None = None, working_dir: Path | None = None) -> EvaluationResult`
- `_run_git(args: list[str], stdin: str | None = None, cwd: Path | None = None) -> str`
- `_diff_stall_fingerprint(scope: list[str] | None, run_dir: Path | None, cwd: Path | None = None) -> str`
- `evaluate_diff_stall(scope: list[str] | None = None, max_stall: int = 1, state_dir: Path | None = None, state_key: str = "", cwd: Path | None = None) -> EvaluationResult`

### Call Path

`FSMExecutor._evaluate` (passes `working_dir=self.working_dir`) -> `evaluate()` (`fsm/evaluators.py` diff_stall branch, ~:2107) -> `evaluate_diff_stall(cwd=...)` -> `_diff_stall_fingerprint(cwd=...)` -> `_run_git(cwd=...)`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

Findings from codebase-analyzer, organized below.

### Confirmed Anchors (code graph + analyzer verified)
- `_run_git` — `fsm/evaluators.py:612-625`; single `subprocess.run(["git", *args], capture_output=True, text=True, timeout=30, input=stdin)` call at :616-618, no `cwd=` today.
- `_diff_stall_fingerprint` — `fsm/evaluators.py:628-664`; calls `_run_git` at :636, :650, :661; calls `Path.cwd()` at :638 for the `run_dir` exclusion (intentionally left on the process cwd — see Acceptance Criteria); `os.path` probes on git-listed paths at :654-658 (must join `cwd`).
- `evaluate_diff_stall` — `fsm/evaluators.py:667-753`; calls `_diff_stall_fingerprint(scope, state_dir)` at :707.
- `evaluate()` — `fsm/evaluators.py:1935`; `diff_stall` dispatch branch ~:2107.
- `FSMExecutor._evaluate` — `fsm/executor.py:3197`; the `evaluate(` call at ~:3282 is the injection point for `working_dir=self.working_dir`.
- `self.working_dir` / `child_working_dir` — `fsm/executor.py:340` (attribute assignment), `:1243` (`child_working_dir = self.working_dir` default), `:1283` (worktree override `child_working_dir = worktree_path`), `:1288-1291` (worktree child's `run_dir` made absolute), `:1329` (passed to child `FSMExecutor(working_dir=child_working_dir)`).

### Isolation Check
`cli/loop/evidence.py:_run_git` (:495-507, `repo_root: Path` positional, returns `tuple[int, str]`, already passes `cwd=str(repo_root)`) and `hooks/pre_done.py:_run_git` (:49-63, `root: Path` positional + `*args`, returns `str | None`, already passes `cwd=root`) are separately-defined functions with incompatible signatures — neither imports from `fsm/evaluators.py`. Changing `fsm/evaluators.py`'s `_run_git` signature has no effect on either.

### Error Handling to Preserve
`_diff_stall_fingerprint`'s existing edge cases (non-git dir raises `_GitFingerprintError`, git timeout raises `_GitFingerprintError`, no-commit repo, `run_dir` outside repo caught via `ValueError` at :641-642, dangling untracked symlinks via `os.path.islink` at :655-656) must keep passing once `cwd=` is threaded through — covered today by `TestDiffStallEvaluator` (`scripts/tests/test_fsm_evaluators.py:1843`), all of which currently rely on `monkeypatch.chdir()` rather than an explicit `cwd` parameter.

## Impact

- **Priority**: P4 - correctness bug, but narrow blast radius: only affects
  loops that put a `diff_stall` evaluator inside a `worktree:` child FSM, and
  no built-in loop does today (latent).
- **Effort**: Small - add a `working_dir` keyword argument to `evaluate()`,
  thread it as `cwd` through three existing functions, add `cwd=` to their
  `subprocess.run` calls and join it onto the `os.path` probes.
- **Risk**: Low - additive, default-`None` parameter; non-worktree callers
  keep today's `Path.cwd()` behavior unchanged.
- **Breaking Change**: No.

## Related

- BUG-3627 — diff_stall content fingerprint (this gap is out of scope there).

## Status

**Open** | Created: 2026-09-27 | Priority: P4


## Session Log
- `/ll:wire-issue` - 2026-09-27T06:33:10 - `de835f3b-4603-4a08-b7dc-82329ffec1ac.jsonl`
- `/ll:refine-issue` - 2026-09-27T06:18:36 - `d1ce99b0-6533-4a9f-af3f-f35128797a41.jsonl`
- `/ll:format-issue` - 2026-09-27T06:06:19 - `5a2b9f7a-3ce6-4168-b70d-09170927290e.jsonl`
