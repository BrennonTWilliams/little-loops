---
id: ENH-2471
title: "Tier 0 verification trace set (locked 3–5 traces) + P1 edit-batch hook regression test"
type: ENH
priority: P2
status: open
captured_at: "2026-07-03T00:00:00Z"
discovered_date: 2026-07-03
discovered_by: scope-epic
parent: EPIC-2456
relates_to: [FEAT-2470]
labels:
  - token-cost
  - testing
  - measurement
  - tier-0
---

# ENH-2471: Tier 0 verification trace set + P1 hook regression test

## Summary

Lock a 3–5 trace set for before/after measurement of FEAT-2470's Tier 0
techniques, and land the P1 edit-batch hook regression test. This is EPIC-2456
§ Children [TBD-2] and partially resolves the epic's Open Question #6 (locked
trace sets need owners and members — this issue owns the Tier 0 set).

## Scope

- Select 3–5 representative loop-run traces (e.g. `general-task` runs from `.loops/runs/` or `ll-logs eval-export`) and lock them as fixtures so every Tier 0 "win" is measured against a stable baseline.
- Record the baseline cost per trace via the host CLI `usage` block (Tier 1 telemetry is not yet online).
- Regression test for the P1 edit-batch `PostToolUse` hook (`scripts/tests/test_edit_batch_hook.py`) — fires on Edit/Write/MultiEdit, is a nudge not a block, and does not fire in non-automation contexts.

## Current Behavior

No locked trace set exists for Tier 0; any before/after claim is measured against a moving target. The P1 edit-batch hook (FEAT-2470) has no regression test.

## Expected Behavior

A locked 3–5 trace set with recorded baseline cost figures; FEAT-2470's delta is reported against it; the hook regression test runs in the standard suite.

## Acceptance Criteria

- Trace-set membership documented (fixture paths checked in or reproducibly derivable) with baseline token/cost figures.
- Before/after delta reported for FEAT-2470 on the locked set.
- Hook regression test passes under `python -m pytest scripts/tests/`.

## Scope Boundaries

- **In**: Tier 0 trace-set selection + baseline capture; the P1 edit-batch hook regression test.
- **Out**: Tier 1 telemetry (F5/F6 children own that); trace sets for F4/F8/streaming-parity (epic Open Question #6 assigns those to their own children).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent epic; § Success Metrics (Tier 0), Open Question #6 |
| `.issues/features/P2-FEAT-2470-tier-0-token-cost-behavioral-quick-wins.md` | The work this measures |

## Impact

- **Priority**: P2 — gates the credibility of every Tier 0 "win"; owns the epic's Tier 0 trace set (Open Question #6)
- **Effort**: Small — fixture selection + baseline capture + one regression test
- **Risk**: Low — test/measurement only
- **Breaking Change**: No

## Status

**Open** | Created: 2026-07-03 | Priority: P2

## Session Log

- `/ll:scope-epic` - 2026-07-03T00:00:00Z - filed from EPIC-2456 § Children [TBD-2] (Tier 0 verification)
