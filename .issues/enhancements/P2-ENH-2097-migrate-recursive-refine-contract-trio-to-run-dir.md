---
id: ENH-2097
title: Migrate the recursive-refine / implement-issue-chain shared-tmp contract to ${context.run_dir}
type: ENH
priority: P2
status: open
captured_at: '2026-06-12T14:10:00Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
relates_to:
- ENH-2096
- ENH-1874
---

# ENH-2097: Migrate the recursive-refine contract trio to `${context.run_dir}`

## Summary

`recursive-refine.yaml` writes ~19 distinct `.loops/tmp/recursive-refine-*.txt` files that form a cross-loop contract: `oracles/implement-issue-chain.yaml` reads `recursive-refine-passed.txt` / `-skipped.txt` at the same bare paths when both run as sibling sub-loops of `auto-refine-and-implement` or `sprint-refine-and-implement` (which add their own `<caller_prefix>-skipped.txt` / `-impl-queue.txt` files). The 2026-06-12 audit suppressed the MR-3 warnings with `shared_state_ok: true` + comments as stage 1; this issue is stage 2: migrate the whole contract atomically to `${context.run_dir}` for real concurrency safety under ll-parallel.

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
