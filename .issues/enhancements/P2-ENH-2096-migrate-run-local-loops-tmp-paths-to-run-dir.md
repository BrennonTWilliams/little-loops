---
id: ENH-2096
title: Migrate run-local .loops/tmp/ paths to ${context.run_dir} in 7 loops with no external consumers
type: ENH
priority: P2
status: open
captured_at: '2026-06-12T14:10:00Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
relates_to:
- BUG-1960
- ENH-2097
---

# ENH-2096: Migrate run-local `.loops/tmp/` paths to `${context.run_dir}`

## Summary

Seven builtin loops write intermediate artifacts to bare `.loops/tmp/` paths that no other loop reads (verified in the 2026-06-12 audit). Concurrent runs (under `ll-parallel`, retries, or a worktree re-run) corrupt each other's state — MR-3. Unlike the recursive-refine contract trio (ENH-2097), these have no cross-loop consumers, so migration is mechanical: replace `.loops/tmp/<name>` with `${context.run_dir}/<name>` and drop any `mkdir -p .loops/tmp` (the runner creates run_dir before execution).

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

## Implementation notes

- Sub-loops dispatched by loop-router inherit the parent run_dir (`scripts/little_loops/fsm/executor.py:557-573`), so even indirect path consumption survives. Spot-check during implementation whether `dispatch` passes file *contents* (via captured vars) rather than paths.
- **Must also flip `test_evaluate_code_uses_loops_tmp`** (`scripts/tests/test_builtin_loops.py`, TestEvaluationQuality area, ~line 556) — it currently asserts `.loops/tmp/` IS present in evaluation-quality's evaluate_code action. Change it to assert `${context.run_dir}` and keep forbidding bare `/tmp/`.
- `TestBuiltinLoopScratchIsolation` only forbids bare `/tmp/`, so it stays green.

## Acceptance Criteria

- [ ] All seven loops write only under `${context.run_dir}/`
- [ ] `ll-loop validate` reports zero MR-3 warnings for these loops
- [ ] `test_evaluate_code_uses_loops_tmp` flipped to the run_dir assertion
- [ ] Corresponding `shared-tmp` entries removed from `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py`
- [ ] One smoke run per migrated loop (`ll-loop run <loop> --dry-run` at minimum; a real short run for loop-router)
