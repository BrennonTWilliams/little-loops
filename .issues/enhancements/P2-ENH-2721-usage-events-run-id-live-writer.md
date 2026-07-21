---
id: ENH-2721
type: ENH
title: "usage_events run_id column + live per-invocation writer (split from ENH-2712)"
priority: P2
status: open
captured_at: '2026-07-21T18:20:00Z'
discovered_date: '2026-07-21'
discovered_by: confidence-check
parent: EPIC-2456
labels:
- token-cost
- observability
- history-db
- schema
relates_to:
- EPIC-2456
- ENH-2712
- ENH-2722
- ENH-2461
- FEAT-2478
- ENH-2477
decision_needed: false
spike_needed: false
spike_attempted: true
spike_completed: true
---

# ENH-2721: `usage_events` `run_id` column + live per-invocation writer (split from ENH-2712)

## Summary

Split out of ENH-2712's Option A decision: add a `run_id` column to `usage_events`, written live at the moment a loop run finishes, so a later query layer (ENH-2722) can join per-run token totals against run outcome. This issue covers the schema migration and the write mechanism only — no query/CLI work.

## Motivation

ENH-2712 bundled a schema migration + live writer (deep, architectural) together with a read-only query/CLI layer (mechanical, low-risk) in one Very-Large issue. Splitting isolates the risky half so it can be reviewed and merged on its own, and unblocks the query/CLI half (ENH-2722) as soon as `run_id` exists.

## Current Behavior

`usage_events` (`session_store.py` v20 migration, ~line 739) has no `run_id` column and is populated only by `_backfill_usage_events()` (JSONL-derived, not live). `loop_runs` (v23 migration, ~line 799) has `run_id`/`terminated_by` but no `session_id`, so there is no exact join key between the two tables today.

## Expected Behavior

- `usage_events` gains a `run_id` column (schema **v29** — `SCHEMA_VERSION` is currently 28, `_MIGRATIONS` ends at index 27).
- A live per-invocation writer stamps `run_id` on `usage_events` rows at the same call site `record_loop_run_summary()` uses in `fsm/executor.py`'s `_finish()` (~line 2582), deriving `run_id` with the same format `_finish()` already uses.
- Concurrent `ll-parallel`/`ll-sprint` runs do not cross-attribute or drop rows.

## Decision Context (inherited from ENH-2712)

**Selected: Option A** (schema `run_id` join key, live per-invocation write) over Option B (time-range join) — Option B silently misattributes tokens under the exact concurrency case `ll-parallel`/`ll-sprint` exist to support, since `loop_runs` has no `session_id` to scope a `BETWEEN` join. See ENH-2712's Decision Rationale for the full comparison table.

**Precedent reconciled**: `ARCHITECTURE-145` (ENH-2461) previously rejected FK-style columns on `usage_events` for a different join target (`tool_events.id`, backfill-derived). `ARCHITECTURE-146` (`.ll/decisions.d/e01ffb15-39ab-46f4-827c-39c2a34c947b.json`) reconciles this: `run_id` is a live write authoritative at write time, not a backfill-derived FK, so `ARCHITECTURE-145`'s rejection does not apply.

## Spike Results (inherited from ENH-2712)

A 2026-07-21 spike already proved this mechanism viable — see `scripts/tests/spike/usage_events_run_id_writer/` (5/5 tests passing as of this split):

| Risk | Proven by | Result |
|------|-----------|--------|
| No live per-invocation writer exists; unproven mid-run write mechanism | `test_single_run_stamps_correct_run_id` | pass |
| Concurrent `ll-parallel`/`ll-sprint` writers could cross-attribute or corrupt `run_id` | `test_concurrent_runs_do_not_cross_attribute` | pass |
| Concurrent writes under `busy_timeout`/WAL could silently drop rows | `test_concurrent_runs_lose_no_writes` | pass |
| `run_id` derivation must match `_finish()`'s inline format exactly | `test_run_id_derivation_matches_executor_format` | pass |
| Isolation guard (spike must not depend on production modules) | `test_spike_does_not_import_production_modules` | pass |

**Promotion plan**: move `record_usage_event()`/`derive_run_id()` from `scripts/tests/spike/usage_events_run_id_writer/` to `scripts/little_loops/spike/usage_events_run_id_writer/` (or directly into `session_store.py`/`fsm/executor.py` if the spike shape maps cleanly), then wire the real v29 migration and the `_finish()` call-site change.

