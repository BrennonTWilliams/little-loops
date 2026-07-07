---
id: BUG-2530
title: "Global event-bus leak in test_complete_issue_lifecycle_emits_event flakes under specific xdist shardings"
type: BUG
priority: P3
status: open
captured_at: '2026-07-07T00:00:00Z'
discovered_date: 2026-07-07
discovered_by: audit
size: Medium
labels:
- tests
- flaky
- event-bus
---

# BUG-2530: Global event-bus leak in test_complete_issue_lifecycle_emits_event flakes under specific xdist shardings

## Summary

`scripts/tests/test_issue_lifecycle.py:1361::test_complete_issue_lifecycle_emits_event`
passes in isolation (0.13s) and under `-n 4` with one node (0.97s), but
historically flakes under specific full-suite shardings — a test-isolation
bug from global event-bus state leaking between tests.

Source: audit run `.loops/runs/general-task-20260707T133447/audit-report.md`
(C7 / Finding #4 / R4; isolation evidence in that run's
`evidence/eventbus-shard.txt`). Explicitly NOT a cause of the test-suite
beachball — independent test-quality issue.

## Current Behavior

Flakes only under specific shardings of the full 14,183-item suite; cannot
be reproduced with isolated or small `-n 4` runs.

## Expected Behavior

Test passes deterministically regardless of sharding/ordering.

## Proposed Solution

Investigate `LLTestBus.global_subscribers` cleanup between tests — likely a
missing teardown/reset fixture, or another test registering global
subscribers that persist into this test's assertions. May require
`pytest -p no:randomly`-style bisection or `--dist loadgroup` experiments to
find the interfering test.

## Acceptance Criteria

- Root cause identified with the specific leaking subscriber/test named.
- Test passes across repeated full-suite `-n auto` runs.
- Cleanup enforced structurally (autouse fixture or bus reset), not by
  reordering tests.
