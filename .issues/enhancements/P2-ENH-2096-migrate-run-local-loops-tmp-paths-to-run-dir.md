---
id: ENH-2096
title: Migrate run-local .loops/tmp/ paths to ${context.run_dir} in 7 loops with no
  external consumers
type: ENH
priority: P2
status: done
captured_at: '2026-06-12T14:10:00Z'
completed_at: '2026-06-12T21:09:03Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
relates_to:
- BUG-1960
- ENH-2097
parent: EPIC-1811
confidence_score: 100
outcome_confidence: 88
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 25
---

# ENH-2096: Migrate run-local `.loops/tmp/` paths to `${context.run_dir}`

## Summary

Seven builtin loops write intermediate artifacts to bare `.loops/tmp/` paths that no other loop reads (verified in the 2026-06-12 audit). Concurrent runs (under `ll-parallel`, retries, or a worktree re-run) corrupt each other's state — MR-3. Unlike the recursive-refine contract trio (ENH-2097), these have no cross-loop consumers, so migration is mechanical: replace `.loops/tmp/<name>` with `${context.run_dir}/<name>` and drop any `mkdir -p .loops/tmp` (the runner creates run_dir before execution).

## Current Behavior

All seven loops write intermediate artifacts to shared bare `.loops/tmp/` paths (e.g., `.loops/tmp/ll-coverage-report`, `.loops/tmp/loop-router-input.json`). These paths are not isolated per run — any two concurrent executions of the same loop (via `ll-parallel`, a retry, or a worktree re-run) read and overwrite each other's files. `ll-loop validate` reports MR-3 warnings for all seven loops (total: 57 warnings across the set).

## Expected Behavior

All seven loops write artifacts exclusively under `${context.run_dir}/` (e.g., `${context.run_dir}/ll-coverage-report`). Each run gets an isolated directory created by the runner before execution; concurrent runs cannot corrupt each other's state. `ll-loop validate` reports zero MR-3 warnings for these loops.

## Motivation

- **Correctness**: Concurrent run corruption is a silent bug — the loop continues running with stale or partially-overwritten intermediate state, producing wrong outputs with no error.
- **ll-parallel safety**: `ll-parallel` is designed to run loops concurrently; bare `.loops/tmp/` writes make these 7 loops unsafe to parallelize today.
- **MR-3 compliance**: The harness validator already flags these as WARNING (rule MR-3); clearing them aligns the builtin loop set with the authoring standards enforced on user-created loops.
- **Mechanical migration**: No behavioral logic changes — only path constants, making this low-risk and completable loop-by-loop.

## Affected loops (MR-3 warning counts)

| Loop | Files |
|---|---|
| loop-router.yaml (33) | loop-router-input/-confidence/-chosen/-top/-branch/-catalog.json |
| test-coverage-improvement.yaml (9) | ll-coverage-report/-gaps/-tests/-skipped |
| dead-code-cleanup.yaml (6) | ll-dead-code-report/-excluded/-tests |
| scan-and-implement.yaml (4) | scan-and-implement-pre/post/new-ids |
| fix-quality-and-tests.yaml (2) | ll-test-results.txt |
| evaluation-quality.yaml (2) | eval-lint-results/-test-results |
| harness-multi-item.yaml (1) | harness-multi-item-tests.txt |

## Proposed Solution

- Sub-loops dispatched by loop-router inherit the parent run_dir (`scripts/little_loops/fsm/executor.py:557-573`), so even indirect path consumption survives. Spot-check during implementation whether `dispatch` passes file *contents* (via captured vars) rather than paths.
- **Must also flip `test_evaluate_code_uses_loops_tmp`** (`scripts/tests/test_builtin_loops.py`, TestEvaluationQuality area, ~line 556) — it currently asserts `.loops/tmp/` IS present in evaluation-quality's evaluate_code action. Change it to assert `${context.run_dir}` and keep forbidding bare `/tmp/`.
- `TestBuiltinLoopScratchIsolation` only forbids bare `/tmp/`, so it stays green.

## Scope Boundaries

