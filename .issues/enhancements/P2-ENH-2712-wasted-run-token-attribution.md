---
id: ENH-2712
type: ENH
title: "Wasted-run token attribution \u2014 ll-ctx-stats waste view over history.db"
priority: P2
status: cancelled
captured_at: '2026-07-21T02:03:13Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
parent: EPIC-2456
labels:
- token-cost
- observability
- history-db
relates_to:
- EPIC-2456
- FEAT-2478
- ENH-2477
- ENH-2461
- ENH-2721
- ENH-2722
decision_needed: false
size: Very Large
confidence_score: 100
outcome_confidence: 61
score_complexity: 7
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 10
spike_needed: true
spike_attempted: true
spike_completed: true
---

# ENH-2712: Wasted-run token attribution — ll-ctx-stats waste view over history.db

**Split 2026-07-21** into two child issues along the risk boundary the `/ll:confidence-check` outcome-confidence assessment surfaced (deep schema/writer work vs. mechanical query/CLI work):
- **ENH-2721** — `usage_events` `run_id` column + live per-invocation writer (schema migration, promotes the spike at `scripts/tests/spike/usage_events_run_id_writer/`)
- **ENH-2722** — `ll-ctx-stats` waste view over `history.db` (read-only query + CLI layer), `blocked_by: ENH-2721`

All research, the Option A/B decision rationale, wiring findings, and spike results below remain valid and were carried forward into the two children verbatim; this issue is kept for history and cancelled rather than deleted.

## Summary

All of EPIC-2456 optimizes $/token on successful work; nothing measures tokens spent on runs that produced **no accepted artifact** — oscillating loops, GATE_FAILED retries, toothless-evaluator iterations (`ll-loop diagnose-evaluators` finds these but nobody totals their cost). Add a `waste` view to `ll-ctx-stats` that joins per-run token totals (F5/F6 telemetry, already shipped) against terminal run outcome, so failure-mode fixes can be ranked against per-token optimizations.

## Motivation

If a meaningful share of spend goes to runs that fail or stall, fixing those loops dominates every remaining tier of the epic — but today that share is unknown. The telemetry to answer it (FEAT-2478 OTel emission, ENH-2477 per-state attribution) already exists; this is a query + presentation layer, near-zero risk. It could reorder the epic's remaining priorities.

## Current Behavior

`ll-ctx-stats` reports context savings and per-tool stats; no view correlates token spend with run outcome. Wasted spend is invisible.

## Expected Behavior

`ll-ctx-stats waste` (or `ll-history waste`) prints per-loop and aggregate: total tokens, tokens on runs ending in failure/stall/no-artifact, waste percentage, and the top-N most wasteful loops/states — read-only over `.ll/history.db` (respecting the `LL_HISTORY_DB` → config → default resolution, ENH-2623).

## Proposed Solution

- Define "wasted": run terminal status ∈ {failed, killed, max_steps-exhausted-without-success} plus iterations that a `diff_stall`/`score_stall` evaluator later discarded. Start with terminal-status only; refine with per-iteration discard tracking as a follow-on.
- SQL over existing run/usage rows in `history.db` (no schema change if run outcome is already recorded; if not, that gap is the first sub-task — check `loops` mirror tables and `raw_events`).
- Read-only; no automated deletion or compaction side effects (per project policy on raw_events).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**The audit in Implementation Step 1 surfaces a real gap, not a formality**: `usage_events` (`scripts/little_loops/session_store.py` v20 migration, ~line 739) and `loop_runs` (v23 migration, ENH-2463, ~line 799) share **no join key**. `usage_events` identity is `session_id` + `ts` (no `run_id` column); `loop_runs` has `run_id`/`terminated_by` but **no `session_id` column** (confirmed: no `session_id` references in `fsm/executor.py`). `run_id` in `loop_runs` is derived in `FSMExecutor._finish()` (`fsm/executor.py:2600`) from a timestamp + loop name, matching the on-disk `.loops/.history/<run_id>-<loop_name>/` archive — not any `usage_events` row. This is a decision point, not a detail:

**Option A**: Add a `run_id` column to `usage_events`, written by the live per-invocation path (the `invocation_id`/`provider_vendor` columns added in the v21/FEAT-2478 migration are already reserved for a future live writer, currently NULL on parser-backfilled rows). Requires a schema migration (v24) following the existing `session_store.py` migration pattern, plus a write-site change wherever `usage_events` rows are inserted during a loop run. Gives an exact join; correctly attributes tokens even when `ll-parallel`/`ll-sprint` run multiple loops concurrently.

