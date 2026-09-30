---
id: ENH-3679
type: ENH
title: Spool best-effort telemetry writes under a held history.db write lock
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:01Z'
blocks:
- ENH-3666
relates_to:
- ENH-3680
---

# ENH-3679: Spool best-effort telemetry writes under a held history.db write lock

## Summary

Make best-effort telemetry writers (`cli_events` and similar) resilient to a held write lock: use a short busy timeout (~250-500 ms) and, on lock failure, append the row to a bounded local JSONL spool drained on the next successful connect. Split out of ENH-3666 after its 2026-09-29 Opus review.

## Current Behavior

Every `ll-*` writer waits `_BUSY_TIMEOUT_MS` (5000 ms) then logs `cli_event_context: enter failed ... database is locked` and drops its row; the command also takes ~12 s wall time. Observed with a detached `--rebuild` holding the lock, but the same happens under any long lock holder (usage-trigger worker, `refresh_raw_events`, `recompress_raw_events`).

## Expected Behavior

Telemetry writes never stall a command beyond the short timeout and are not lost: on `OperationalError: database is locked` the row goes to a spool (`.ll/` scoped, size- and age-bounded, one small JSON line per row so appends stay atomic) and is drained/idempotently inserted on the next successful connect. Non-telemetry writers keep the 5000 ms timeout.

## Scope Boundaries

- **In scope**: a short busy timeout for best-effort telemetry writers, a bounded local JSONL spool, and an idempotent drain on the next successful connect.
- **Out of scope**: `rebuild()` internals (ENH-3666), the rebuild trigger (ENH-3678), the `context-monitor.sh` hook spool (ENH-3680), remote-backend telemetry (its own unreachable-marker path).

## Impact

- **Priority**: P3 - telemetry rows dropped and ~12s command stalls under any long lock holder
- **Effort**: Small/Medium - short timeout, a bounded spool file, and an idempotent drain
- **Risk**: Medium - new durability surface (spool) on the telemetry path
- **Breaking Change**: No

## Acceptance Criteria

- [ ] With a real second connection holding `BEGIN IMMEDIATE`, a `cli_event_context` write returns within the short timeout and its row appears after the lock is released and the spool drains.
- [ ] Spool is bounded (size/age), drained idempotently (no duplicate rows), and never grows unbounded when the DB is permanently unavailable.
- [ ] Remote (libsql) backend behavior unchanged (its own unreachable-marker path).
- [ ] Existing telemetry-writer tests pass; docs describe the spool.

## Related

- ENH-3666, ENH-3678; ENH-3680 (hook spool, same drain idea: consider one shared spool mechanism).

## Status

**Open** | Created: 2026-09-30 | Priority: P3
