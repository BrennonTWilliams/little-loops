---
id: ENH-2721
type: ENH
title: usage_events run_id column + live per-invocation writer (split from ENH-2712)
priority: P2
status: done
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
confidence_score: 100
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
size: Very Large
completed_at: '2026-07-21T18:28:29Z'
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Verified line refs**: `usage_events` v20 `CREATE TABLE` is at `session_store.py:739-752`; `loop_runs` v23 `CREATE TABLE` is at `session_store.py:799-816`; `record_loop_run_summary()` is at `session_store.py:1709-1780`; `_backfill_usage_events()` is at `session_store.py:2636-2710`; `_finish()` is at `fsm/executor.py:2583-2613`, with the exact `run_id` derivation at line 2601 (`self.started_at.replace(":", "").replace(".", "").replace("+", "")[:17]`) and the `f"{run_id}-{self.fsm.name}"` concat at line 2604.
- **Closest migration precedent is v21, not v20**: `session_store.py:754-764` already added two forward-compat NULL columns to `usage_events` (`invocation_id`, `provider_vendor`) via plain `ALTER TABLE ... ADD COLUMN`, with a comment explicitly calling out that both are "reserved for a future live per-invocation writer" — the same framing this issue uses. v29 should follow this exact `ALTER TABLE` shape (plus a `CREATE INDEX IF NOT EXISTS idx_usage_events_run_id ON usage_events(run_id);`, which the spike's `_SCHEMA` constant already includes), not the `CREATE TABLE` shape used by v26-v28 (those are new tables, not applicable here).

**Decision point — where the "live per-invocation writer" actually stamps `run_id`:**

The issue's Expected Behavior and Implementation Steps say the writer is wired "at the same call site `record_loop_run_summary()` uses in `_finish()`." Codebase analysis found this call site does not have per-invocation data: `_finish()` runs exactly once, at run completion, with only final-state locals — it has no access to individual LLM-call token counts. Per-invocation usage data currently only flows through the `on_usage: UsageCallback` parameter threaded through `_run_action()` (`fsm/executor.py:1487`, docstring at 1495) and `_run_baseline_arm()` (`fsm/executor.py:2188`, docstring at 2195) — and that callback is `(input_tokens, output_tokens)`-only today; it carries no `model`, cache-token counts, or `run_id`. The spike's own module docstring (`writer.py:75-77`) anticipates this gap, describing its `record_usage_event()` as "exactly what a live `on_usage_detailed` callback wired at the same call sites as today's `on_usage`" would do — i.e. the spike itself assumes a *new*, richer callback at the `_run_action`/`_run_baseline_arm` sites, not a write from inside `_finish()`.

**Option A**: Extend `on_usage` into a richer `on_usage_detailed` callback (model, cache tokens, `run_id`) and wire it at both `_run_action()` (~1487) and `_run_baseline_arm()` (~2188), so one `usage_events` row is INSERTed per LLM call — a true per-invocation live writer, matching the spike's `record_usage_event()` shape and matching the issue's title literally. Requires touching the `on_usage` callback signature and both its call sites, not just `_finish()`.

> **Selected:** Option A — reuses an already-built `DetailedUsageCallback`/`TokenUsage` pipeline that currently dead-ends before a DB write, is spike-proven under concurrency, and is the only option consistent with this issue's own inherited Decision Context.

**Option B**: Keep `usage_events` population exactly as today (`_backfill_usage_events()` only) and add a single UPDATE at `_finish()` that stamps `run_id` onto whichever `usage_events` rows fall in the run's `[started_at, ended_at]` window for its `session_id` — literally matching "same call site as `record_loop_run_summary()`," but this reintroduces the time-range/`BETWEEN`-join imprecision that this issue's own inherited Decision Context explicitly rejected as ENH-2712's "Option B" ("Option B silently misattributes tokens under the exact concurrency case `ll-parallel`/`ll-sprint` exist to support").

**Recommended**: Option A — it's the only one consistent with this issue's own inherited Decision Context, and it's what the spike's writer.py docstring already assumes. It expands Implementation Steps/Integration Map beyond `_finish()` alone: `fsm/executor.py:1487` (`_run_action()`) and `fsm/executor.py:2188` (`_run_baseline_arm()`) both need edits to thread the richer callback, in addition to (not instead of) the `_finish()`-adjacent wiring already described for run-scoped metadata.

### Decision Rationale

**Selected: Option A** (richer `on_usage_detailed` callback wired at `_run_action()`/`_run_baseline_arm()`), scored via parallel codebase-evidence agents:

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 0 |
| Simplicity | 2 | 3 |
| Testability | 3 | 1 |
| Risk | 2 | 0 |
| **Total** | **10/12** | **4/12** |

**Key evidence:**
- `DetailedUsageCallback`/`TokenUsage` and `ActionResult.usage_events` collection already exist in production (`subprocess_utils.py:41,45-60,295-296,473-483`; `fsm/runners.py:23-25,47-48,103-104,156-173,197`) — Option A is mostly wiring existing pieces through `_run_action()`/`_run_baseline_arm()`, not new design.
- The v21 migration comment (`session_store.py:759`) explicitly earmarks `usage_events` for "a future live per-invocation writer" — Option A is the pre-declared extension point.
- `loop_runs` (v23, `session_store.py:799-816`) has no `session_id` column, so Option B's `BETWEEN [started_at, ended_at]` UPDATE cannot be scoped to a single run. `ll-parallel` (`cli/parallel.py`) runs multiple loop executions concurrently by design, so overlapping windows are the expected case, not an edge case — reproducing exactly the misattribution failure this issue's inherited Decision Context already rejected Option B for.
- No precedent for a BETWEEN/time-range join exists anywhere in `session_store.py`; Option A's write pattern (connect → parameterized INSERT → commit → close-in-finally) matches two existing writers (`record_loop_run_summary`, `_backfill_usage_events`) and is already spike-proven, including a dedicated concurrency test (`test_concurrent_runs_do_not_cross_attribute`).
- Residual scope note for implementation: `_run_action()`'s shell/mcp branches have no usage signal today (partial per-action-mode coverage), and the spike's INSERT omits `cost_usd`/`invocation_id`/`provider_vendor` — both addressable during promotion, not blockers to the decision.

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
- `scripts/little_loops/session_store.py` — v29 migration (`ALTER TABLE`, following the v21 `invocation_id`/`provider_vendor` precedent at lines 754-764, not the v26-v28 `CREATE TABLE` shape); write-through near `record_loop_run_summary()` (line 1709) / `_backfill_usage_events()` (line 2636)
- `scripts/little_loops/fsm/executor.py:2583-2613` (`_finish()`) — new `run_id`-stamped `usage_events` write, sibling to `record_loop_run_summary()`
- `scripts/little_loops/config-schema.json` (~line 1749-1752) — update `analytics.capture.usage_events` description

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- If Option A above is selected (recommended): `scripts/little_loops/fsm/executor.py:1487` (`_run_action()`) and `scripts/little_loops/fsm/executor.py:2188` (`_run_baseline_arm()`) — both call the `on_usage: UsageCallback` parameter and need to thread the richer `on_usage_detailed`-style payload (model, cache tokens, `run_id`) for a true per-invocation write.
- Additional current `usage_events` consumers not previously listed, useful for confirming "no behavior change to existing consumers" (AC #5): `scripts/little_loops/history_reader.py` (`cost_attribution()` and related queries), `scripts/little_loops/cli/ctx_stats.py`, `scripts/little_loops/fsm/cost_graph.py`, `scripts/little_loops/fsm/persistence.py` (`archive_run()` — the mirrored `run_id`/archive-path derivation this issue's `run_id` format must continue to match).

### Similar Patterns
- Prior `session_store.py` migrations v20→v28 (schema pattern); v21 (`session_store.py:754-764`) is the closest precedent specifically — a plain `ALTER TABLE ... ADD COLUMN` adding forward-compat NULL columns to `usage_events` itself
- `scripts/tests/spike/usage_events_run_id_writer/writer.py` — spike implementation to promote

### Tests
- `scripts/tests/test_session_store.py:4999` `TestSchemaV28` — template for new `TestSchemaV29`
- `scripts/tests/test_session_store.py:3287` `TestSchemaV20UsageEvents.test_usage_events_columns` — add `"run_id"` to the expected exact-set
- **Corrected count** (verified by `/ll:refine-issue` — supersedes the "12+ across 5 files" estimate below): 13 hardcoded literal `SCHEMA_VERSION == 28` assertions need bumping to 29 — 12 in `test_session_store.py` (lines 1380, 1825, 1826, 1995, 1996, 2047, 2048, 2143, 2144, 3724, 3725, 3765, 3766, 4513, 4659, 4880, 4985, 5025) + 1 in `test_assistant_messages.py:88`. `test_enh_2511_mcp_telemetry.py:81`, `test_enh_2497_agent_type.py:85`, and `test_queue_store.py:64` compare against the imported `SCHEMA_VERSION` symbol (not a literal `28`) and need **no edit** on the version bump. Original estimate (kept for traceability): lines 1380, 1825-1826, 1995-1996, 2047-2048, 2126, 2143-2144, 3724-3725, 3765-3766, 3820, 4513, 4659, 4880, 4985, 5025, plus `test_enh_2511_mcp_telemetry.py:18`, `test_enh_2497_agent_type.py:17`, `test_queue_store.py:14` — lines 2126/3820 and the three non-`test_session_store.py` line numbers did not verify against current source.
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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-21_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- Moderate per-site complexity: the selected Option A requires changing the `on_usage` callback signature (`UsageCallback`) itself, threaded through two call sites (`fsm/executor.py:1487` `_run_action()`, `fsm/executor.py:2188` `_run_baseline_arm()`), plus verifying four downstream `usage_events` consumers (`history_reader.py::cost_attribution()`, `cli/ctx_stats.py`, `fsm/cost_graph.py`, `fsm/persistence.py::archive_run()`) see no behavior change — cross-module shared-state change, not a single contained edit.
- 13 hardcoded `SCHEMA_VERSION == 28` test assertions across `test_session_store.py` and `test_assistant_messages.py` need mechanical bumping to 29; low individual risk but easy to miss one and get a false-green suite.
- Residual scope gaps acknowledged in the Decision Rationale but not yet resolved: `_run_action()`'s shell/mcp branches have no usage signal today (partial per-action-mode coverage), and the spike's INSERT omits `cost_usd`/`invocation_id`/`provider_vendor` — addressable during promotion, not blockers, but worth tracking so they don't silently regress AC #5 ("no behavior change to existing consumers").

## Status

**Decomposed** | Created: 2026-07-21 | Priority: P2

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-21
- **Reason**: Issue too large for single session (score 11/11, Very Large)

### Decomposed Into
- ENH-2723: `usage_events` `run_id` column — schema migration (v29)
- ENH-2724: `usage_events` live per-invocation `run_id` writer (`on_usage_detailed`)
- ENH-2725: `usage_events` `run_id` backfill on historical rows

## Session Log
- `/ll:issue-size-review` - 2026-07-21T18:30:00 - `1d8fe38e-085a-4ee8-8c6c-5d16d9fd18d7.jsonl`
- `/ll:confidence-check` - 2026-07-21T18:25:00 - `11300915-65eb-4c62-9307-85e985e74f0b.jsonl`
- `/ll:decide-issue` - 2026-07-21T18:22:34 - `1f613a63-3b97-4b14-8dba-2ec0bebd378a.jsonl`
- `/ll:refine-issue` - 2026-07-21T18:19:26 - `94aa4f31-9ec4-466a-ab83-7e6c12ad77c8.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-07-21
- **Decomposed into**: ENH-2723, ENH-2724, ENH-2725

Work for ENH-2721 is now carried by its child issues; this parent was closed by rn-decompose.