> **Selected:** Option A — exact join key is the only option that stays correct under `ll-parallel`/`ll-sprint` concurrency, which the issue itself calls out as the tool's core supported use case.

**Option B**: Approximate via a time-range join — `usage_events.ts BETWEEN loop_runs.started_at AND loop_runs.ended_at` — with no schema change. Simpler, but silently misattributes tokens whenever two loop runs overlap in time (the exact concurrency case `ll-parallel`/`ll-sprint` exist to support), and `usage_events.session_id` isn't constrained to the session(s) that executed the loop's states, so a busy dev session running unrelated commands during a loop's window would inflate its "waste" figure.

**Recommended**: Option A for v1 — the miscounting risk in Option B directly undermines the issue's own goal (ranking loops by wasted spend); a wrong ranking is worse than no ranking. `session_store.py` already has an established migration cadence (v20→v23 in recent history) and `record_loop_run_summary()`'s call site in `fsm/executor.py:2582` (`_finish()`) is the natural sibling location for a new `record_usage_event(..., run_id=...)` write-through once the live per-invocation writer exists — check whether that writer already exists before scoping this as new work; if only the backfill-from-JSONL path (`_backfill_usage_events()`, `session_store.py:2636`) currently populates `usage_events`, extending it to also stamp `run_id` (matched by session/time overlap onto the nearest `loop_runs` row, then treated as ground truth going forward) is a smaller first cut than a live writer.

### Decision Rationale

**Selected: Option A** (schema `run_id` join key on `usage_events`, written by a new live per-invocation writer).

**Reasoning**: Option B's zero-migration simplicity is real, but its failure mode is silent and directly contradicts the issue's stated purpose. `ll-parallel`/`ll-sprint` run loops concurrently by design (`cli/parallel.py:254`, `--workers`), and `loop_runs` has no `session_id` column to scope a time-range join — so any `usage_events` row whose timestamp falls inside a run's `[started_at, ended_at]` window gets counted, regardless of which session produced it. Under the exact concurrency scenario these tools exist to support, Option B's waste-percentage output would be quietly wrong with no error surfaced — worse than not having the feature, since a wrong ranking could misdirect the rest of EPIC-2456's prioritization. Option A costs more upfront (a new migration plus a live per-invocation writer, since `_backfill_usage_events()` is currently the only write site and is JSONL-derived, not live), but `record_loop_run_summary()`'s call site in `_finish()` (`fsm/executor.py:2582`) is a natural, already-established sibling location for the new write-through, and the `invocation_id`/`provider_vendor` columns added in v21 were explicitly reserved for this future writer — so the schema was already anticipating this option.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:---:|:---:|:---:|:---:|:---:|
| A — schema `run_id` join | 2 | 1 | 2 | 2 | 7/12 |
| B — time-range join | 2 | 3 | 3 | 0 | 8/12 |

