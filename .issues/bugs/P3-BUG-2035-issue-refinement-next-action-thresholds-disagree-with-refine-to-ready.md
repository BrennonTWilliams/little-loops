---
id: BUG-2035
type: BUG
priority: P3
status: open
captured_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: audit-loop-run
relates_to:
  - BUG-2034
---

# BUG-2035: issue-refinement and refine-to-ready-issue use disagreeing readiness thresholds

## Summary

`issue-refinement` decides *which* issue needs work by calling `ll-issues
next-action` with **no threshold flags**, so it uses the CLI defaults
`ready_threshold=85` / `outcome_threshold=70` (`next_action.py:32-34`). The
sub-loop it then invokes, `refine-to-ready-issue`, gates "done" on **different**
thresholds: `readiness_threshold=90` / `outcome_threshold=75`
(`refine-to-ready-issue.yaml:17-19`). The two halves of the same refinement loop
therefore disagree on what "ready" means.

This mismatch is part of why borderline issues churn (see BUG-2034): an issue can
sit in a band where the sub-loop keeps trying to push it higher (needs ≥90/75)
while `next-action` would have been satisfied at ≥85/70 — or vice versa — so the
two never agree that the issue is finished.

## Current Behavior

- Selector (`issue-refinement.yaml:17`):
  `ll-issues next-action --skip "..."` → defaults 85 / 70.
- Sub-loop gates (`refine-to-ready-issue.yaml:17-19`, read by `check_readiness`
  and `check_outcome`): 90 / 75 (overridable by
  `commands.confidence_gate.{readiness,outcome}_threshold` in `ll-config.json`).
- The canonical source is `commands.confidence_gate` in `ll-config.json`, but
  `next-action` is invoked without passing those values, so it silently falls
  back to hardcoded argparse defaults that differ from the sub-loop's defaults.

## Expected Behavior

Both the selector and the sub-loop read the same readiness/outcome thresholds —
ideally both sourced from `commands.confidence_gate` in `ll-config.json` — so
"`next-action` says this issue still needs work" and "`refine-to-ready-issue`
considers this issue done" are consistent.

## Proposed Fix

Pass explicit thresholds to `next-action` in `issue-refinement.yaml`, resolved
from `commands.confidence_gate` (matching the sub-loop), e.g.:

```yaml
evaluate:
  action: >-
    ll-issues next-action
    --ready-threshold "$(ll-config get commands.confidence_gate.readiness_threshold 90)"
    --outcome-threshold "$(ll-config get commands.confidence_gate.outcome_threshold 75)"
    --skip "$(cat .loops/tmp/issue-refinement-skip-list 2>/dev/null)"
```

(Exact config-read mechanism to match how `refine-to-ready-issue` resolves it —
see its `check_readiness`/`check_outcome` Python blocks.) Verify the `next-action`
CLI exposes `--ready-threshold` / `--outcome-threshold` (it does:
`cli/issues/__init__.py:478-481`).

## Acceptance Criteria

- [ ] `issue-refinement`'s `next-action` call and `refine-to-ready-issue`'s gates
      resolve to identical readiness/outcome thresholds for the same config.
- [ ] With default config, an issue the sub-loop considers "done" is not
      immediately re-selected by `next-action`.
- [ ] Thresholds derive from `commands.confidence_gate` (single source of truth),
      not from divergent hardcoded defaults.

## Scope Boundaries

- Touches `issue-refinement.yaml`'s `evaluate` state only. Does not change
  `next-action` CLI defaults (other callers may rely on them) and does not change
  the sub-loop's thresholds.

## Files

- `scripts/little_loops/loops/issue-refinement.yaml:16-22` — `evaluate` state
- `scripts/little_loops/cli/issues/next_action.py:32-34` — default thresholds
  (reference)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:17-19` — canonical
  thresholds (reference)

## Impact

- **Priority**: P3 — coherence/correctness defect that compounds the BUG-2034
  churn; not independently fatal.
- **Effort**: Small — one state edit.
- **Risk**: Low.
- **Breaking Change**: No.

## Labels

`loops`, `issue-refinement`, `bug`, `captured`, `from-audit`

## Status

**Open** | Created: 2026-06-08 | Priority: P3
