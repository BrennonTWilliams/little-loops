---
id: BUG-3726
type: BUG
title: reconcile-issue --from-verify-evidence adds ACs for context-only inventory
  evidence
priority: P3
status: open
program_design_not_applicable: true
discovered_by: ll-issues-create
discovered_date: '2026-10-04'
captured_at: '2026-10-04T01:57:03Z'
parent: EPIC-3694
relates_to:
- ENH-3718
- BUG-3695
---

# BUG-3726: reconcile-issue --from-verify-evidence adds ACs for context-only inventory evidence

## Summary

Found by ENH-3718's live evaluation: when `/ll:reconcile-issue --from-verify-evidence` is handed `DIRECTIVE_DRIFT` evidence whose items point at context-only Tests/Documentation inventory entries, a real model (claude-sonnet-5-5) turns each entry into an Acceptance Criterion. `commands/reconcile-issue.md` ("Source extension — `--from-verify-evidence`") says context-only inventory items create no requirement and each added item must be entailed by the selected mechanism.

## Current Behavior

Two independent direct calls (D3, D4) on an issue whose Proposed Solution is a docstring-only change, with `verify_verdict: DIRECTIVE_DRIFT` and `verify_evidence` reading `Acceptance Criteria: 'no AC covers the Integration Map Tests and Documentation entries (tests/test_core.py::test_count_words, tests/test_cli.py::test_count_prints_total, README.md)' -> add an AC for each listed Tests and Documentation entry`, each added three ACs of the form "`tests/test_core.py::test_count_words` passes with no edits to the test file" and "`README.md` is unchanged". Both are requirements derived from an inventory listing, and both D3 and D4 did it. The same command correctly added a Step (no AC) for fixture-invalidation evidence (D1, D2) and changed nothing for a `VALID` verdict with stale evidence (N1, N2).

## Expected Behavior

An evidence item whose target is a context-only entry (an unchanged caller, test or documentation inventory with no behavior or contract consequence) is not actioned. Reconcile leaves the body unchanged and records the item under `## CONCERNS`, as it already does for items that demand a new behavior or option.

## Proposed Solution

Tighten the `--from-verify-evidence` text in `commands/reconcile-issue.md` so each evidence item is classified by the same role table B6 uses (observable behavior or contract, required fixture update, context-only) before any addition, and a context-only target is refused with a `## CONCERNS` line. Do not touch `check_reconcile_limit` (`target: 2`). Re-run D3 and D4, plus D1, D2, N1 and N2 as regression controls, with the same shim.

## Acceptance Criteria

- [ ] `commands/reconcile-issue.md` states that a context-only evidence target is refused and recorded under `## CONCERNS`.
- [ ] Two live direct calls on `postmortems/ENH-3718-live-eval-20261003/fixtures/D3.ENH-8803.md` leave the issue body unchanged.
- [ ] Regression controls D1, D2, N1 and N2 keep their ENH-3718 outcomes (Step added with no AC; body unchanged).

## Impact

- **Priority**: P3 - exposure needs a B6 false positive first, and the added ACs are no-op "unchanged" assertions
- **Effort**: Small
- **Risk**: Low

## Steps to Reproduce

The evidence is synthetic: a real B6 pass returned `VALID` on this fixture, so the end-to-end loop does not reach reconcile on it. This is a reconcile-side robustness gap against a B6 false positive, not an observed loop failure. Fixtures, the shim and per-trial before/after snapshots are in `postmortems/ENH-3718-live-eval-20261003/` (`postmortems/ENH-3718-live-eval-20261003/fixtures/D3.ENH-8803.md`, and the `logs/D3`, `logs/D4` directories beside it).

1. Build a throwaway project with `D3.ENH-8803.md` committed under `.issues/enhancements/`.
2. Run `/ll:reconcile-issue ENH-8803 --from-verify-evidence` with the snapshot of commit `d960240d4`.
3. Diff the issue file: three new ACs, none entailed by the docstring-only mechanism.

## Labels

`reconcile-issue`, `directive-drift`, `epic-3694`

## Status

**Open** | Created: 2026-10-04 | Priority: P3
