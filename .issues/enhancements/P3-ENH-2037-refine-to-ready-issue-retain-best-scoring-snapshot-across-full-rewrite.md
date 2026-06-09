---
id: ENH-2037
type: ENH
priority: P3
status: done
captured_at: '2026-06-08T00:00:00Z'
completed_at: '2026-06-09T05:55:50Z'
discovered_date: 2026-06-08
discovered_by: audit-loop-run
relates_to:
- BUG-2034
confidence_score: 98
outcome_confidence: 81
score_complexity: 23
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 20
decision_needed: false
implementation_order_risk: true
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

   > **Selected:** Best-snapshot retention — 4+ existing codebase precedents (`vega-viz`, `canvas-sketch-generator`, `rlhf-animated-svg`, `svg-textgrad`), reuses the `iter-N/` snapshot infrastructure already created by `snapshot_issue`, purely additive change.

2. **Regression guard on loop-back** — in `check_refine_limit`, if the latest
   pass scored lower than the previous, route to `breakdown_issue` (or restore +
   terminate) instead of another `--full-rewrite`.
3. **Incremental refine on retries** — use `--full-rewrite` only on the first
   pass; drop it on loop-backs so retries refine incrementally rather than
   regenerating from scratch. (Depends on `/ll:refine-issue` semantics — verify.)

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-09.

**Selected**: Option 1 — Best-snapshot retention

**Reasoning**: Option 1 directly satisfies all three acceptance criteria using established codebase patterns. Four existing loops (`vega-viz`, `canvas-sketch-generator`, `svg-textgrad`, `rlhf-animated-svg`) implement the identical terminal `restore_best`/`finalize` guard shape, and the `iter-N/` snapshot infrastructure already exists in `snapshot_issue` (lines 86-103) — making this a purely additive one-state change. Options 2 and 3 have structural gaps: Option 2 routes to `breakdown_issue` which decomposes rather than restores the issue, leaving AC2 unmet without a separate restore step; Option 3 switches the generation mode without any best-result retention guarantee (`commands/refine-issue.md:473` classifies default no-flag mode as rewrite-equivalent, and `--gap-analysis` on retry prevents score improvement).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 — Best-snapshot retention | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option 2 — Regression guard on loop-back | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |
| Option 3 — Incremental refine on retries | 0/3 | 1/3 | 1/3 | 0/3 | 2/12 |

**Key evidence**:
- **Option 1**: `vega-viz.yaml`, `canvas-sketch-generator.yaml`, `rlhf-animated-svg.yaml`, and `svg-textgrad.yaml` all implement `restore_best`/`finalize` terminal guards; `ll-issues show --json` used at 19 call sites for score reading; `iter-N/<id>.md` snapshots contain parseable frontmatter scores.
- **Option 2**: Score-comparison gate exists in `adversarial-redesign.yaml`, but `check_refine_limit` evaluator restructuring is required, no score-initialization state exists, and `breakdown_issue` decomposes the issue rather than restoring the best version — AC2 unmet without an additional restore step.
- **Option 3**: Default no-flag mode is rewrite-equivalent (`commands/refine-issue.md:473`); `--gap-analysis` on retry prevents score improvement; non-monotonicity is documented in `canvas-sketch-generator.yaml:14-16`; the established codebase fix pattern is best-score retention, not flag-switching.

## Acceptance Criteria

- [x] A pass that lowers scores does not cause the loop to persist the lower-
      scoring issue version.
- [x] The issue file at terminal is the best-scoring version produced during the
      run (or a documented equivalent guarantee).
- [x] Regression test with a stubbed refine step that lowers the score on pass 2,
      asserting the pass-1 (higher) version is retained.

## Scope Boundaries

- Touches `refine-to-ready-issue.yaml` (and possibly the `/ll:refine-issue`
  invocation flags). Does not change `issue-refinement`/`recursive-refine`
  orchestration.
- Does not change the meaning of the confidence/outcome thresholds.

## Files

- `scripts/little_loops/loops/refine-to-ready-issue.yaml:80-103` —
  `refine_issue`, `snapshot_issue`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:303` — `check_refine_limit`
- `scripts/tests/` — regression test

## Impact

- **Priority**: P3 — wastes expensive LLM passes and can ship a worse-refined
  issue; not a hard failure.
- **Effort**: Small–Medium depending on option chosen (Option 1 is smallest).
- **Risk**: Low–Medium — must not regress the normal improving path.
- **Breaking Change**: No.

## Labels

`loops`, `refine-to-ready-issue`, `enhancement`, `captured`, `from-audit`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-09_

**Readiness Score**: 86/100 → PROCEED
**Outcome Confidence**: 66/100 → MODERATE

### Outcome Risk Factors
- ~~**Open decision — either/or option not resolved**~~: Resolved — Option 1 (best-snapshot retention) selected by `/ll:decide-issue` on 2026-06-09. `decision_needed: false`.
- **Functional regression test is a co-deliverable**: Acceptance criterion 3 calls for a stubbed regression test; no existing test exercises best-snapshot retention. Tests are co-deliverables of this issue and must be implemented alongside the fix.

## Resolution

Added `restore_best` state to `scripts/little_loops/loops/refine-to-ready-issue.yaml` between `check_outcome` (on_yes) and `done`. The state scans all `iter-N/$ISSUE_ID.md` snapshots in the run directory, computes a composite score (`confidence_score * 1000 + outcome_confidence`) for each, and copies the highest-scoring snapshot back over the live issue file before termination. No snapshot is created by this state — it reuses the existing `snapshot_issue` infrastructure. Two regression tests added to `TestRefineToReadyIssueSubLoop` in `scripts/tests/test_builtin_loops.py` covering the restore and no-op paths.

## Session Log
- `/ll:ready-issue` - 2026-06-09T05:38:19 - `7fee7388-0a83-4166-84f7-f401a43a6ff1.jsonl`
- `/ll:decide-issue` - 2026-06-09T05:28:58 - `7369bd88-d802-4aef-b327-6aab05d3dc56.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e9de03e-3aa5-4f0b-8d49-4ede38072a90.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20c2c88c-2ba8-442b-a6c2-69f500f77b2e.jsonl`

## Status

**Open** | Created: 2026-06-08 | Priority: P3
