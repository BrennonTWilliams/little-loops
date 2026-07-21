---
id: ENH-2724
type: ENH
title: usage_events live per-invocation run_id writer (on_usage_detailed)
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
- ENH-2712
- ENH-2722
blocked_by:
- ENH-2723
decision_needed: false
spike_needed: false
spike_attempted: true
spike_completed: true
---

# ENH-2724: `usage_events` live per-invocation `run_id` writer (`on_usage_detailed`)

## Summary

Promote the ENH-2712 spike's write mechanism into production: extend the `on_usage: UsageCallback` parameter into a richer `on_usage_detailed` callback (model, cache tokens, `run_id`) wired at both `_run_action()` (`fsm/executor.py:1487`) and `_run_baseline_arm()` (`fsm/executor.py:2188`), so one `usage_events` row is INSERTed per LLM call with `run_id` stamped at write time. This is the live-writer slice of ENH-2721, decomposed to build on the schema column from ENH-2723.

## Parent Issue

Decomposed from ENH-2721: `usage_events` `run_id` column + live per-invocation writer (split from ENH-2712)

## Blocked By

ENH-2723 (the `run_id` column must exist before this writer can stamp it).

## Decision Context (inherited from ENH-2721 / ENH-2712)

**Selected: Option A** — richer `on_usage_detailed` callback wired at `_run_action()`/`_run_baseline_arm()`, over Option B (a single UPDATE at `_finish()` scoped by `[started_at, ended_at]`). Option B was rejected because `loop_runs` has no `session_id` to scope a `BETWEEN` join, and `ll-parallel`/`ll-sprint` run overlapping windows by design — reproducing the exact misattribution failure this issue's lineage already rejected. See ENH-2721's Decision Rationale for the full scored comparison (Option A: 10/12, Option B: 4/12).

`DetailedUsageCallback`/`TokenUsage` and `ActionResult.usage_events` collection already exist in production (`subprocess_utils.py:41,45-60,295-296,473-483`; `fsm/runners.py:23-25,47-48,103-104,156-173,197`) — this is mostly wiring existing pieces through `_run_action()`/`_run_baseline_arm()`, not new design.

## Spike Results (inherited from ENH-2712/ENH-2721)

A 2026-07-21 spike already proved this mechanism viable — see `scripts/tests/spike/usage_events_run_id_writer/` (5/5 tests passing):

| Risk | Proven by | Result |
|------|-----------|--------|
| No live per-invocation writer exists; unproven mid-run write mechanism | `test_single_run_stamps_correct_run_id` | pass |
| Concurrent `ll-parallel`/`ll-sprint` writers could cross-attribute or corrupt `run_id` | `test_concurrent_runs_do_not_cross_attribute` | pass |
| Concurrent writes under `busy_timeout`/WAL could silently drop rows | `test_concurrent_runs_lose_no_writes` | pass |
| `run_id` derivation must match `_finish()`'s inline format exactly | `test_run_id_derivation_matches_executor_format` | pass |
| Isolation guard (spike must not depend on production modules) | `test_spike_does_not_import_production_modules` | pass |

**Promotion plan**: move `record_usage_event()`/`derive_run_id()` from `scripts/tests/spike/usage_events_run_id_writer/` to production (`session_store.py`/`fsm/executor.py`, or a promoted module if the spike shape maps cleanly).

## Implementation Steps

