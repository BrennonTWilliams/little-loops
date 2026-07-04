---
id: FEAT-2097
title: Migrate the recursive-refine / implement-issue-chain shared-tmp contract to
  ${context.run_dir}
type: FEAT
priority: P2
status: done
captured_at: '2026-06-12T14:10:00Z'
completed_at: '2026-06-12T21:25:04Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
relates_to:
- ENH-2096
- ENH-1874
confidence_score: 100
outcome_confidence: 88
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 23
---

# FEAT-2097: Migrate the recursive-refine contract trio to `${context.run_dir}`

## Summary

`recursive-refine.yaml` writes ~19 distinct `.loops/tmp/recursive-refine-*.txt` files that form a cross-loop contract: `oracles/implement-issue-chain.yaml` reads `recursive-refine-passed.txt` / `-skipped.txt` at the same bare paths when both run as sibling sub-loops of `auto-refine-and-implement` or `sprint-refine-and-implement` (which add their own `<caller_prefix>-skipped.txt` / `-impl-queue.txt` files). The 2026-06-12 audit suppressed the MR-3 warnings with `shared_state_ok: true` + comments as stage 1; this issue is stage 2: migrate the whole contract atomically to `${context.run_dir}` for real concurrency safety under ll-parallel.

## Motivation

This enhancement would:
- **Concurrency safety**: Eliminate shared-state corruption when `ll-parallel` runs multiple `recursive-refine` instances simultaneously — bare `.loops/tmp/` paths are overwritten by whichever run lands last
- **Technical debt**: Remove the `shared_state_ok: true` suppressions added as stage-1 workarounds, replacing them with the structural fix the MR-3 rule was designed to enforce
- **Consistency**: Aligns the recursive-refine / implement-issue-chain contract with the run_dir isolation pattern already used by other loops in the harness

## Feasibility (verified)

Child sub-loops always inherit the parent's run_dir: the `with:` branch re-injects it via `child_fsm.context.setdefault("run_dir", ...)` and the `context_passthrough` branch spreads the parent context (`scripts/little_loops/fsm/executor.py:557-573`). Sibling sub-loops of the same parent therefore see the same run_dir, so the contract survives migration.

## Scope (one atomic commit)

- `scripts/little_loops/loops/recursive-refine.yaml` (831 lines; paths appear inside both shell actions and inline-Python actions, e.g. `attempts_file = '.loops/tmp/recursive-refine-attempts.txt'` — interpolation applies to both)
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` (reader, `get_passed_issues` + `implement_next`)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml` (caller_prefix queue/skip files)
- Remove the four `shared_state_ok: true` declarations added as stage-1 suppressions (incl. the pre-existing one in implement-issue-chain)
- Update `test_get_passed_issues_reads_recursive_refine_outputs` and any other tests asserting the bare paths in `scripts/tests/test_builtin_loops.py`

## Known acceptable behavior change

Running `oracles/implement-issue-chain` standalone after a *standalone* recursive-refine run will no longer find the files (different run_dirs). Acceptable: the oracle is documented as a sub-loop component (loops/README.md).

## Acceptance Criteria

- [ ] No `.loops/tmp/` references remain in the four files
- [ ] `shared_state_ok` flags removed; `ll-loop validate` reports zero MR-3 warnings for all four
- [ ] Full integration check: `ll-loop simulate auto-refine-and-implement` (or a bounded real run) shows the passed/skipped handoff working end-to-end
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes

## Implementation Steps

1. Audit all `.loops/tmp/recursive-refine-*.txt` path literals in `recursive-refine.yaml` (~19 occurrences in shell and inline-Python actions) and replace with `${context.run_dir}/recursive-refine-*.txt`
2. Update `oracles/implement-issue-chain.yaml` — migrate `get_passed_issues` and `implement_next` reader paths to use `${context.run_dir}/`
3. Update `auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml` — migrate caller_prefix queue/skip file paths to `${context.run_dir}/`
4. Remove all four `shared_state_ok: true` declarations (including the pre-existing one in `implement-issue-chain`)
5. Update `test_get_passed_issues_reads_recursive_refine_outputs` and any other test assertions on bare `.loops/tmp/` paths in `scripts/tests/test_builtin_loops.py`
6. Run `ll-loop validate` on all four loops and confirm zero MR-3 warnings
7. Run `python -m pytest scripts/tests/test_builtin_loops.py` to confirm full test suite passes

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` (831 lines; ~19 path literals to migrate in both shell and inline-Python actions)
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` (reader states: `get_passed_issues`, `implement_next`)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (caller_prefix queue/skip file paths)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` (caller_prefix queue/skip file paths)
- `scripts/tests/test_builtin_loops.py` (assertions on bare `.loops/tmp/` paths)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:557-573` — run_dir injection via `context_passthrough` and `with:` branch (read-only; confirms run_dir inheritance for sibling sub-loops)

### Similar Patterns
- `grep -r 'run_dir' scripts/little_loops/loops/` — find loops already using `${context.run_dir}/` as reference implementations

### Tests
- `scripts/tests/test_builtin_loops.py` — `test_get_passed_issues_reads_recursive_refine_outputs` and related bare-path assertions

### Documentation
- `scripts/little_loops/loops/README.md` — already documents `implement-issue-chain` as a sub-loop component (covers the known acceptable behavior change)

### Configuration
- N/A


## Resolution

All four loop files migrated atomically to `${context.run_dir}`:
- `recursive-refine.yaml`: 128 `.loops/tmp/recursive-refine-*` path literals replaced; two Python f-string blocks updated with explicit `run_dir` variable; `shared_state_ok: true` and stale comment removed
- `oracles/implement-issue-chain.yaml`: `recursive-refine-{passed,skipped}.txt` reader paths and caller_prefix queue/skip paths migrated; `shared_state_ok: true` removed
- `auto-refine-and-implement.yaml`: skipped/impl-queue paths migrated; `shared_state_ok: true` and comment removed
- `sprint-refine-and-implement.yaml`: skipped file path migrated; `shared_state_ok: true` and comment removed
- `test_builtin_loops.py`: 5 tests updated (3 `.loops/tmp/` → `${context.run_dir}` assertions, 1 `shared_state_ok` inversion, 1 queue path assertion)

All 820 tests pass. `ll-loop validate` reports zero MR-3 warnings for all four loops.

## Session Log
- `/ll:ready-issue` - 2026-06-12T21:14:27 - `c075077a-db89-41ce-be86-35b3dc26256a.jsonl`
- `/ll:format-issue` - 2026-06-12T18:27:09 - `b707c5d1-5008-4de5-bbcc-8364948be699.jsonl`
- `/ll:manage-issue` - 2026-06-12T21:25:04 - implementation complete
