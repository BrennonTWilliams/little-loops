---
id: ENH-2036
type: ENH
priority: P3
status: open
captured_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: audit-loop-run
relates_to:
  - BUG-817
  - BUG-2034
---

# ENH-2036: Move issue-refinement skip-list and commit-count from .loops/tmp to run_dir (MR-3)

## Summary

`issue-refinement` writes its skip-list and commit-count to **bare**
`.loops/tmp/issue-refinement-{skip-list,commit-count}`
(`issue-refinement.yaml:13,17,38-40,45-49`) instead of the runner-injected
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

## Current Behavior

- `init` (`:13`): `rm -f .loops/tmp/issue-refinement-commit-count
  .loops/tmp/issue-refinement-skip-list`
- `evaluate` (`:17`): reads `.loops/tmp/issue-refinement-skip-list`
- `handle_failure` (`:38-40`): appends the failing ID to
  `.loops/tmp/issue-refinement-skip-list`
- `check_commit` (`:45-49`): increments
  `.loops/tmp/issue-refinement-commit-count`

All four are unscoped, so every concurrent instance shares one set of files.

## Expected Behavior

These intermediate artifacts live under `${context.run_dir}/` (e.g.
`${context.run_dir}/skip-list`, `${context.run_dir}/commit-count`), which the
runner creates per run and which `context_passthrough` shares correctly between
parent and child. `ll-loop validate issue-refinement` emits no MR-3 WARNINGs (or
the loop declares `shared_state_ok: true` with justification if sharing is ever
intentional — it is not here).

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

- `scripts/little_loops/loops/issue-refinement.yaml:13,17,38-40,45-49`
- `thoughts/audits/loop-artifact-isolation-audit.md:112` — tracked remediation
  (reference)

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