1. Promote `record_usage_event()`/`derive_run_id()` from `scripts/tests/spike/usage_events_run_id_writer/` into production code.
2. Extend `UsageCallback` into `on_usage_detailed` (model, cache tokens, `run_id`) and wire it at `_run_action()` (`fsm/executor.py:1487`) and `_run_baseline_arm()` (`fsm/executor.py:2188`).
3. Wire the write-through near `_finish()` (`fsm/executor.py:2583-2613`), sibling to `record_loop_run_summary()`, deriving `run_id` with the same format `_finish()` already uses (`self.started_at.replace(":", "").replace(".", "").replace("+", "")[:17]`, concatenated as `f"{run_id}-{self.fsm.name}"`).
4. Update `config-schema.json`'s `analytics.capture.usage_events` description (~line 1749) — it currently asserts `usage_events` has no live writer; that becomes false once this ships.
5. Verify no behavior change to existing `usage_events` consumers: `history_reader.py::cost_attribution()`, `cli/ctx_stats.py`, `fsm/cost_graph.py`, `fsm/persistence.py::archive_run()` (the mirrored `run_id`/archive-path derivation this must continue to match).

## Scope Boundaries

- **Out of scope**: the v29 schema migration itself — that is ENH-2723 (prerequisite).
- **Out of scope**: backfilling `run_id` on historical rows — that is ENH-2725.
- **Out of scope**: the query/CLI waste view (`waste_attribution()`, `ll-ctx-stats` waste section) — that is ENH-2722, blocked on this issue's parent.
- **Known residual gap** (acknowledged, not a blocker): `_run_action()`'s shell/mcp branches have no usage signal today (partial per-action-mode coverage); the spike's INSERT omits `cost_usd`/`invocation_id`/`provider_vendor`. Addressable during promotion, not required for this issue's acceptance criteria.
- **In scope**: the `on_usage_detailed` callback, both call-site wirings, the `_finish()`-adjacent write, and the config-schema doc update.

## Acceptance Criteria

- [ ] Live writer stamps `run_id` on new `usage_events` rows at loop-run finish, matching `_finish()`'s `run_id` derivation exactly.
- [ ] Concurrent `ll-parallel`/`ll-sprint` runs do not cross-attribute or lose rows (regression coverage carried over from the spike: cross-attribution + no-lost-writes tests).
- [ ] `config-schema.json`'s `analytics.capture.usage_events` description reflects the live writer.
- [ ] No behavior change to existing `usage_events` consumers (`cost_attribution()`, `ctx_stats.py`, `cost_graph.py`, `archive_run()`).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py:1487` (`_run_action()`) — thread `on_usage_detailed`
- `scripts/little_loops/fsm/executor.py:2188` (`_run_baseline_arm()`) — thread `on_usage_detailed`
- `scripts/little_loops/fsm/executor.py:2583-2613` (`_finish()`) — new `run_id`-stamped write, sibling to `record_loop_run_summary()`
- `scripts/little_loops/config-schema.json` (~line 1749-1752) — update `analytics.capture.usage_events` description
- `scripts/tests/test_fsm_executor.py` — verify `record_loop_run_summary()` caller in `_finish()` still passes alongside the new write-through; concurrency regression tests promoted from the spike

### Similar Patterns
- `scripts/tests/spike/usage_events_run_id_writer/writer.py` — spike implementation to promote
- `record_loop_run_summary()` (`session_store.py:1709-1780`) — existing sibling writer pattern (connect → parameterized INSERT → commit → close-in-finally)

### Documentation
- `docs/ARCHITECTURE.md` — schema-versions table: v29 entry (writer behavior note)
- `docs/guides/HISTORY_SESSION_GUIDE.md` (~line 108 `usage_events` row) — `run_id` writer update
- `docs/observability/otel-mapping.md` (~lines 55-65) — `run_id` as a new forward-compat column, same shape as `invocation_id`/`provider_vendor`

## Impact

- **Priority**: P2 — the core deliverable of ENH-2721; unblocks ENH-2722.
- **Effort**: Medium — cross-module callback signature change threaded through two call sites, plus consumer-safety verification.
- **Risk**: Low-moderate — additive write path, no behavior change to existing consumers; concurrency safety already spike-proven.

## Status

**Open** | Created: 2026-07-21 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-07-21T18:30:00 - `1d8fe38e-085a-4ee8-8c6c-5d16d9fd18d7.jsonl`