- **In scope**: The 7 loops identified in the 2026-06-12 audit (loop-router, test-coverage-improvement, dead-code-cleanup, scan-and-implement, fix-quality-and-tests, evaluation-quality, harness-multi-item) and the single test assertion flip in `test_builtin_loops.py`.
- **Out of scope**: Loops with cross-loop consumers (covered by ENH-2097 — recursive-refine trio); changes to the runner's `run_dir` creation logic; loops under `loops/lib/` (non-runnable fragments); any new MR-3 warnings introduced after this audit date.

## Acceptance Criteria

- [ ] All seven loops write only under `${context.run_dir}/`
- [ ] `ll-loop validate` reports zero MR-3 warnings for these loops
- [ ] `test_evaluate_code_uses_loops_tmp` flipped to the run_dir assertion
- [ ] Corresponding `shared-tmp` entries removed from `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py`
- [ ] One smoke run per migrated loop (`ll-loop run <loop> --dry-run` at minimum; a real short run for loop-router)

## Implementation Steps

1. For each of the 7 loops in priority order: replace all `.loops/tmp/<artifact>` path strings with `${context.run_dir}/<artifact>` and remove any `mkdir -p .loops/tmp` shell commands.
2. Spot-check `loop-router.yaml` dispatch paths — confirm sub-loops receive file contents via captured vars, not raw paths that would break with the new location.
3. In `scripts/tests/test_builtin_loops.py`, flip `test_evaluate_code_uses_loops_tmp` to assert `${context.run_dir}` (and keep the `bare /tmp/` forbid); remove `shared-tmp` ALLOWLIST entries for all 7 loops from `TestValidatorWarningBudget`.
4. Run `ll-loop validate` on all 7 migrated loops; confirm zero MR-3 warnings each.
5. Smoke test each loop: `ll-loop run <loop> --dry-run`; run `loop-router` with a real short run.
6. Run full test suite (`python -m pytest scripts/tests/`) and confirm green.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/loop-router.yaml`
- `scripts/little_loops/loops/test-coverage-improvement.yaml`
- `scripts/little_loops/loops/dead-code-cleanup.yaml`
- `scripts/little_loops/loops/scan-and-implement.yaml`
- `scripts/little_loops/loops/fix-quality-and-tests.yaml`
- `scripts/little_loops/loops/evaluation-quality.yaml`
- `scripts/little_loops/loops/harness-multi-item.yaml`
- `scripts/tests/test_builtin_loops.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:557-573` — dispatch logic that injects `run_dir` into sub-loops; read-only reference, no changes needed.

### Similar Patterns
- `loops/oracles/` loops — may have similar patterns; out of scope for this issue but worth a grep after completion: `grep -r "loops/tmp" loops/oracles/`

### Tests
- `scripts/tests/test_builtin_loops.py` — `test_evaluate_code_uses_loops_tmp` (flip assertion), `TestValidatorWarningBudget.ALLOWLIST` (remove 7 `shared-tmp` entries)

### Documentation
- N/A — no user-facing docs reference `.loops/tmp/` paths for these loops

### Configuration
- N/A

## Impact

- **Priority**: P2 — Correctness issue for concurrent users (ll-parallel, retries, worktrees) but does not affect normal single-run usage.
- **Effort**: Medium — 7 loops × mechanical YAML path edit + 1 test file flip; no behavioral logic changes. Spot-check of loop-router dispatch adds minor complexity.
- **Risk**: Low — Path-only changes with no behavioral logic modifications; `run_dir` is always created by the runner before execution; changes are loop-by-loop and independently verifiable.
- **Breaking Change**: No

## Labels

`automation`, `loops`, `migration`, `correctness`, `mcp-3`

## Status

**Open** | Created: 2026-06-12 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-06-12T20:59:17 - `139296a5-54ef-432e-8ff1-1f41dae3ccca.jsonl`
- `/ll:format-issue` - 2026-06-12T20:23:52 - `051a8502-cb48-4c5c-bcc3-3f728b6c3074.jsonl`