Option B edges out A on raw rubric total, but its Risk score of 0 reflects a dispositive correctness defect (silent misattribution under the tool's primary supported concurrency use case), not merely elevated implementation risk — this overrides the numeric tiebreak, consistent with the issue's own pre-existing analysis.

**Key evidence**: `cli/parallel.py:1,254` (`--workers` concurrency); `session_store.py:739-750` (`usage_events` schema, no `run_id`), `:799-813` (`loop_runs` schema, no `session_id`), `:754-760` (v21 `invocation_id`/`provider_vendor` reserved-for-future-writer comment); `history_reader.py:854-919` (`cost_attribution`), `:1544-1591` (`aggregate_loop_runs`) — both exact-key joins, no existing `BETWEEN`-style precedent; `fsm/executor.py:2582` (`_finish()`, sibling write-through site).

## Implementation Steps

1. Audit what run-outcome + token data `history.db` already holds; document the join.
2. Query module in `history_reader.py` (`waste_attribution()`), tested against fixture DB.
3. CLI surface in `ctx_stats.py` (or `ll-history`) with `--json` output.
4. Docs: API.md entry + a short "interpreting waste" note.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 (audit)**: Resolved above — no join key exists today; see the Option A/B decision.
- **Step 2 (`waste_attribution()`)**: Model after `cost_attribution()` (`history_reader.py:854`, whitelist-dict `_COST_ATTR_GROUP_COLUMNS` at line 843 guards `GROUP BY` against injection, sums `input_tokens`/`output_tokens`/cache columns/`cost_usd` from `usage_events`) and `aggregate_loop_runs()` (`history_reader.py:1550`, whitelist `_LOOP_RUN_GROUP_COLUMNS` at line 1544, groups `loop_runs` by `loop_name`/`terminated_by`). Follow the module's universal contract: `_connect_readonly()` (line 363, never raises, returns `None` on failure), `try/except sqlite3.Error: logger.warning(...); return []`, numeric aggregates guarded with `row["x"] or 0`. Add the new function to the module docstring's "Public API" list (lines 8-60).
- **Step 3 (CLI)**: `ctx_stats.py` has **no subcommand structure today** — `_build_parser()` (line 40) is a flat parser with only `--db`/`--json`; there's no `add_subparsers()` call. A literal `ll-ctx-stats waste` subcommand is a structural addition, not an established pattern in this file. Simpler alternative consistent with the file's existing shape: add a `waste` section to the existing combined report (model `_aggregate_mcp_health()`, `ctx_stats.py:169`, which thinly delegates to a `history_reader` function) and gate it behind a flag if a separate view is wanted. **Also note**: `ctx_stats.py` does **not** call `resolve_history_db()` — it builds `db_path` from a locally-defined `DEFAULT_DB_RELPATH` (line 36), bypassing the `LL_HISTORY_DB` env/config chain (ENH-2623) entirely. The new waste aggregator should explicitly call `resolve_history_db()` (`session_store.py:179`) rather than inherit this existing gap, per the issue's own requirement to respect ENH-2623 resolution.
- **`ll-loop diagnose-evaluators` is not reusable here**: it's filesystem/JSONL-based (`scripts/little_loops/analytics/variance.py:162`, reads `.loops/.history/*/events.jsonl`), has zero token/cost awareness, and reads a different corpus than `.ll/history.db`. The `diff_stall`/`score_stall` evaluators it indirectly relates to (`fsm/evaluators.py:572,667`) run live during execution and emit routing verdicts, not waste labels — no code exists today that classifies per-iteration token waste; this remains genuinely new work, matching the issue's own "follow-on" framing for per-iteration discard tracking.
- **Step 2 test pattern**: `TestCostAttribution` (`scripts/tests/test_history_reader.py:92-181`) — seeds `usage_events` via `conn.executemany(...)`, asserts `cost_attribution(db=missing) == []`, and asserts `ValueError` on an unwhitelisted `group_by` (SQL-injection regression test). `test_aggregate_loop_runs` (same file, ~line 1786) shows the alternate producer-side seeding idiom via `session_store.record_loop_run_summary(...)`. Both `TestMissingDatabase`/`TestEmptyTables` (lines 29-89) establish the always-`[]`-never-raise contract a new test class should also cover.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. **Correct the migration version**: this issue's Option A/B analysis assumes a "v24" migration; `SCHEMA_VERSION` is actually 28, so the new migration is **v29**. Before writing the migration, reconcile with `.ll/decisions.yaml` `ARCHITECTURE-145` (ENH-2461), which previously rejected FK-style column additions onto `usage_events` for a different join target — confirm this issue's `run_id` column is still the right call given that precedent, or cite why it differs.
6. Add `TestSchemaV29` in `scripts/tests/test_session_store.py` (model: `TestSchemaV28`, line 4999) and update `TestSchemaV20UsageEvents.test_usage_events_columns` (line 3287) to include `"run_id"` in its exact-set assertion.
7. Bump all 12+ hardcoded `SCHEMA_VERSION == 28` assertions to 29 across `test_session_store.py`, `test_assistant_messages.py:88`, `test_enh_2511_mcp_telemetry.py:18`, `test_enh_2497_agent_type.py:17`, `test_queue_store.py:14`.
8. Add a `run_id`-population test to `TestBackfillUsageEvents` (`test_session_store.py:3124`) and a `TestWasteAttribution` class to `test_history_reader.py` (model: `TestCostAttribution`, line 92).
9. Add the missing `ctx_stats.py` regression test proving `LL_HISTORY_DB`/`history.db_path` config overrides are honored (no such test exists today) — this is the actual proof the ENH-2623 bypass fix works.
10. Update `docs/guides/HISTORY_SESSION_GUIDE.md` and `docs/observability/otel-mapping.md` schema/query references, `docs/reference/CLI.md`'s `ll-ctx-stats` entry, and `config-schema.json`'s `analytics.capture.usage_events` description if the write-through ships.

## Acceptance Criteria

- [ ] `waste_attribution()` returns per-loop totals: tokens_total, tokens_wasted, waste_pct, run counts.
- [ ] CLI view lists top wasteful loops with `--json` support.
- [ ] Read-only: no writes/deletes against history.db.
- [ ] Documented definition of "wasted" with its known limitations.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/history_reader.py` — add `waste_attribution()`, modeled on `cost_attribution()` (line 854) and `aggregate_loop_runs()` (line 1550)
- `scripts/little_loops/cli/ctx_stats.py` — add a waste-aggregation helper (`_aggregate_waste()` following `_aggregate_mcp_health()`, line 169) and a report section; also fix the existing ENH-2623 gap where this file bypasses `resolve_history_db()` (uses local `DEFAULT_DB_RELPATH`, line 36)
- `scripts/little_loops/session_store.py` — only if Option A (schema `run_id` join key) is chosen: new migration (v24) plus a write-through change near `record_loop_run_summary()` (line 1709) / `_backfill_usage_events()` (line 2636)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:2582` (`_finish()`) — writes `loop_runs` rows via `record_loop_run_summary()`; the natural sibling site for a `run_id`-stamped `usage_events` write if Option A is chosen
- `scripts/little_loops/cli/loop/info.py:1161,1217` (`cmd_diagnose_evaluators()`, `cmd_calibrate_budget()`) — related but separate waste-adjacent tooling (evaluator health, not token cost); no code change needed but worth cross-referencing in docs

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/history.py:245,262,299,316` — reference implementation for the `ctx_stats.py` `resolve_history_db()` fix: `from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context, resolve_history_db` then `resolve_history_db(project_root / DEFAULT_DB_PATH)` [Agent 2 finding]
- **Schema-version correction**: `SCHEMA_VERSION` is currently **28** (`session_store.py:217`), not 24 as this issue's Option A text assumes — a new migration for the `run_id` column would be **v29**, not v24. `_MIGRATIONS` list ends at index 27 (~line 905). [Agent 2 + Agent 3 finding]
- **Prior decision precedent to reconcile**: `.ll/decisions.yaml` `ARCHITECTURE-145` (from ENH-2461) previously rejected FK-style column additions onto `usage_events` (joining to `tool_events.id`), establishing `usage_events` as an "independent table (join on `session_id`, `ts`) + per-call grain." A `run_id` FK-style column under this issue's Option A is the same shape of change that decision rejected for a different target — worth reconciling/citing before implementing, via `ll-issues decisions list` [Agent 2 finding]
- `scripts/little_loops/config-schema.json` (~line 1749-1752) — `analytics.capture.usage_events` description text asserts *"usage_events is currently derived by the raw_events rebuild parser, not a live per-event writer"*; a run_id write-through near `record_loop_run_summary()`/`_backfill_usage_events()` would contradict this claim and the description needs updating [Agent 2 finding]

### Similar Patterns
- `history_reader.py:854` `cost_attribution()` — token-sum rollup with whitelisted `GROUP BY`
- `history_reader.py:1550` `aggregate_loop_runs()` — outcome rollup by `loop_name`/`terminated_by`
- `history_reader.py:739,789` `mcp_server_usage()` / `mcp_failure_rate()` — `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` success/failure rollup shape, the closest existing analog to a waste-percentage calculation

### Tests
- `scripts/tests/test_history_reader.py` — `TestCostAttribution` (lines 92-181) and `test_aggregate_loop_runs` (~line 1786) are the fixture-seeding templates; `TestMissingDatabase`/`TestEmptyTables` (lines 29-89) for the never-raise contract
- `scripts/tests/test_cli_ctx_stats.py` — `test_json_mode` / `test_json_mode_skill_health_present` (lines 282-366) for CLI-level `--json` assertions

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store.py:4999` `TestSchemaV28` — exact migration-test template to copy for the new `run_id` migration (`TestSchemaV29`): column-set assertion + `test_v27_db_upgrades_gains_subagent_runs`-style upgrade-from-prior-version check. `_bootstrap_schema_at()` (line 3957) is the shared helper for the upgrade test [Agent 3 finding]
- `scripts/tests/test_session_store.py:3287` `TestSchemaV20UsageEvents.test_usage_events_columns` — **will break**: exact-set (`cols == {...}`) assertion over `usage_events` columns; must add `"run_id"` to the expected set if Option A ships [Agent 2 + Agent 3 finding]
- **12+ hardcoded `SCHEMA_VERSION == 28` assertions will break** and must be bumped to 29 across: `scripts/tests/test_session_store.py` (lines 1380, 1825-1826, 1995-1996, 2047-2048, 2126, 2143-2144, 3724-3725, 3765-3766, 3820, 4513, 4659, 4880, 4985, 5025), `scripts/tests/test_assistant_messages.py:88`, `scripts/tests/test_enh_2511_mcp_telemetry.py:18`, `scripts/tests/test_enh_2497_agent_type.py:17`, `scripts/tests/test_queue_store.py:14` [Agent 2 finding]
- `scripts/tests/test_session_store.py:3124` `TestBackfillUsageEvents` (`test_rebuild_is_idempotent_for_usage` at 3259-3281) — new test needed proving backfilled rows get the correct `run_id` and stay idempotent on re-run [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — verify `record_loop_run_summary()` caller in `_finish()` still passes if a `run_id`-stamped `usage_events` write-through is added alongside it [Agent 1 finding]
- **New test gap (no existing coverage)**: `test_cli_ctx_stats.py` has no test that sets `LL_HISTORY_DB` env or `history.db_path` config with no `--db` flag — this is the actual regression proof for the `resolve_history_db()` fix; it would fail today and pass once `ctx_stats.py` routes through `resolve_history_db()` [Agent 3 finding]
- New `TestWasteAttribution` class in `test_history_reader.py`, mirroring `TestCostAttribution`'s `_seed`/group-by/injection-guard/missing-db shape [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — `history_reader.py` module reference section needs a `waste_attribution()` entry
- `docs/ARCHITECTURE.md` — schema-versions table (documents `loop_runs`/`usage_events`/`orchestration_runs`) needs an entry for the v29 migration (corrected from v24)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md` (~line 108 `usage_events` row, ~line 112 `loop_runs` row) — separate schema reference table from ARCHITECTURE.md's; needs the same v29/`run_id`/`waste_attribution()` updates [Agent 2 finding]
- `docs/observability/otel-mapping.md` (~lines 55-65 "Persistence", ~67-74 "Cost attribution query") — documents `cost_attribution()` and the `invocation_id`/`provider_vendor` forward-compat columns; `run_id` is the same shape of forward-compat column and `waste_attribution()` is the same shape of query function, both in this doc's existing scope [Agent 2 finding]
- `docs/reference/CLI.md` (`### ll-ctx-stats`, lines 270-289) — CLI reference entry needs a new "waste" JSON-key/section documented, following the existing per-key pattern [Agent 2 finding]
- `commands/help.md:300` — one-line `ll-ctx-stats` description in the master command list; cosmetic update only if the tool's stated scope meaningfully expands [Agent 2 finding]

### Configuration
- `resolve_history_db()` (`session_store.py:179`) is the only config-path touchpoint, and only to fix `ctx_stats.py`'s existing bypass

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` (~line 1749-1752, `analytics.capture.usage_events` description) — needs updating if Option A's write-through ships (see Dependent Files note above) [Agent 2 finding]

## Impact

- **Priority**: P2 — cheap to build, potentially reorders all remaining token-cost work.
- **Effort**: Small (~100 LOC + tests), assuming outcome data exists; Medium if an outcome column must be backfilled.
- **Risk**: Low — read-only analytics.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-21_

**Readiness Score**: 100/100 → STRONG GO
**Outcome Confidence**: 61/100 → MODERATE (re-scored 2026-07-21 after confirming the `ARCHITECTURE-145` precedent is reconciled)

### Outcome Risk Factors
- Deep per-site complexity: the plan requires a new schema migration (v29) plus a live per-invocation `usage_events` writer wired into `fsm/executor.py`'s `_finish()`, and cascades into 12+ hardcoded `SCHEMA_VERSION == 28` assertions across 5 test files — this is architectural-level work, not a mechanical substitution.
- ~~No existing live per-invocation writer exists yet... unproven internal mechanism with no test coverage~~ — **retired by the 2026-07-21 spike** (`scripts/tests/spike/usage_events_run_id_writer/`): 5 tests proved the write mechanism, `run_id` derivation parity with `_finish()`, and concurrency safety under `ll-parallel`/`ll-sprint`-style overlap. Test coverage score raised 15→20 accordingly.
- Broad change surface: touches `session_store.py` (migration + write-through), `fsm/executor.py`, `history_reader.py`, `ctx_stats.py`, 4+ test files, and 4+ documentation files (`HISTORY_SESSION_GUIDE.md`, `otel-mapping.md`, `CLI.md`, `config-schema.json`) — wide blast radius beyond the core query/CLI layer the issue title implies.
- ~~Unreconciled precedent: `ARCHITECTURE-145`... no `.ll/decisions.yaml` entry formally reconciles them yet~~ — **retired**: `ARCHITECTURE-146` (`.ll/decisions.d/e01ffb15-39ab-46f4-827c-39c2a34c947b.json`, 2026-07-21T17:41:50Z) already reconciles this — `run_id` is a live per-invocation write authoritative at write time, not a backfill-derived FK, so `ARCHITECTURE-145`'s rejection doesn't apply. Ambiguity score raised 20→24 accordingly.

## Spike Results

_Added by `/ll:spike` on 2026-07-21_

**Retired risks**

| Risk (from Outcome Risk Factors) | Proven by | Result |
|----------------------------------|-----------|--------|
| No live per-invocation writer exists; unproven mid-run write mechanism | `TestUsageEventsRunIdWriter::test_single_run_stamps_correct_run_id` | ✓ pass |
| Concurrent `ll-parallel`/`ll-sprint` writers could cross-attribute or corrupt `run_id` | `TestUsageEventsRunIdWriter::test_concurrent_runs_do_not_cross_attribute` | ✓ pass |
| Concurrent writes under `busy_timeout`/WAL could silently drop rows | `TestUsageEventsRunIdWriter::test_concurrent_runs_lose_no_writes` | ✓ pass |
| `run_id` derivation must match `_finish()`'s inline format exactly for a drop-in wire-up | `TestUsageEventsRunIdWriter::test_run_id_derivation_matches_executor_format` | ✓ pass |
| Isolation guard (spike must not depend on production modules) | `TestUsageEventsRunIdWriter::test_spike_does_not_import_production_modules` | ✓ pass |

**Spike location**: `scripts/tests/spike/usage_events_run_id_writer/`
**Verification**: 5 spike tests pass; existing `usage_events`/`SchemaV28` (9 tests) and `CostAttribution` (4 tests) regression suites unaffected — 18 tests across 3 commands.
**Promotion**: move `record_usage_event()`/`derive_run_id()` to `scripts/little_loops/spike/usage_events_run_id_writer/` in a separate PR, then wire the real v29 migration and `_finish()` call-site change as the actual ENH-2712 implementation.

## Session Log
- `/ll:confidence-check` - 2026-07-21T18:15:00 - `bc2b7cf0-fc25-4700-a6e3-c95ced3f3fa8.jsonl`
- `/ll:confidence-check` - 2026-07-21T18:00:00 - `08339d06-d2c5-4f76-a31f-71e1fb61d2d9.jsonl`
- `/ll:spike` - 2026-07-21T17:36:14 - `74d7879e-9d6d-4546-b56a-52662ad4ace0.jsonl`
- `/ll:confidence-check` - 2026-07-21T17:29:51 - `086fb7d0-d311-4b83-80fa-36c69997912d.jsonl`
- `/ll:wire-issue` - 2026-07-21T17:23:04 - `712f520b-f072-48e5-bf39-095b885a0afe.jsonl`
- `/ll:decide-issue` - 2026-07-21T05:10:29 - `255186e7-f4f9-45b7-b959-38186bd122ed.jsonl`
- `/ll:refine-issue` - 2026-07-21T04:58:15 - `1992a3d7-7ba0-476d-80b0-50ba3a3e1eb8.jsonl`
- `/ll:capture-issue` - 2026-07-21T02:03:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79ab3d38-0b67-42aa-9ad2-b6f2af55d225.jsonl`

---

## Status

**Open** | Created: 2026-07-21 | Priority: P2
