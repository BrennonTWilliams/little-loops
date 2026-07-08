---
id: FEAT-2476
title: "F2 — --max-cost accumulator + 80%/100% guard + ELIS one-line forecast (umbrella coordination tracker)"
type: FEAT
priority: P2
status: open
captured_at: "2026-07-04T20:05:34Z"
discovered_date: 2026-07-04
discovered_by: capture-issue
parent: EPIC-2456
relates_to: [FEAT-2548, FEAT-2549, FEAT-2550, ENH-2475, ENH-2477, FEAT-2478, ENH-2461, FEAT-2123]
labels:
  - token-cost
  - budget
  - fsm
  - cli
  - tier-1
  - umbrella
decision_needed: false
confidence_score: 95
outcome_confidence: 62
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 10
---

# FEAT-2476: F2 — `--max-cost` accumulator + 80%/100% guard + ELIS one-line forecast (umbrella)

> **This is the umbrella coordination tracker for the F2 feature.**
> Implementation lives in three children (FEAT-2548 → FEAT-2549 →
> FEAT-2550). This file holds the shared scope, motivation, and
> expected behavior; the per-child file lists, anchors, implementation
> steps, and acceptance criteria live in each child. See
> `## Children` below.

## Use Case

As an operator who wants to cap a long-running `ll-loop run` at a
USD ceiling, I want a `--max-cost` flag plus a `cost_limits.*`
config fallback so a misconfigured loop cannot burn through budget
unnoticed. The F2 feature decomposes into three children along
the natural data-flow seams (FEAT-2548 primitive → FEAT-2549 CLI
→ FEAT-2550 integration); this umbrella tracks the overall scope
and ensures the three land together.

## Summary

Add a USD-cost accumulator over FSM iterations, a CLI flag
(`--max-cost`) that aborts when the configured ceiling is hit, and an
ELIS-based one-line regression forecast on completion. This is
EPIC-2456 § Children [TBD-4] — Goal #1 from the EPIC.

Pricing already exists at `scripts/little_loops/pricing.py:10–78`
(`MODEL_PRICING` with Opus/Sonnet/Haiku rows including cache fields
and `estimate_cost_usd()`). Per-state cost aggregation (ENH-2477) is
complete in `scripts/little_loops/fsm/cost_graph.py`. The children
below add the missing **ceiling** surface (CLI flag, accumulator,
soft/hard guard, ELIS forecast, config layer, OTel transport, docs).

## Motivation

Every `ll-loop run` invocation today has no inherent cost ceiling —
the loop will spend what it spends. For ad-hoc and CI contexts, that
means a single misconfiguration can burn through budget before an
operator notices. EPIC-2456 Goal #1 makes the `--max-cost` ceiling
first-class.

Compounding across `ll-auto` / `ll-sprint` / `ll-parallel` and ad-hoc
`ll-loop` invocations, the spend surface is large; the optimization
surface for *capping* spend has no existing primitive. The
`cost_limits.max_cost_per_run` config key does **not** exist in
`.ll/ll-config.json` or `config-schema.json`; the children introduce
the key and the code that reads it.

## Current Behavior

- `scripts/little_loops/pricing.py` exposes `estimate_cost_usd()` and
  `MODEL_PRICING` rows for Opus/Sonnet/Haiku.
- `scripts/little_loops/cli/loop/_helpers.py:1652-1714`
  (`_print_usage_summary`) prints a per-state cost table but does
  not enforce any limit.
- `scripts/little_loops/fsm/cost_graph.py` (ENH-2477, completed)
  aggregates per-state cost; F2 reads from this layer.
- `ll-loop run` accepts no cost-related flag.
- No `cost_limits.*` keys in `.ll/ll-config.json` or
  `config-schema.json`.

### Codebase Research Findings (summary)

- **Stale anchor (refine-pass 2026-07-05)**: the original
  `executor.py:1295-1305` cite is the `_resolve_next_state()`
  interceptor hook, NOT cache aggregation. The actual per-action
  aggregation lives in `FSMExecutor._run_action()` at
  `fsm/executor.py:1382-1392` (sums `result.usage_events:
  list[TokenUsage]` — `subprocess_utils.py:44-56` — into
  `action_complete` payload). The RSS-budget twin sits at
  `fsm/executor.py:1395-1414`.
