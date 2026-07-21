---
id: ENH-2725
type: ENH
title: usage_events run_id backfill on historical rows
priority: P2
status: done
captured_at: '2026-07-21T18:30:00Z'
completed_at: '2026-07-21T20:05:46Z'
discovered_date: '2026-07-21'
discovered_by: issue-size-review
parent: EPIC-2456
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
confidence_score: 97
outcome_confidence: 85
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 21
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

- [x] `_backfill_usage_events()` populates `run_id` on backfilled rows where derivable.
- [x] Backfill is idempotent on re-run — no duplicate or corrupted `run_id` stamps.
- [x] `TestBackfillUsageEvents` passes.
- [x] No behavior change to existing `usage_events` consumers for rows where `run_id` cannot be derived (stays NULL).

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py:2697-2771` (`_backfill_usage_events()`, current anchor confirmed) — `run_id` derivation and stamping
- `scripts/tests/test_session_store.py:3124-3282` (`TestBackfillUsageEvents`) — new/extended coverage; `TestSchemaV20UsageEvents.test_usage_events_columns` (`test_session_store.py:3287-3311`) already asserts `run_id` in the column set (ENH-2723)

### Similar Patterns
- `fsm/executor.py:2606-2666` (`_finish()`, current anchor confirmed — derivation at `2624` and `2648-2650`) — the `run_id` derivation format this backfill must match exactly
- `fsm/persistence.py:506-541` (`archive_run()`) — second inline copy of the identical `run_id` compact-timestamp transform; no shared helper exists between the two
- `session_store.py:799-813` (`loop_runs` table schema) — has `run_id` (UNIQUE), `loop_name`, `started_at`, `ended_at` but **no `session_id` column** — see Codebase Research Findings below for why this matters
- `session_store.py:1844-1862` (`update_loop_run_diagnostics()`) — closest existing single-column `UPDATE ... WHERE run_id = ?` precedent for an additive, already-inserted-rows column patch (different table; `usage_events`/`loop_runs` have no such precedent today)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Scope gap**: `_backfill_usage_events()` iterates only `type == "assistant"` JSONL records, reading `sessionId`, `timestamp`, `message.model`, `message.usage` — there is no `started_at`/FSM-name-equivalent field in this source at all. The `run_id` format Implementation Step 1 specifies (`self.started_at...` + `self.fsm.name`) cannot be derived directly from the same JSONL data this function parses; `self.started_at`/`self.fsm.name` are in-process `FSMExecutor` state (`fsm/executor.py:229`, `fsm/executor.py:207`) that is never written to the transcript stream.
- **Correlation table exists but lacks a join key**: `loop_runs` (populated only by `_finish()` via `record_loop_run_summary()`, never from `raw_events`/JSONL — comment at `session_store.py:795-797`) carries `run_id`, `loop_name`, `started_at`, `ended_at` but no `session_id`. The only correlation available between a `usage_events` row (`session_id`, `ts`) and a `loop_runs` row is a timestamp-window join (`usage_events.ts BETWEEN loop_runs.started_at AND loop_runs.ended_at`), which is ambiguous whenever two `loop_runs` rows overlap in time — a real case under `ll-parallel`'s concurrent worktree runs.
- **Idempotency precedent**: `_backfill_usage_events()` has no per-row dedup today (plain `INSERT`, no `UNIQUE` constraint on `usage_events`) — its only idempotency guarantee comes from `rebuild()` wiping `usage_events` via `_REBUILD_TABLES` (`session_store.py:3723-3733`) before full re-derivation (`session_store.py:3767-3785`), proven by `test_rebuild_is_idempotent_for_usage` (`test_session_store.py:3259-3281`). If this issue's extension runs as a standalone, targeted `UPDATE` on already-populated rows (distinct from a full `rebuild()`), it needs its own idempotency guard — no existing `_backfill_*` function does an additive, already-inserted-rows column patch.

> **Selected:** Option A — satisfies the issue's own Acceptance Criteria, matches the architecture already committed to at ENH-2712/ENH-2721 (query-level join, not FK-linked), and degrades safely to NULL under ambiguity.

**Option A**: Timestamp-window join — extend `_backfill_usage_events()` (or a follow-on pass) to look up `loop_runs` rows where `usage_events.ts` falls between `loop_runs.started_at` and `loop_runs.ended_at`, and stamp `run_id` only when exactly one `loop_runs` row matches (unambiguous). Rows with zero or multiple (concurrent/overlapping) matches stay `NULL` — consistent with existing AC #4.

**Option B**: Re-scope to query-time join only — leave `usage_events.run_id` NULL for historical rows entirely, and instead join `usage_events` to `loop_runs` by timestamp window at query time (in `ll-ctx-stats`/`ll-session` consumers) rather than persisting a best-guess value into a column intended as a precise join key.

**Recommended**: Option A for v1 — degrades safely to NULL under ambiguity (already covered by AC #4), keeps the persisted-column contract useful for the common case (serial runs with no window overlap), and stays consistent with the incremental-slice spirit of decomposing ENH-2721.

### Decision Rationale

**Selected: Option A** (timestamp-window join, stamp only when unambiguous).

Option A is the only option that satisfies ENH-2725's literal Acceptance Criteria — `_backfill_usage_events()` must populate `run_id` on backfilled rows where derivable. Option B leaves the column NULL for all historical rows unconditionally, which doesn't derive anything; it re-scopes the issue rather than choosing an implementation for it. Option B also re-proposes an alternative the parent issue chain (ENH-2712 → ENH-2721) already evaluated and rejected on the record (`.ll/decisions.d/e01ffb15-39ab-46f4-827c-39c2a34c947b.json`) for the identical `loop_runs`-lacks-`session_id` ambiguity — reopening that would require explicit renegotiation with ENH-2721/2723/2724, not a unilateral re-scope inside this issue. Option A's ambiguity-guard (stamp only on exactly one match, else NULL) is a new query shape for `session_store.py` (no existing `BETWEEN`/window join precedent) and needs a larger test fixture (seeded `loop_runs` rows with overlapping windows), but this is a bounded, one-time cost against a backfill pass versus Option B's cost of introducing duplicated join logic across every `usage_events` consumer (`ctx_stats.py`, `history_reader.py`) with no persisted column to show for it.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-:|:-:|:-:|:-:|:-:|
| A — timestamp-window join | 2 | 1 | 2 | 2 | **7/12** |
| B — query-time join only | 0 | 1 | 1 | 0 | 2/12 |

Key evidence:
- Option A's join mechanism has no precedent in `session_store.py` (no `BETWEEN`/range join anywhere in the file), but its per-row iteration shape matches `_backfill_usage_events()`'s existing structure, and the v29 migration comment (`session_store.py:905-913`) already frames `usage_events`↔`loop_runs` as a deliberate query-level join, not an FK.
- Option B fails AC #1/#3 outright (no `run_id` populated, no passing `TestBackfillUsageEvents` coverage for derivation) and directly contradicts the recorded ENH-2712/ENH-2721 decision rejecting the same time-range-join shape for the same ambiguity reason.
- Both options share the identical concurrency risk (`loop_runs` has no `session_id`), which Option A already absorbs via its "ambiguous → stays NULL" guard — the concern doesn't differentiate the two options, it only reinforces why Option A's guard is necessary.

## Impact

- **Priority**: P2 — closes historical-data gap once ENH-2723 lands; not required for ENH-2722's core query path but avoids permanently-NULL historical rows.
- **Effort**: Small-Medium — single-function extension plus idempotency test coverage.
- **Risk**: Low — backfill-only, additive, no behavior change to consumers for non-derivable rows.

## Status

**Open** | Created: 2026-07-21 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-07-21T20:05:22 - `df7f2449-90f0-4070-ab48-5298cbbf8cb8.jsonl`
- `/ll:confidence-check` - 2026-07-21T20:15:00 - `d6cec29c-ab7e-431d-94a7-55153c16e91b.jsonl`
- `/ll:decide-issue` - 2026-07-21T19:51:59 - `c297abc8-91c7-4b91-8a18-a365fd0de134.jsonl`
- `/ll:refine-issue` - 2026-07-21T19:48:08 - `56a159f8-9e96-4a48-b223-45a5fa8a5d80.jsonl`
- `/ll:issue-size-review` - 2026-07-21T18:30:00 - `1d8fe38e-085a-4ee8-8c6c-5d16d9fd18d7.jsonl`
