---
id: ENH-2036
type: ENH
priority: P3
status: done
captured_at: '2026-06-08T00:00:00Z'
completed_at: '2026-06-09T03:28:49Z'
discovered_date: 2026-06-08
discovered_by: audit-loop-run
relates_to:
- BUG-817
- BUG-2034
confidence_score: 100
outcome_confidence: 90
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 22
---

# ENH-2036: Move issue-refinement skip-list and commit-count from .loops/tmp to run_dir (MR-3)

## Summary

`issue-refinement` writes its skip-list and commit-count to **bare**
`.loops/tmp/issue-refinement-{skip-list,commit-count}`
(`issue-refinement.yaml:13,17,45-51,54-61`) instead of the runner-injected
`${context.run_dir}/`. This violates the meta-loop per-run isolation rule (MR-3)
documented in `.claude/CLAUDE.md` — `ll-loop validate issue-refinement` emits 5
MR-3 WARNINGs for these paths. It is already logged in the "Medium" remediation
bucket of `thoughts/audits/loop-artifact-isolation-audit.md:112`.

Because `rn-build` invokes `issue-refinement` with `context_passthrough: true`,
the skip-list lives in shared `.loops/tmp/`. Two concurrent runs (e.g. under
`ll-parallel`, a retry that re-enters the loop, or a worktree run alongside the
main checkout) read and append to the **same** skip-list and commit-count files,
corrupting each other's state — the same class of defect as BUG-817
(cross-project `/tmp` path conflicts) and BUG-1960.

## Motivation

Running `issue-refinement` under `ll-parallel`, in a worktree, or via a retry that re-enters the loop results in two instances writing to the same skip-list and commit-count files. Because the runner injects a unique `run_dir` per execution, moving these artifacts there costs nothing and closes the concurrency hazard permanently.

- **Correctness**: Two concurrent `rn-build` → `issue-refinement` chains silently corrupt each other's skip-lists — a failing issue in run A can appear in run B's skip-list and be silently bypassed.
- **MR-3 compliance**: `ll-loop validate issue-refinement` currently emits 5 MR-3 WARNINGs; this fix reduces them to zero.
- **Low risk, high leverage**: Four path-substitution edits and one cleanup removal, with no behavior change on single-serial runs.

## Current Behavior

- `init` (`:13`): `rm -f .loops/tmp/issue-refinement-commit-count
  .loops/tmp/issue-refinement-skip-list`
- `evaluate` (`:17`): reads `.loops/tmp/issue-refinement-skip-list`
- `handle_failure` (`:45-51`): appends the failing ID to
  `.loops/tmp/issue-refinement-skip-list`
- `check_commit` (`:54-61`): increments
  `.loops/tmp/issue-refinement-commit-count`

All four are unscoped, so every concurrent instance shares one set of files.

## Expected Behavior

These intermediate artifacts live under `${context.run_dir}/` (e.g.
`${context.run_dir}/skip-list`, `${context.run_dir}/commit-count`), which the
runner creates per run and which `context_passthrough` shares correctly between
parent and child. `ll-loop validate issue-refinement` emits no MR-3 WARNINGs (or
the loop declares `shared_state_ok: true` with justification if sharing is ever
intentional — it is not here).

## Proposed Solution

Replace all four bare `.loops/tmp/issue-refinement-*` path references in `issue-refinement.yaml` with `${context.run_dir}/` equivalents:

| State | Old path | New path |
|---|---|---|
| `init` | `rm -f .loops/tmp/issue-refinement-commit-count .loops/tmp/issue-refinement-skip-list` | remove line (runner pre-creates `run_dir`) |
| `evaluate` | `.loops/tmp/issue-refinement-skip-list` | `${context.run_dir}/skip-list` |
| `handle_failure` | `.loops/tmp/issue-refinement-skip-list` | `${context.run_dir}/skip-list` |
| `check_commit` | `.loops/tmp/issue-refinement-commit-count` | `${context.run_dir}/commit-count` |

`context_passthrough: true` in `rn-build` already propagates `run_dir` to child invocations, so any parent-child skip-list sharing that previously relied on a shared `.loops/tmp/` path continues to work correctly via `run_dir`.

## Acceptance Criteria

- [ ] skip-list and commit-count paths use `${context.run_dir}/`.
- [ ] `ll-loop validate issue-refinement` no longer emits MR-3 WARNINGs for these
      paths.
- [ ] Two concurrent `issue-refinement` runs (or two rn-build runs) do not share
      or corrupt each other's skip-list / commit-count.
- [ ] Existing single-run behavior (skip on failure, commit every 5) is
      preserved.

## Scope Boundaries

- Touches `issue-refinement.yaml` only. Consider folding in the same fix for
  `refine-to-ready-issue`'s and `recursive-refine`'s bare `.loops/tmp/` writes
  (also in the isolation-audit Medium bucket) **only if** they share the same PR;
  otherwise capture separately to keep diffs reviewable.
- The `mkdir -p .loops/tmp` calls can be dropped once paths move under `run_dir`
  (the runner already creates `run_dir`).

## Files

- `scripts/little_loops/loops/issue-refinement.yaml:13,17,45-51,54-61`
- `thoughts/audits/loop-artifact-isolation-audit.md:112` — tracked remediation
  (reference)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/issue-refinement.yaml` — 4 path changes at states `init` (:13), `evaluate` (:17), `handle_failure` (:45-51), `check_commit` (:54-61)

### Dependent Files (Callers/Importers)
- `rn-build` invokes `issue-refinement` via `context_passthrough: true` — benefits automatically; no changes needed

### Similar Patterns
- `refine-to-ready-issue` and `recursive-refine` have similar bare `.loops/tmp/` writes (same isolation-audit Medium bucket) — Scope Boundaries allows folding into same PR

### Tests
- N/A — validate with `ll-loop validate issue-refinement` (zero MR-3 WARNINGs is the acceptance gate)

### Documentation
- `thoughts/audits/loop-artifact-isolation-audit.md:112` — update tracking entry to resolved after fix

### Configuration
- N/A

## Implementation Steps

1. Edit `issue-refinement.yaml`: substitute `${context.run_dir}/skip-list` for `.loops/tmp/issue-refinement-skip-list` and `${context.run_dir}/commit-count` for `.loops/tmp/issue-refinement-commit-count` in all four locations
2. Remove the `rm -f .loops/tmp/issue-refinement-{commit-count,skip-list}` cleanup from the `init` state
3. Run `ll-loop validate issue-refinement` and confirm zero MR-3 WARNINGs
4. Run a single-instance smoke-test (`ll-loop run issue-refinement`) to verify skip-on-failure and commit-every-5 behavior is preserved

## Impact

- **Priority**: P3 — latent concurrency/corruption hazard; no impact on a single
  serial run, but real under `ll-parallel` / worktree / retry re-entry.
- **Effort**: Small — mechanical path substitution + validate.
- **Risk**: Low.
- **Breaking Change**: No.

## Labels

`loops`, `issue-refinement`, `loop-validation`, `artifact-isolation`,
`enhancement`, `captured`, `from-audit`

## Status

**Open** | Created: 2026-06-08 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-09T03:25:18 - `8625c164-18d7-47bc-9b80-218363426e41.jsonl`
- `/ll:format-issue` - 2026-06-09T02:41:43 - `2e851901-2808-4980-9585-6d4994df06a4.jsonl`
- `/ll:confidence-check` - 2026-06-08T00:00:00Z - `8625c164-18d7-47bc-9b80-218363426e41.jsonl`
