---
id: BUG-3627
type: BUG
title: diff_stall evaluator shares stall state across runs and misses commits, staged,
  and untracked changes
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T03:35:14Z'
---

# BUG-3627: diff_stall evaluator shares stall state across runs and misses commits, staged, and untracked changes

## Summary

`evaluate_diff_stall` (`little_loops.fsm.evaluators`, the evaluator behind the `diff_stall_gate` fragment in `loops/lib/common.yaml`) persists its snapshot and stall counter in a cache that is shared across runs and loops, and compares a signal (`git diff --stat`) that is blind to several kinds of real progress. Result: false stall verdicts, including a stall on the very first check of a fresh run.

## Current Behavior

- **Cross-run / cross-loop cache**: state lives at `.loops/tmp/ll-diff-stall-<md5(scope)>.txt` / `.count`. The key is derived only from `evaluate.scope`; every loop using root scope shares `ll-diff-stall-_root_.*`. Nothing resets it at run start, so a new run inherits the previous run's snapshot and stall count. If the prior run ended stalled (count ≥ max_stall) and the tree still matches its snapshot (e.g. empty diff because everything was committed), the new run's first check increments past the threshold and returns `no` immediately.
- **Commits look like no progress**: `git diff --stat` shows unstaged tracked changes only. A worker that commits each pass produces an empty diff every time → counted as stalled.
- **Staged and untracked changes are invisible**: new files and `git add`-ed edits never change the snapshot.
- **`--stat` is insensitive to same-line-count edits**: replacing content while keeping per-file +/- counts yields an identical snapshot.
- Concurrent runs of different loops in the same project clobber each other's counters.

Affected loops (import `diff_stall_gate` / `type: diff_stall`): `continue-task`, `incremental-refactor`, `generator-evaluator`, `generator-evaluator-flux`, `harness-single-shot`, `harness-multi-item`, `harness-plan-research-implement-report`, `vega-viz`, `generative-art`, `openscad-model-generator`, `canvas-sketch-generator`, `pixi-data-viz`.

## Expected Behavior

- Stall state is scoped per run instance (under `${context.run_dir}` or keyed by run id), so a fresh run always starts at count 0 with no prior snapshot.
- The progress fingerprint changes on any real change: tracked diff (full content, not `--stat`), staged changes, untracked file contents, and `HEAD` sha — excluding the run dir itself. `general-task`'s `final_verify_spin_gate` (BUG-3270) already implements this fingerprint shape in shell.

## Motivation

The stall gate is the non-LLM progress signal that meta-loop rule (2) requires. A signal that false-positives on commits and leaks state between runs routes productive runs to partial terminals — and the pass-1 stall case makes a run's outcome depend on whatever loop last ran in the project.

## Proposed Solution

- Thread the run dir (or run id) into `evaluate_diff_stall` and store state there; fall back to the current `.loops/tmp` path only when no run context exists.
- Replace `git diff --stat` with a content hash of `git diff HEAD` + `HEAD` sha + untracked file contents (`git ls-files --others --exclude-standard`), honoring `scope`.
- Update the fragment description in `loops/lib/common.yaml` and `TestDiffStallGate` in `scripts/tests/test_fsm_fragments.py`.

## Program Design

### Types

- `scope: list[str] | None` — optional pathspecs limiting the fingerprint (unchanged)
- `max_stall: int` — consecutive identical fingerprints before a `no` verdict (unchanged)
- `state_dir: Path | None` — NEW: per-run directory for snapshot/count files; `None` keeps the legacy `.loops/tmp` location

### Signatures

- `evaluate_diff_stall(scope: list[str] | None = None, max_stall: int = 1, state_dir: Path | None = None) -> EvaluationResult` — fingerprint = hash of `git diff HEAD` + `HEAD` sha + untracked paths and contents, scoped and excluding `.loops/`

### Call Path

FSM executor evaluates a state whose `evaluate.type` is `diff_stall` -> `evaluate_diff_stall(scope, max_stall, state_dir=<run dir>)` -> `EvaluationResult` verdict `yes` / `no` / `error` -> state routing

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_diff_stall()` (cache path, fingerprint)
- `scripts/little_loops/fsm/executor.py` — whatever dispatches `diff_stall` must pass run context (run dir / run id)
- `scripts/little_loops/loops/lib/common.yaml` — `diff_stall_gate` fragment description

### Dependent Files (Callers/Importers)
- The 12 loops listed under Current Behavior (behavior change only; no YAML edits expected)

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml` — `final_verify_spin_gate` content fingerprint scoped away from `${context.run_dir}`

### Tests
- `scripts/tests/test_fsm_fragments.py::TestDiffStallGate`
- evaluator unit tests for `evaluate_diff_stall` (locate with grep)

