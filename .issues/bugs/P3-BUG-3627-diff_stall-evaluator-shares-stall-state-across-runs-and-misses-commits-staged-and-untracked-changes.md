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
