---
id: ENH-2722
type: ENH
title: "ll-ctx-stats waste view over history.db (split from ENH-2712)"
priority: P2
status: open
captured_at: '2026-07-21T18:20:00Z'
discovered_date: '2026-07-21'
discovered_by: confidence-check
parent: EPIC-2456
blocked_by:
- ENH-2721
labels:
- token-cost
- observability
- history-db
relates_to:
- EPIC-2456
- ENH-2712
- ENH-2721
- FEAT-2478
- ENH-2477
- ENH-2461
- ENH-2623
decision_needed: false
---

# ENH-2722: `ll-ctx-stats` waste view over history.db (split from ENH-2712)

## Summary

Split out of ENH-2712's query/CLI half: once ENH-2721 lands a `run_id` join key on `usage_events`, add a `waste` view to `ll-ctx-stats` that joins per-run token totals against terminal run outcome, so failure-mode fixes can be ranked against per-token optimizations. This issue is read-only analytics — no schema changes.

## Motivation

All of EPIC-2456 optimizes $/token on successful work; nothing measures tokens spent on runs that produced no accepted artifact — oscillating loops, GATE_FAILED retries, toothless-evaluator iterations. If a meaningful share of spend goes to those runs, fixing them dominates every remaining tier of the epic — but today that share is unknown.

**Blocked by ENH-2721**: this issue's join (`usage_events.run_id = loop_runs.run_id`) does not exist until ENH-2721's schema migration and live writer ship. Do not start implementation before ENH-2721 is merged.

## Current Behavior

`ll-ctx-stats` reports context savings and per-tool stats; no view correlates token spend with run outcome. Wasted spend is invisible.

## Expected Behavior

`ll-ctx-stats` prints per-loop and aggregate: total tokens, tokens on runs ending in failure/stall/no-artifact, waste percentage, and the top-N most wasteful loops/states — read-only over `.ll/history.db` (respecting the `LL_HISTORY_DB` → config → default resolution, ENH-2623).

## Proposed Solution

- Define "wasted": run terminal status ∈ {failed, killed, max_steps-exhausted-without-success}. Start with terminal-status only; per-iteration `diff_stall`/`score_stall` discard tracking is an explicit follow-on, not in scope here.
- SQL join: `usage_events.run_id = loop_runs.run_id` (exact key, once ENH-2721 ships) — no time-range join, no schema change in this issue.
- Read-only; no automated deletion or compaction side effects (per project policy on `raw_events`).

## Implementation Steps

1. Query module in `history_reader.py` (`waste_attribution()`), modeled on `cost_attribution()` (line 854, whitelist-dict `_COST_ATTR_GROUP_COLUMNS` at line 843 guards `GROUP BY` against injection) and `aggregate_loop_runs()` (line 1550, whitelist `_LOOP_RUN_GROUP_COLUMNS` at line 1544). Follow the module's universal contract: `_connect_readonly()` (line 363, never raises), `try/except sqlite3.Error: logger.warning(...); return []`, numeric aggregates guarded with `row["x"] or 0`. Add to the module docstring's "Public API" list (lines 8-60).
2. CLI surface in `ctx_stats.py`: `ctx_stats.py` has no subcommand structure today (`_build_parser()`, line 40, is a flat parser) — add a `waste` section to the existing combined report (model `_aggregate_mcp_health()`, line 169, which thinly delegates to a `history_reader` function) rather than introducing a new subcommand structure.
3. Fix the existing `ctx_stats.py` ENH-2623 gap while touching this file: it does not call `resolve_history_db()` — it builds `db_path` from a locally-defined `DEFAULT_DB_RELPATH` (line 36), bypassing the `LL_HISTORY_DB` env/config chain entirely. Route through `resolve_history_db()` (`session_store.py:179`), following `cli/history.py:245,262,299,316`'s reference usage (`from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context, resolve_history_db`).
4. Docs: API.md entry + a short "interpreting waste" note.