- **`.ll/ll-config.json` does NOT yet document `cost_limits.*`
  keys.** The children introduce them (Tier 1).
- **Data source for the ELIS forecast is `<run_dir>/usage.jsonl`
  (run-local), NOT `.ll/history.db`.** `usage.jsonl` is written by
  `PersistentExecutor._handle_event()` at
  `fsm/persistence.py:637-655`. ENH-2461 proposes a future
  `usage_event` table at `session_store._MIGRATIONS`, but that is
  not yet implemented.

## Expected Behavior

- `ll-loop run --max-cost=1.00` accepts a USD ceiling; the run
  halts at the configured ceiling ±5% on representative workloads
  and **never** exceeds it.
- At 80% of the ceiling the run emits a soft warning (continues).
  At 100% it emits a hard-stop and exits with a typed non-zero
  code (`EXIT_CODES["cost_budget_exceeded"] == 1`).
- On completion (success or halt), the run prints an ELIS
  one-line regression forecast: predicted final cost vs. measured
  final cost, with forecast error ≤15% on held-out trace sets.
- `cost_limits.max_cost_per_run` and `cost_limits.warn_at` read
  from `.ll/ll-config.json` and the loop YAML schema
  (`budget_accumulator:` block) are honored as fallback values
  when the CLI flag is absent.
- `loop_complete` event payload carries `total_cost_usd` and
  `cost_unknown_model` for downstream consumers (OTel transport,
  `ll-loop info`, `ll-logs`).

## Acceptance Criteria

See the children's `## Acceptance Criteria` sections for detailed
end-to-end ACs:

- **FEAT-2548** — `BudgetAccumulator` / `BudgetGuard` / `ELISForecast`
  primitive + `BudgetAccumulatorConfig` dataclass + validation +
  JSON Schema.
- **FEAT-2549** — `--max-cost` argparse flag on `ll-loop run` and
  `ll-loop resume`; `EXIT_CODES["cost_budget_exceeded"] == 1`;
  `run_background` re-exec forwarding; `cmd_run` override
  application; resume runtime override.
- **FEAT-2550** — executor wiring (post-state accumulator + guard
  emit; post-state-execution check; `_finish()` payload);
  `loop_complete` payload fields `total_cost_usd` /
  `cost_unknown_model`; OTel span attributes; `CostLimitsConfig`;
  `init/core.py` defaults; all docs; all tests.

The umbrella is `done` when all three children are `done` and
`python -m pytest scripts/tests/` exits 0 across the combined
change set.

## Children

This feature is decomposed into three children along the natural
data-flow seams (a → b → c). Each lands as its own PR; FEAT-2476
stays open until all three are done.

- **FEAT-2548** — F2a `fsm/budget.py` primitive:
  `BudgetAccumulator` + `BudgetGuard` + `ELISForecast` +
  `BudgetAccumulatorConfig` dataclass + validation (`KNOWN_TOP_LEVEL_KEYS`
  + `_validate_cost_limits`) + JSON Schema mirror + `fsm/__init__.py`
  re-exports. **5 files** (`fsm/budget.py` new + `fsm/schema.py` +
  `fsm/validation.py` + `fsm/fsm-loop-schema.json` +
  `fsm/__init__.py`). Tests: `test_fsm_budget.py` (new).
  *(filed 2026-07-08, P2)*

- **FEAT-2549** — F2b `--max-cost` CLI surface: argparse flag on
  `ll-loop run` + `ll-loop resume`, `EXIT_CODES["cost_budget_exceeded"]`
  entry, `run_background` re-exec forwarding, `cmd_run` override
  application, resume runtime override. **4 files**
  (`cli/loop/__init__.py` + `cli/loop/run.py` +
  `cli/loop/_helpers.py` + `cli/loop/lifecycle.py`). Tests:
  `test_cli_max_cost.py` (new) + extensions in
  `test_cli_args.py` + `test_ll_loop_parsing.py`. Depends on
  **FEAT-2548**. *(filed 2026-07-08, P2)*

