---
id: BUG-3568
type: BUG
title: Autodev residual decision group reaches implement_current with decision_needed
  armed
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:12Z'
parent: EPIC-3565
---

# BUG-3568: Autodev residual decision group reaches implement_current with decision_needed armed

## Summary

`oracles/resolve-decision.yaml` state `check_residual_decision` (BUG-3278) routes to `done`
when a residual decision group survives `/ll:decide-issue --auto`. That is deliberate: it is a
bounded human-review exit, and the flag stays armed. Its comment says the caller's own
`decision_needed` gate holds the issue. But autodev's success path (`mark_decide_ran` →
`rerun_confidence_after_decide` → `recheck_after_decide`) only checks readiness/outcome
scores. So an issue with `decision_needed: true` and passing scores went to
`implement_current`, where ll-auto halts at the decision gate. The result was a wasted
implementation attempt, ledgered as unverified/phantom rather than decision-unresolved.

## Current Behavior

Before the fix, a residual decision group plus passing scores led to `implement_current` →
ll-auto decision halt → `autodev-unverified.txt`.

## Expected Behavior

A still-armed flag after the oracle returns `done` is ledgered via
`record_decision_unresolved` and deferred for human review.

## Motivation

Held-for-review issues wasted an ll-auto implementation attempt, and were misreported as unverified instead of decision-unresolved.

## Proposed Solution

Re-check `decision_needed` in `mark_decide_ran` before rescoring. Implemented; see Resolution.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `mark_decide_ran`

### Dependent Files (Callers/Importers)
- N/A — loop-internal routing

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_autodev_decision_gate.py` — `test_mark_decide_ran_holds_residual_decision`
- `scripts/tests/test_builtin_loops.py` — `test_mark_decide_ran_next_routes_to_rerun_confidence_after_decide`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Make `mark_decide_ran` a `shell_exit` check-flag state
2. Armed → `record_decision_unresolved`; cleared → `rerun_confidence_after_decide`
3. Update routing tests

## Impact

- **Priority**: P2
- **Effort**: Small
- **Risk**: Low

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `mark_decide_ran`, `recheck_after_decide`
- **Cause**: the oracle's `done` terminal means "flag cleared" or "residual held for human
  review". The caller treated both as cleared.

## Resolution

`mark_decide_ran` now writes the marker, then runs
`ll-issues check-flag <ID> decision_needed` (`fragment: shell_exit`): `on_yes` →
`record_decision_unresolved`, `on_no`/`on_error` → `rerun_confidence_after_decide`. This also
saves one confidence-check call for held issues. The entry-time sibling
`mark_decide_ran_at_dequeue` has the same check (see BUG-3569). Tests:
`test_mark_decide_ran_holds_residual_decision` and the updated
`test_mark_decide_ran_next_routes_to_rerun_confidence_after_decide`. Landed in commit
`9a5d0f523`; the `test_builtin_loops.py` update was uncommitted at capture time.

Follow-up (open, tracked in BUG-3571): the resolve-decision oracle's
description still says `done` means the flag was cleared.

## Acceptance Criteria

- [x] A still-armed `decision_needed` after resolve-decision success routes to `record_decision_unresolved`
- [x] A cleared flag keeps the existing rescoring path

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2