## Scope Boundaries

- **Out of scope**: the `usage_events` schema migration and live writer — that is ENH-2721, which this issue is blocked on.
- **Out of scope**: per-iteration `diff_stall`/`score_stall` discard tracking — an explicit follow-on, not required for a terminal-status waste view.
- **In scope**: `waste_attribution()` query function, the `ll-ctx-stats` waste report section, and fixing `ctx_stats.py`'s existing `resolve_history_db()` bypass.

## Acceptance Criteria

- [ ] `waste_attribution()` returns per-loop totals: tokens_total, tokens_wasted, waste_pct, run counts.
- [ ] CLI view lists top wasteful loops with `--json` support.
- [ ] Read-only: no writes/deletes against history.db.
- [ ] `ctx_stats.py` routes through `resolve_history_db()` instead of its local `DEFAULT_DB_RELPATH`.
- [ ] Documented definition of "wasted" with its known limitations (terminal-status only, no per-iteration discard tracking yet).

## Integration Map

### Files to Modify
- `scripts/little_loops/history_reader.py` — add `waste_attribution()`, modeled on `cost_attribution()` (line 854) and `aggregate_loop_runs()` (line 1550)
- `scripts/little_loops/cli/ctx_stats.py` — add `_aggregate_waste()` (following `_aggregate_mcp_health()`, line 169) and a report section; fix the `resolve_history_db()` bypass (line 36)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/history.py:245,262,299,316` — reference implementation for the `resolve_history_db()` fix
- `scripts/little_loops/cli/loop/info.py:1161,1217` (`cmd_diagnose_evaluators()`, `cmd_calibrate_budget()`) — related but separate waste-adjacent tooling (evaluator health, not token cost); no code change needed, worth cross-referencing in docs

### Similar Patterns
- `history_reader.py:854` `cost_attribution()` — token-sum rollup with whitelisted `GROUP BY`
- `history_reader.py:1550` `aggregate_loop_runs()` — outcome rollup by `loop_name`/`terminated_by`
- `history_reader.py:739,789` `mcp_server_usage()` / `mcp_failure_rate()` — `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` success/failure rollup shape, closest existing analog to a waste-percentage calculation

### Tests
- `scripts/tests/test_history_reader.py` — `TestCostAttribution` (lines 92-181) and `test_aggregate_loop_runs` (~line 1786) are the fixture-seeding templates; `TestMissingDatabase`/`TestEmptyTables` (lines 29-89) for the never-raise contract. New `TestWasteAttribution` class mirroring the same shape.
- `scripts/tests/test_cli_ctx_stats.py` — `test_json_mode` / `test_json_mode_skill_health_present` (lines 282-366) for CLI-level `--json` assertions
- New test gap: `test_cli_ctx_stats.py` has no test that sets `LL_HISTORY_DB` env or `history.db_path` config with no `--db` flag — this is the regression proof for the `resolve_history_db()` fix; it fails today and passes once `ctx_stats.py` routes through `resolve_history_db()`

### Documentation
- `docs/reference/API.md` — `history_reader.py` module reference section needs a `waste_attribution()` entry
- `docs/ARCHITECTURE.md` — note the waste view as a consumer of ENH-2721's `run_id` join
- `docs/reference/CLI.md` (`### ll-ctx-stats`, lines 270-289) — new "waste" JSON-key/section
- `commands/help.md:300` — one-line `ll-ctx-stats` description, cosmetic update only

### Configuration
- `resolve_history_db()` (`session_store.py:179`) — only config-path touchpoint, to fix `ctx_stats.py`'s existing bypass

## Impact

- **Priority**: P2 — cheap to build once unblocked, potentially reorders remaining token-cost work.
- **Effort**: Small (~100 LOC + tests).
- **Risk**: Low — read-only analytics; the only dependency is ENH-2721's `run_id` column landing first.

## Status

**Open** | Created: 2026-07-21 | Priority: P2 | Blocked by: ENH-2721