- **FEAT-2550** — F2c executor wiring + OTel transport +
  `CostLimitsConfig` + `init/core.py` defaults + docs + tests.
  **~18 files** (4 executor sites, transport, event schemas,
  config layer, 3 CLI display consumers, 8 doc files, 4 test
  files). Depends on **FEAT-2548** + **FEAT-2549**.
  *(filed 2026-07-08, P2)*

### Implementation decisions (resolved)

- **A1**: `fsm/budget.py` location (next to `fsm/host_guard.py` —
  structural twin precedent).
- **B1**: pure-Python ELIS via stdlib
  `statistics.linear_regression(range(n), values).slope`
  (`issue_history/summary.py:184` template). No scipy/numpy.
- **C**: place `budget_accumulator:` on `FSMLoop` top-level (mirror
  `host_guard`), not per-state (per-state schema keys are owned by
  ENH-2477).
- **D**: warn threshold default 0.8 (80%).

### Coordination notes (deferred, out of F2 scope)

- Cross-host `usage_events` parity (`runners.py:46-180`,
  `issue_manager.py`, `parallel/worker_pool.py`) — gated on
  **FEAT-2123**. F2 emits `cost: n/a (unknown model)` on hosts
  lacking this plumbing.
- `history.db` `usage_event` table — gated on **ENH-2461**. F2
  reads from `usage.jsonl` (run-local) only.

## Scope Boundaries

- **In**: USD-cost ceiling, soft/hard guard, ELIS one-line
  forecast, CLI flag, config wiring, OTel surface, docs.
- **Out**: Routing cascade (F7-lite); OTel `gen_ai.usage.*`
  attribute emission (F5 / FEAT-2478); LLMLingua compression
  (F4-gated); streams-of-prompt-cost prediction beyond simple
  one-line regression.
- **Out of scope**: cross-host parity (FEAT-2123); history.db
  persistence (ENH-2461).

## Impact

- **Priority**: P2 — high-leverage; first-clamp primitive for
  runaway cost.
- **Effort**: Medium — ~160 LOC primitive (F2a) + ~80 LOC CLI
  (F2b) + ~250 LOC integration (F2c) ≈ 490 LOC across the
  three children, plus tests and docs.
- **Risk**: Low — additive; guard defaults to `unlimited`; OTel
  attributes are best-effort; existing runs unchanged.
- **Breaking Change**: No — flag is opt-in; default behavior
  unchanged.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-08_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 62/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across ~20 sites spanning code, tests, config, docs, OTel transport, and event schemas — manageable because most sites are mechanical mirror-adds to existing patterns (host_guard, throttle, LoopRunDefaults).
- Blast radius from new `loop_complete` payload fields (`total_cost_usd`, `cost_unknown_model`) consumed by `transport.py:462-477`, `cli/loop/info.py:379-383`, `cli/loop/_helpers.py:1740-1796`, `cli/logs.py:1752,1769,1778`, and `init/core.py` — 8+ downstream consumers across multiple subsystems.

_Added by `/ll:confidence-check` on 2026-07-08 (split pass)_

**Split decision**: outcome confidence was 62/100 (MODERATE) dominated
by 16+ site breadth, not ambiguity. Decomposed into FEAT-2548
(primitive, expected HIGH), FEAT-2549 (CLI, expected HIGH), and
FEAT-2550 (integration, expected MODERATE) along natural
data-flow seams. Each lands as its own PR; this umbrella stays
`status: open` until all three children are done. No spec
content lost — every anchor, decision, and acceptance criterion
moved to its owning child.

## Status

**Open** | Created: 2026-07-04 | Priority: P2 | Split 2026-07-08 → FEAT-2548 / FEAT-2549 / FEAT-2550

## Session Log
- `/ll:confidence-check` (split) - 2026-07-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d276935-0474-4bff-85e3-154d56cf1226.jsonl`
- `/ll:refine-issue` - 2026-07-05T05:28:38 - `0dd2f4a0-5634-48f9-b6d1-6c46f2d01c58.jsonl`
- `/ll:decide-issue` - 2026-07-05T05:19:14 - `24fd5b80-284c-4979-a68e-8175dca88a5f.jsonl`
- `/ll:wire-issue` - 2026-07-05T05:03:44 - `e2c32cf7-41b3-4238-8159-397c566f5606.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:53:57 - `8c12fca6-38f6-4c73-9351-ad9e1a4928e3.jsonl`

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
