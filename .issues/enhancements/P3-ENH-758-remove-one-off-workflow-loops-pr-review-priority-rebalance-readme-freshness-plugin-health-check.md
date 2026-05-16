---
id: ENH-758
type: ENH
priority: P3
status: completed
discovered_date: 2026-03-15
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
---

# ENH-758: Remove one-off workflow loops that don't belong in the loop catalog

## Summary

Four built-in loops were removed from `loops/` because they were one-off workflows disguised
as FSM loops — they had a clear terminal state, no meaningful reason to run repeatedly on a
cron, and already had corresponding skill/command equivalents. The loop catalog now contains
only loops that benefit from iterative, periodic, or continuous execution.

## Problem

The built-in loop catalog contained loops that violated the core contract of a loop: that it
makes sense to run repeatedly over time with changing state between runs. The following four
loops were actually linear pipelines with a defined end state:

- **`pr-review-cycle`** — a pre-PR quality + test + PR-creation pipeline. Runs once per PR.
  The internal "loop back to check-quality after fixing tests" is retry logic, not iteration.
- **`priority-rebalance`** — a single snapshot → analyze → rebalance → commit pass.
  Priority distribution doesn't warrant continuous monitoring.
- **`readme-freshness`** — gather stats → compare → fix → commit. A discrete sync operation,
  not ongoing maintenance.
- **`plugin-health-check`** — a one-time config audit. Plugin config changes rarely enough
  that periodic re-running adds no value; `/ll:audit-claude-config` covers the use case.

## Solution

Deleted the four loop YAML files and cleaned up all references:

- `loops/pr-review-cycle.yaml` — deleted
- `loops/priority-rebalance.yaml` — deleted
- `loops/readme-freshness.yaml` — deleted
- `loops/plugin-health-check.yaml` — deleted

## Files Changed

- `loops/pr-review-cycle.yaml` — deleted
- `loops/priority-rebalance.yaml` — deleted
- `loops/readme-freshness.yaml` — deleted
- `loops/plugin-health-check.yaml` — deleted
- `scripts/tests/test_builtin_loops.py` — removed all four from expected set; removed
  `pr-review-cycle` from `TestBuiltinLoopScratchIsolation.AFFECTED_LOOPS`
- `docs/guides/LOOPS_GUIDE.md` — removed four rows from the built-in loop reference table

## Verification

```
python -m pytest scripts/tests/test_builtin_loops.py -v
# → 14 passed
```
