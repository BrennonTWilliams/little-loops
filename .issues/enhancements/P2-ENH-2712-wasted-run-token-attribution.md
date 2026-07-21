---
id: ENH-2712
type: ENH
title: "Wasted-run token attribution \u2014 ll-ctx-stats waste view over history.db"
priority: P2
status: open
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
decision_needed: false
size: Very Large
---

# ENH-2712: Wasted-run token attribution — ll-ctx-stats waste view over history.db

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

### Similar Patterns
- `history_reader.py:854` `cost_attribution()` — token-sum rollup with whitelisted `GROUP BY`
- `history_reader.py:1550` `aggregate_loop_runs()` — outcome rollup by `loop_name`/`terminated_by`
- `history_reader.py:739,789` `mcp_server_usage()` / `mcp_failure_rate()` — `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` success/failure rollup shape, the closest existing analog to a waste-percentage calculation

### Tests
- `scripts/tests/test_history_reader.py` — `TestCostAttribution` (lines 92-181) and `test_aggregate_loop_runs` (~line 1786) are the fixture-seeding templates; `TestMissingDatabase`/`TestEmptyTables` (lines 29-89) for the never-raise contract
- `scripts/tests/test_cli_ctx_stats.py` — `test_json_mode` / `test_json_mode_skill_health_present` (lines 282-366) for CLI-level `--json` assertions

### Documentation
- `docs/reference/API.md` — `history_reader.py` module reference section needs a `waste_attribution()` entry
- `docs/ARCHITECTURE.md` — schema-versions table (documents `loop_runs`/`usage_events`/`orchestration_runs`) needs an entry if Option A's v24 migration is chosen

### Configuration
- None — read-only feature; `resolve_history_db()` (`session_store.py:179`) is the only config-path touchpoint, and only to fix `ctx_stats.py`'s existing bypass

## Impact

- **Priority**: P2 — cheap to build, potentially reorders all remaining token-cost work.
- **Effort**: Small (~100 LOC + tests), assuming outcome data exists; Medium if an outcome column must be backfilled.
- **Risk**: Low — read-only analytics.

## Session Log
- `/ll:decide-issue` - 2026-07-21T05:10:29 - `255186e7-f4f9-45b7-b959-38186bd122ed.jsonl`
- `/ll:refine-issue` - 2026-07-21T04:58:15 - `1992a3d7-7ba0-476d-80b0-50ba3a3e1eb8.jsonl`
- `/ll:capture-issue` - 2026-07-21T02:03:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79ab3d38-0b67-42aa-9ad2-b6f2af55d225.jsonl`

---

## Status

**Open** | Created: 2026-07-21 | Priority: P2