### Documentation
- `docs/guides/LOOPS_GUIDE.md` / `docs/reference/` entries describing `diff_stall` semantics (grep `diff_stall`)

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Current shape: `evaluate_diff_stall(scope, max_stall)` (`fsm/evaluators.py`) runs `git diff --stat [-- scope]` with no `cwd=`, keys state by `md5("|".join(sorted(scope)) or "_root_")[:12]` under `Path.cwd()/.loops/tmp/ll-diff-stall-<key>.{txt,count}`, and nothing in the repo ever deletes those files (no run-start reset, no cleanup). First call (no snapshot) writes count `0` and returns `yes`; equal snapshot increments and returns `no` at `stall_count >= max_stall`; differing snapshot resets to `0`. Git failure/timeout return `error`; file writes are uncaught.
- Run context gap: the only production caller is the `evaluate()` dispatcher branch `elif eval_type == "diff_stall"`, which passes only `scope=config.scope, max_stall=config.max_stall`. `evaluate()` already receives `context: InterpolationContext`, and `ctx.context["run_dir"]` is populated for CLI runs (`cli/loop/run.py` ~:236, `runs/<instance_id or loop_name>/`; `cli/loop/testing.py` ~:217 for simulate). `InterpolationContext` has no run-id field; the instance id is reachable only through the `run_dir` path. `run_dir` may be absent (direct executor use, older tests), so the no-context path must remain valid.
- Schema surface: `EvaluateConfig.scope`/`max_stall` (`fsm/schema.py` ~:134-135, parsed ~:249); validation covers only `max_stall >= 1` (`fsm/validation/structural_rules.py`); `scope` is neither validated nor interpolated. `fsm/fsm-loop-schema.json` (~:829) describes `scope` as "Paths to limit git diff to" — update if fingerprint semantics change.
- Reference fingerprint (`loops/general-task.yaml` `final_verify_spin_gate`): hashes `git diff "$BASELINE_REF" -- . ':(exclude).loops/'` plus sorted untracked paths (`git ls-files -o --exclude-standard -z`) plus `git hash-object` of each untracked file, via `git hash-object --stdin`. It excludes the whole `.loops/` tree, not just the run dir, because `ll-init` ships no `.loops/` gitignore entry to consuming projects; it diffs against a stored baseline ref rather than `HEAD`, and has a looser no-git fallback. Its tests run the real action in a temp git repo (`TestGeneralTaskFinalVerifySpinGateShellAction`, `test_builtin_loops.py`).
- Constraints from git semantics: `git diff HEAD` errors on a repo with no commits and outside a git repo (today's `--stat` path reports git failure as `error`); a `HEAD`-sha component makes committed progress visible but also means a revert-to-same-content after commits changes the fingerprint; untracked-file hashing must not read the run dir or other `.loops/` state or the fingerprint changes on every evaluation.
- Affected users: all `fragment: diff_stall_gate` loops (fragment sets `max_stall: 2`; `continue-task` overrides `max_stall: 3`, `on_error: run_tests`) and `oracles/generator-evaluator.yaml` `check_diff_stall`, inherited by `generator-evaluator-flux.yaml`. None of the loops sampled (`continue-task`, `harness-single-shot`, `incremental-refactor`) sets `scope`; the remaining users were not opened.
- Tests: `TestDiffStallEvaluator` in `scripts/tests/test_fsm_evaluators.py` patches `little_loops.fsm.evaluators.subprocess.run` (`mock_git`) and `chdir`s to `tmp_path`; every test assumes a single `git diff --stat` call and `test_first_call_resets_stale_count_file` hardcodes the `ll-diff-stall-<md5("_root_")[:12]>.count` path, so a multi-command fingerprint or relocated state invalidates that fixture shape. `TestDiffStallGateFragment` (`test_fsm_fragments.py`) — the issue's `TestDiffStallGate` — only checks fragment resolution (`max_stall == 2`, description present) and never exercises the evaluator, so it is not where behavior tests belong. Other references that must keep passing: `test_grader_coverage.py` (lists `evaluate_diff_stall`), `test_fsm_schema_fuzz.py`, `test_cli_loop_audit.py::test_diff_stall_detected`, `test_builtin_loops.py` (`check_stall`, ~:3957).
- Event consumers keyed on the `diff_stall` evaluate event: `cli/loop/audit.py` (`diff_stall_present` when verdict in `stall`/`no`), `cli/loop/info.py`. The `details` keys (`stall_count`, `max_stall`, `diff_changed`) are part of that surface.
- Sibling evaluator: `evaluate_action_stall` (`evaluators.py` ~:898) uses the same shared `.loops/tmp` cache directory and likely shares the cross-run defect; out of scope for this issue but worth a follow-up check.

## Implementation Steps

1. Pass run context into `evaluate_diff_stall`; store snapshot/count under the run dir.
2. Replace the `--stat` snapshot with a content fingerprint (`git diff HEAD` + `HEAD` sha + untracked contents), honoring `scope` and excluding the run dir.
3. Add tests for each Acceptance Criterion; update fragment docs.

## Impact

- **Priority**: P3 — false `partial`/stall terminals waste runs; no data loss.
- **Effort**: Small–Medium — one evaluator plus tests.
- **Risk**: Low–Medium — 12 built-in loops change stall sensitivity (stalls will trip less often).
- **Breaking Change**: No

## Steps to Reproduce

1. Run any root-scoped `diff_stall_gate` loop to a stall terminal (counter file reaches max_stall).
2. Commit or discard the working-tree changes so `git diff --stat` matches the stored snapshot (e.g. both empty).
3. Start a new run of any root-scoped diff_stall loop; its first stall check returns `no`.

## Acceptance Criteria

- Two sequential runs of the same loop do not share stall state; a fresh run's first check always returns `yes`.
- A pass that only commits, only stages, or only adds untracked files counts as progress.
- A same-line-count content edit counts as progress.
- Existing diff_stall tests updated; new tests cover each case above.

## Related

- FEAT-3594 (`continue-task`) — discovered during its review; that loop replaces its stall gate with a loop-local fingerprint independently.
- BUG-3270 — `general-task` `final_verify_spin_gate` fingerprint pattern.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-27T03:56:26 - `d2d94801-a3bb-4af7-800e-2bfc0ccec8d4.jsonl`
