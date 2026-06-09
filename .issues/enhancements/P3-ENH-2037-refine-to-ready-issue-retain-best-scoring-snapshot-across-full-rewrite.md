---
id: ENH-2037
type: ENH
priority: P3
status: open
captured_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: audit-loop-run
relates_to:
  - BUG-2034
---

# ENH-2037: refine-to-ready-issue should retain the best-scoring snapshot across --full-rewrite passes

## Summary

`refine-to-ready-issue`'s `refine_issue` state always runs
`/ll:refine-issue <id> --auto --full-rewrite` (`refine-to-ready-issue.yaml:80-84`)
on every pass — including loop-backs from `check_refine_limit`. `--full-rewrite`
is destructive and **non-monotonic**: it can produce a *worse* result than the
prior version. In run `.loops/runs/rn-build-20260608T181251/`, FEAT-032's
`outcome_confidence` regressed 71→68 across rewrite passes, and the loop kept the
regressed version (see `audit-rn-build-feat032-2026-06-08.md`).

`snapshot_issue` (`refine-to-ready-issue.yaml:86-103`) already copies each
iteration's issue file into `${context.run_dir}/iter-N/`, but nothing ever
*restores* the best-scoring snapshot — so a late regression silently wins.

## Current Behavior

1. `refine_issue` → `/ll:refine-issue --full-rewrite` (unconditional).
2. `snapshot_issue` copies the result to `iter-N/`.
3. `confidence_check` re-scores; if still below threshold and budget remains,
   `check_refine_limit` loops back to `refine_issue` → another full rewrite.
4. Whatever the final pass produced is what persists — even if an earlier pass
   scored higher.

Note: there is **no** "escalation to `--full-rewrite`" to guard (an earlier audit
draft assumed one); the rewrite is unconditional from the first pass. The real
defect is the absence of best-result retention / regression handling.

## Expected Behavior

The loop preserves the highest-scoring version produced across all passes. On
reaching a terminal, if the current issue file scores lower than a prior
iteration snapshot, restore the best snapshot. Equivalently, add a regression
guard that stops re-rewriting once scores drop and keeps the best-so-far.

## Proposed Options (pick during refinement)

1. **Best-snapshot retention** — before `done`/`breakdown_issue`, compare the
   current `outcome_confidence`/`confidence_score` against each `iter-N/`
   snapshot and `cp` the best one back over the issue file. Lowest behavioral
   risk; reuses existing snapshots.
2. **Regression guard on loop-back** — in `check_refine_limit`, if the latest
   pass scored lower than the previous, route to `breakdown_issue` (or restore +
   terminate) instead of another `--full-rewrite`.
3. **Incremental refine on retries** — use `--full-rewrite` only on the first
   pass; drop it on loop-backs so retries refine incrementally rather than
   regenerating from scratch. (Depends on `/ll:refine-issue` semantics — verify.)

## Acceptance Criteria

- [ ] A pass that lowers scores does not cause the loop to persist the lower-
      scoring issue version.
- [ ] The issue file at terminal is the best-scoring version produced during the
      run (or a documented equivalent guarantee).
- [ ] Regression test with a stubbed refine step that lowers the score on pass 2,
      asserting the pass-1 (higher) version is retained.

## Scope Boundaries

- Touches `refine-to-ready-issue.yaml` (and possibly the `/ll:refine-issue`
  invocation flags). Does not change `issue-refinement`/`recursive-refine`
  orchestration.
- Does not change the meaning of the confidence/outcome thresholds.

## Files

- `scripts/little_loops/loops/refine-to-ready-issue.yaml:80-103` —
  `refine_issue`, `snapshot_issue`, `check_refine_limit`
- `scripts/tests/` — regression test

## Impact

- **Priority**: P3 — wastes expensive LLM passes and can ship a worse-refined
  issue; not a hard failure.
- **Effort**: Small–Medium depending on option chosen (Option 1 is smallest).
- **Risk**: Low–Medium — must not regress the normal improving path.
- **Breaking Change**: No.

## Labels

`loops`, `refine-to-ready-issue`, `enhancement`, `captured`, `from-audit`

## Status

**Open** | Created: 2026-06-08 | Priority: P3
