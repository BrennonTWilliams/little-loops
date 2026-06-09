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

## Steps to Reproduce

1. Configure a project with default `ll-config.json` (no `commands.confidence_gate` overrides).
2. Start the `issue-refinement` loop against a backlog containing an issue whose readiness score is in the 85–89 range.
3. Observe: `ll-issues next-action` selects the issue (meets the hardcoded 85 selector threshold).
4. Observe: `refine-to-ready-issue` sub-loop requires readiness ≥ 90 to exit, iterating without converging.
5. To trigger the config-override path: set `commands.confidence_gate.readiness_threshold: 90` in `ll-config.json`; `refine-to-ready-issue` picks up 90, but `next-action` still uses default 85 — selector and sub-loop now disagree even when config is explicitly set.

## Root Cause

- **File**: `scripts/little_loops/loops/issue-refinement.yaml`
- **Anchor**: `evaluate` state shell action (`ll-issues next-action`)
- **Cause**: `next-action` is called without `--ready-threshold` / `--outcome-threshold` flags, so it falls back to hardcoded argparse defaults in `get_next_action_data()` (`ready_threshold=85`, `outcome_threshold=70`). The sub-loop `refine-to-ready-issue` independently reads thresholds from `commands.confidence_gate` in `ll-config.json` via `check_readiness` and `check_outcome` states (defaults `readiness_threshold=90`, `outcome_threshold=75`). There is no shared resolution path — two sources, two different defaults.

## Motivation

Borderline issues (readiness 85–89) land in the disagreement band: `next-action` considers them needing work (below its 90-equivalent) yet will re-select them after the sub-loop exits (they still score ≥85). This produces churn identical to BUG-2034 — the selector and sub-loop never agree the issue is done, wasting loop iterations. Making `commands.confidence_gate` the single source of truth for both halves eliminates the churn band and makes loop termination coherent.

## Proposed Solution

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

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/issue-refinement.yaml` — `evaluate` state: add `--ready-threshold` / `--outcome-threshold` flags to the `ll-issues next-action` call

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/next_action.py` — `get_next_action_data()`: reference only; CLI defaults remain unchanged (other callers depend on them)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `check_readiness` / `check_outcome` states: reference only; canonical threshold source to match

### Similar Patterns
- N/A — no other loop calls `ll-issues next-action` with threshold flags

### Tests
- `scripts/tests/test_builtin_loops.py` — add test asserting `evaluate` state passes explicit threshold flags to `next-action`

### Documentation
- N/A

### Configuration
- `.ll/ll-config.json` — `commands.confidence_gate.readiness_threshold` / `commands.confidence_gate.outcome_threshold` (single source of truth after fix)

## Implementation Steps

1. In `issue-refinement.yaml`, update the `evaluate` state's `action:` to read `commands.confidence_gate.{readiness,outcome}_threshold` from `ll-config.json` using the same Python snippet pattern as `check_readiness`/`check_outcome` in `refine-to-ready-issue.yaml`.
2. Pass the resolved values as `--ready-threshold` and `--outcome-threshold` to `ll-issues next-action`.
3. Confirm the config-read path matches exactly how `refine-to-ready-issue` resolves these values.
4. Run `ll-loop validate issue-refinement` to confirm no new FSM violations are introduced.
5. Add a unit test in `test_builtin_loops.py` asserting the `evaluate` state passes explicit threshold flags.

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


## Session Log
- `/ll:format-issue` - 2026-06-09T02:41:48 - `2e851901-2808-4980-9585-6d4994df06a4.jsonl`
