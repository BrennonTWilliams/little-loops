---
status: done
completed_at: 2026-06-14T00:00:00Z
discovered_date: 2026-06-14T00:00:00Z
discovered_by: manual
---

# BUG-2155: Stale routing assertions in `test_rn_remediate.py` after `rn-remediate.yaml` update

## Summary

Two tests in `TestReadinessAndDecisionGates` asserted old `on_yes` routing targets that were superseded when `rn-remediate.yaml` added `check_complexity_pre_implement` and `check_wire_needed_outcome` as intermediate states. Both tests failed with an `AssertionError` comparing the expected direct target against the new intermediate state name.

## Location

- **File**: `scripts/tests/test_rn_remediate.py`
- **Anchor**: `TestReadinessAndDecisionGates.test_check_readiness_routes_yes_to_implement`, `TestReadinessAndDecisionGates.test_check_outcome_routes_yes_to_refine`

## Current Behavior

```
FAILED test_check_readiness_routes_yes_to_implement
  AssertionError: assert 'check_complexity_pre_implement' == 'implement'

FAILED test_check_outcome_routes_yes_to_refine
  AssertionError: assert 'check_wire_needed_outcome' == 'refine'
```

## Root Cause

`rn-remediate.yaml` was updated to insert two new intermediate states into the routing chain:

1. `check_readiness.on_yes` changed from `implement` → `check_complexity_pre_implement` (gates wiring check before implementing)
2. `check_outcome.on_yes` changed from `refine` → `check_wire_needed_outcome` (gates wiring check before refining)

The tests in `test_rn_remediate.py` were not updated alongside the loop change.

## Fix Applied

Updated both assertions and their docstrings to match the current loop routing:

- `test_check_readiness_routes_yes_to_implement`: assertion changed to `cr["on_yes"] == "check_complexity_pre_implement"`
- `test_check_outcome_routes_yes_to_refine`: assertion changed to `co["on_yes"] == "check_wire_needed_outcome"`; docstring updated to describe the wire-gating rationale

## Impact

- **Priority**: P4 — Test-only drift; no production behavior affected
- **Effort**: Trivial — two one-line assertion changes
- **Risk**: None

## Resolution

Updated `scripts/tests/test_rn_remediate.py` — both assertions and docstrings corrected. All 10 tests in `TestReadinessAndDecisionGates` pass; full suite: **11494 passed, 7 skipped**.

## Session Log
- `hook:posttooluse-status-done` - 2026-06-15T00:43:30 - `6f2f3173-38e1-42c3-82b9-ecd7b3cf6e4e.jsonl`

- Manual test run + fix - 2026-06-14