## Implementation Steps

1. Add schema migration **v29**: `run_id` column on `usage_events` (`session_store.py`, following the v20→v28 migration pattern; `_MIGRATIONS` list).
2. Promote the spike's write mechanism (`record_usage_event()` / `derive_run_id()`) into production code, wired at the `_finish()` call site in `fsm/executor.py` (~line 2582), sibling to `record_loop_run_summary()`.
3. Extend `_backfill_usage_events()` (`session_store.py:2636`) to also stamp `run_id` on backfilled rows where derivable, so historical rows aren't permanently NULL.
4. Update `config-schema.json`'s `analytics.capture.usage_events` description (~line 1749) — it currently asserts usage_events has no live writer; that becomes false once this ships.

## Scope Boundaries

- **Out of scope**: the query/CLI waste view (`waste_attribution()`, `ll-ctx-stats` waste section) — that is ENH-2722, blocked on this issue.
- **Out of scope**: per-iteration `diff_stall`/`score_stall` discard tracking — an explicit follow-on noted in ENH-2712's original Proposed Solution, not required for the `run_id` join key.
- **In scope**: schema migration (v29), the live per-invocation writer, and extending `_backfill_usage_events()` to stamp `run_id` on historical rows.

## Acceptance Criteria

- [ ] `usage_events` schema is v29 with a `run_id` column.
- [ ] Live writer stamps `run_id` on new rows at loop-run finish, matching `_finish()`'s `run_id` derivation exactly.
- [ ] Concurrent `ll-parallel`/`ll-sprint` runs do not cross-attribute or lose rows (regression coverage carried over from the spike).
- [ ] `_backfill_usage_events()` populates `run_id` on backfilled rows where derivable; idempotent on re-run.
- [ ] No behavior change to existing `usage_events` consumers (`cost_attribution()`, etc.) — additive column only.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — v29 migration; write-through near `record_loop_run_summary()` (line 1709) / `_backfill_usage_events()` (line 2636)
- `scripts/little_loops/fsm/executor.py:2582` (`_finish()`) — new `run_id`-stamped `usage_events` write, sibling to `record_loop_run_summary()`
- `scripts/little_loops/config-schema.json` (~line 1749-1752) — update `analytics.capture.usage_events` description

### Similar Patterns
- Prior `session_store.py` migrations v20→v28 (schema pattern)
- `scripts/tests/spike/usage_events_run_id_writer/writer.py` — spike implementation to promote

### Tests
- `scripts/tests/test_session_store.py:4999` `TestSchemaV28` — template for new `TestSchemaV29`
- `scripts/tests/test_session_store.py:3287` `TestSchemaV20UsageEvents.test_usage_events_columns` — add `"run_id"` to the expected exact-set
- 12+ hardcoded `SCHEMA_VERSION == 28` assertions must bump to 29: `test_session_store.py` (lines 1380, 1825-1826, 1995-1996, 2047-2048, 2126, 2143-2144, 3724-3725, 3765-3766, 3820, 4513, 4659, 4880, 4985, 5025), `test_assistant_messages.py:88`, `test_enh_2511_mcp_telemetry.py:18`, `test_enh_2497_agent_type.py:17`, `test_queue_store.py:14`
- `scripts/tests/test_session_store.py:3124` `TestBackfillUsageEvents` — new test proving backfilled rows get correct `run_id`, idempotent on re-run
- `scripts/tests/test_fsm_executor.py` — verify `record_loop_run_summary()` caller in `_finish()` still passes alongside the new write-through
- `scripts/tests/spike/usage_events_run_id_writer/` — promote/retire once production code lands

### Documentation
- `docs/ARCHITECTURE.md` — schema-versions table: v29 entry
- `docs/guides/HISTORY_SESSION_GUIDE.md` (~line 108 `usage_events` row) — `run_id`/v29 update
- `docs/observability/otel-mapping.md` (~lines 55-65) — `run_id` as a new forward-compat column, same shape as `invocation_id`/`provider_vendor`

## Impact

- **Priority**: P2 — unblocks ENH-2722's query/CLI layer.
- **Effort**: Medium — schema migration + write-through + cascading test-version bumps, but the write mechanism itself is spike-proven.
- **Risk**: Low-moderate — additive column, no behavior change to existing consumers; concurrency safety already proven.

## Status

**Open** | Created: 2026-07-21 | Priority: P2
