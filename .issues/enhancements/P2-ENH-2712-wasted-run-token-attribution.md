---
id: ENH-2712
type: ENH
title: Wasted-run token attribution — ll-ctx-stats waste view over history.db
priority: P2
status: open
captured_at: "2026-07-21T02:03:13Z"
discovered_date: "2026-07-21"
discovered_by: capture-issue
parent: EPIC-2456
labels: [token-cost, observability, history-db]
relates_to: [EPIC-2456, FEAT-2478, ENH-2477, ENH-2461]
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

## Implementation Steps

1. Audit what run-outcome + token data `history.db` already holds; document the join.
2. Query module in `history_reader.py` (`waste_attribution()`), tested against fixture DB.
3. CLI surface in `ctx_stats.py` (or `ll-history`) with `--json` output.
4. Docs: API.md entry + a short "interpreting waste" note.

## Acceptance Criteria

- [ ] `waste_attribution()` returns per-loop totals: tokens_total, tokens_wasted, waste_pct, run counts.
- [ ] CLI view lists top wasteful loops with `--json` support.
- [ ] Read-only: no writes/deletes against history.db.
- [ ] Documented definition of "wasted" with its known limitations.

## Impact

- **Priority**: P2 — cheap to build, potentially reorders all remaining token-cost work.
- **Effort**: Small (~100 LOC + tests), assuming outcome data exists; Medium if an outcome column must be backfilled.
- **Risk**: Low — read-only analytics.

## Session Log
- `/ll:capture-issue` - 2026-07-21T02:03:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79ab3d38-0b67-42aa-9ad2-b6f2af55d225.jsonl`

---

## Status

**Open** | Created: 2026-07-21 | Priority: P2
