---
id: BUG-3437
type: BUG
title: SSE fan-in backoff never engages; producers at max_clients re-probed ~10/s
  forever
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
---

# BUG-3437: SSE fan-in backoff never engages; producers at max_clients re-probed ~10/s forever

## Summary

In _fan_in_producer_sockets (transport.py ~1105) the guard `elapsed < rescan_s` is unsatisfiable because `now` is sampled at loop-top and dead readers are reaped one full `stop.wait(rescan_s)` later, so the doubling branch is dead code and interval resets every cycle. Compare elapsed against a dedicated immediate-EOF window (connected_at-relative), and rewrite test_producer_at_max_clients_backs_off_sub_linearly to assert decay shape (window N+1 < window N) instead of the brittle `< 10` absolute threshold. Fails locally and on CI (B1 in thoughts/ci-unit-test-failures-2026-09-10.md).

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]


## Session Log
- `/ll:scope-epic` - 2026-09-10T21:15:16 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
