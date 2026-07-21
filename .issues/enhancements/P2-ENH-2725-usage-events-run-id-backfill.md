---
id: ENH-2725
type: ENH
title: usage_events run_id backfill on historical rows
priority: P2
status: open
captured_at: '2026-07-21T18:30:00Z'
discovered_date: '2026-07-21'
discovered_by: issue-size-review
parent: ENH-2721
labels:
- token-cost
- observability
- history-db
relates_to:
- EPIC-2456
- ENH-2721
- ENH-2723
blocked_by:
- ENH-2723
decision_needed: false
spike_needed: false
---

# ENH-2725: `usage_events` `run_id` backfill on historical rows

## Summary

Extend `_backfill_usage_events()` (`session_store.py:2636-2710`) to also stamp `run_id` on backfilled rows where derivable from existing JSONL-derived data, so historical rows aren't permanently NULL once the `run_id` column exists. This is the backfill slice of ENH-2721, decomposed to build on the schema column from ENH-2723 and to proceed independently of the live writer (ENH-2724) — both consume the same column but neither depends on the other's code path.

## Parent Issue

Decomposed from ENH-2721: `usage_events` `run_id` column + live per-invocation writer (split from ENH-2712)

## Blocked By

ENH-2723 (the `run_id` column must exist before backfill can populate it).

## Motivation

`_backfill_usage_events()` populates `usage_events` from JSONL-derived data today with no `run_id`. Once ENH-2723 lands the column, historical rows would otherwise stay permanently NULL — this issue closes that gap for rows where `run_id` is derivable, without requiring the live writer (ENH-2724) to land first.

## Implementation Steps

1. Extend `_backfill_usage_events()` (`session_store.py:2636-2710`) to derive and stamp `run_id` on backfilled rows where the source JSONL data supports derivation, using the same `run_id` format `_finish()` uses (`self.started_at.replace(":", "").replace(".", "").replace("+", "")[:17]`, concatenated as `f"{run_id}-{self.fsm.name}"`).
2. Ensure the backfill is idempotent on re-run (matches existing `_backfill_usage_events()` idempotency guarantees for other columns).
3. Add `TestBackfillUsageEvents` coverage (`test_session_store.py:3124`) proving backfilled rows get the correct `run_id` and that re-running the backfill is a no-op on already-stamped rows.

## Scope Boundaries

- **Out of scope**: the v29 schema migration itself — that is ENH-2723 (prerequisite).
- **Out of scope**: the live per-invocation writer — that is ENH-2724 (independent of this issue; both consume the ENH-2723 column but neither blocks the other).
- **In scope**: `_backfill_usage_events()` extension and its idempotency/derivation test coverage.

## Acceptance Criteria

- [ ] `_backfill_usage_events()` populates `run_id` on backfilled rows where derivable.
- [ ] Backfill is idempotent on re-run — no duplicate or corrupted `run_id` stamps.
- [ ] `TestBackfillUsageEvents` passes.
- [ ] No behavior change to existing `usage_events` consumers for rows where `run_id` cannot be derived (stays NULL).

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py:2636-2710` (`_backfill_usage_events()`) — `run_id` derivation and stamping
- `scripts/tests/test_session_store.py:3124` (`TestBackfillUsageEvents`) — new/extended coverage

### Similar Patterns
- `fsm/executor.py:2583-2613` (`_finish()`) — the `run_id` derivation format this backfill must match exactly

## Impact

- **Priority**: P2 — closes historical-data gap once ENH-2723 lands; not required for ENH-2722's core query path but avoids permanently-NULL historical rows.
- **Effort**: Small-Medium — single-function extension plus idempotency test coverage.
- **Risk**: Low — backfill-only, additive, no behavior change to consumers for non-derivable rows.

## Status

**Open** | Created: 2026-07-21 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-07-21T18:30:00 - `1d8fe38e-085a-4ee8-8c6c-5d16d9fd18d7.jsonl`
