---
id: FEAT-2476
title: "F2 — --max-cost accumulator + 80%/100% guard + ELIS one-line forecast"
type: FEAT
priority: P2
status: open
captured_at: "2026-07-04T20:05:34Z"
discovered_date: 2026-07-04
discovered_by: capture-issue
parent: EPIC-2456
relates_to: [ENH-2475, ENH-2461, FEAT-2123]
labels:
  - token-cost
  - budget
  - fsm
  - cli
  - tier-1
---

# FEAT-2476: F2 — --max-cost accumulator + 80%/100% guard + ELIS one-line forecast

## Summary

Add a USD-cost accumulator over FSM iterations, a CLI flag
(`--max-cost`) that aborts when the configured ceiling is hit, and an
ELIS-based one-line regression forecast on completion. This is
EPIC-2456 § Children [TBD-4] — Goal #1 from the EPIC.

Pricing already exists at `scripts/little_loops/pricing.py:10–55`
(`MODEL_PRICING` with Opus/Sonnet/Haiku rows including cache fields) and
`estimate_cost_usd()` at lines 58–78; per-state cache aggregation exists
at `scripts/little_loops/fsm/executor.py:1295–1305`. This child adds the
missing **ceiling** surface (CLI flag, accumulator, soft/hard guard,
forecast).

## Motivation

Every `ll-loop run` invocation today has no inherent cost ceiling — the
loop will spend what it spends. For ad-hoc and CI contexts, that means a
single misconfiguration can burn through budget before an operator
notices. EPIC-2456 Goal #1 makes the `--max-cost` ceiling first-class.

Compounding across `ll-auto` / `ll-sprint` / `ll-parallel` and ad-hoc
`ll-loop` invocations, the spend surface is large; the optimization
surface for *capping* spend has no existing primitive. The
`cost_limits.max_cost_per_run` config key already exists in
`.ll/ll-config.json` (per `commands/ll-init` defaults) but no code reads
it; this child closes the loop.

## Current Behavior

- `scripts/little_loops/pricing.py` exposes `estimate_cost_usd()` and
  `MODEL_PRICING` rows for Opus/Sonnet/Haiku.
- `scripts/little_loops/cli/loop/_helpers.py:1676` prints a per-state
  cost table but does not enforce any limit.
- `scripts/little_loops/fsm/executor.py:1295–1305` aggregates
  `cache_read`/`cache_creation` per state but does not project forward
  or halt.
- `ll-loop run` accepts no cost-related flag.

## Expected Behavior

- `ll-loop run --max-cost=1.00` accepts a USD ceiling; the run halts at
  the configured ceiling ±5% on representative workloads and **never**
  exceeds it.
- At 80% of the ceiling the run emits a soft warning (continues). At
  100% it emits a hard-stop and exits with a typed non-zero code.
- On completion (success or halt), the run prints an ELIS
  one-line regression forecast: predicted final cost vs. measured final
  cost, with forecast error ≤15% on held-out trace sets.
- `cost_limits.max_cost_per_run` and per-state `cost_ceiling_per_state`
  / `cost_warn_at` read from `.ll/ll-config.json` and the loop YAML
  schema are honored as fallback values when the CLI flag is absent.

## Proposed Solution

1. **`scripts/little_loops/fsm/budget.py`** (new, ~120 LOC):
   - `BudgetAccumulator` — adds `usage` from each FSM state into a
     running total using `pricing.estimate_cost_usd()`.
   - `BudgetGuard.check(usage)` — returns one of `OK`, `WARN`,
     `HALT` based on accumulated spend vs. ceiling and thresholds.
   - `ELISForecast.fit(state_history, k=1)` + `.predict(steps)` — one-
     line regression over per-state cost; emits predicted final cost
     given `steps_ahead`.

2. **`scripts/little_loops/cli/loop/__main__.py`**: add `--max-cost`
   argparse flag. Defaults to `None` (unlimited); when set, passed
   through to `fsm/executor.run_loop`.

3. **`scripts/little_loops/fsm/executor.py:1295–1305` extension**:
   - After each state, call `BudgetAccumulator.add(usage)`.
   - After each state, call `BudgetGuard.check(acc.total)` and route
     `WARN` → log warning, `HALT` → exit with non-zero code.
   - On completion, print `ELISForecast` summary line.

4. **`scripts/little_loops/fsm/schema.py`**: add `cost_ceiling_per_state`
   and `cost_warn_at` keys to the loop YAML schema (interacts with F6
   child — coordinate on JSON output shape).

5. **Config plumbing**: `.ll/ll-config.json` already documents
   `cost_limits.*` keys; just read them in `fsm/budget.py`.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/budget.py` (new) — accumulator + guard + ELIS
- `scripts/little_loops/cli/loop/__main__.py` — `--max-cost` argparse
- `scripts/little_loops/fsm/executor.py:1295–1305` — wire accumulator + guard
- `scripts/little_loops/fsm/schema.py` — `cost_ceiling_per_state` /
  `cost_warn_at` loop-YAML keys
- `scripts/little_loops/pricing.py` (no change, already supports)
- `.ll/ll-config.json` (already documents `cost_limits.*`; verify naming)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/_helpers.py:1676` — per-state cost
  table extension feeds the accumulator
- `scripts/little_loops/loops/general-task.yaml`,
  `loops/deep-research.yaml`, others — opt into `--max-cost` defaults

### Similar Patterns

- `scripts/little_loops/fsm/budget.py` (new) mirrors shape conventions
  from `fsm/validation.py` (typed guards returning enums)
- ELIS regression: one-line weighted least-squares with the existing
  `tools/math.py` if any — confirm by grep before adding new dep

### Tests

- `scripts/tests/test_fsm_budget.py` (new) — accumulator + guard + ELIS
  forecast ≤15% error on representative runs
- `scripts/tests/test_cli_max_cost.py` (new) — `--max-cost` halts at
  ceiling ±5%, never exceeds, propagates non-zero exit

### Documentation

- `docs/reference/API.md` — `fsm/budget.py` module
- `docs/ARCHITECTURE.md` — note `cost_limits` config wiring in the
  "Token cost layer" section (added by EPIC-2456's central doc pass)

### Configuration

- `cost_limits.max_cost_per_run` (USD) — primary runtime ceiling
- `cost_limits.warn_at` (default 0.8) — soft warning threshold
- Loop YAML: `cost_ceiling_per_state`, `cost_warn_at` per-state overrides

## Implementation Steps

1. Author `fsm/budget.py` with `BudgetAccumulator`, `BudgetGuard`,
   `ELISForecast`
2. Wire `BudgetAccumulator.add(usage)` into `fsm/executor.py` post-state
3. Add `--max-cost` flag to `cli/loop/__main__.py`; pass through to executor
4. Extend `fsm/schema.py` with `cost_ceiling_per_state` / `cost_warn_at`
5. On completion, print `ELISForecast` one-line summary
6. Add `scripts/tests/test_fsm_budget.py` + `scripts/tests/test_cli_max_cost.py`
7. Verify `python -m pytest scripts/tests/` exits 0
8. Coordinate with **ENH-2461** (persist real LLM token usage into
   `history.db`) — the `usage` payload this consumes must come from
   ENH-2461's storage, not from a parallel ad-hoc source
9. Coordinate with **FEAT-2123** (surface token usage from Codex/OpenCode
   runners) when `--max-cost` runs on non-Claude hosts

## Acceptance Criteria

- `ll-loop run --max-cost=1.00` exits at $1.00 ± 5% on representative
  workloads and never exceeds
- 80% of ceiling emits a soft warning; 100% emits hard-stop with typed
  non-zero exit
- On completion, ELIS forecast line prints; forecast error ≤15% on held-
  out trace sets
- `cost_limits.max_cost_per_run` is honored when `--max-cost` is absent
- Per-state `cost_ceiling_per_state` / `cost_warn_at` honored from loop
  YAML
- `python -m pytest scripts/tests/` exits 0

## Scope Boundaries

- **In**: USD-cost ceiling, soft/hard guard, ELIS one-line forecast,
  CLI flag, config wiring
- **Out**: Routing cascade (F7-lite); OTel `gen_ai.usage.*` attribute
  emission (F5); LLMLingua compression (F4-gated)
- **Out of scope**: streams-of-prompt-cost prediction beyond simple
  one-line regression

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent; § Tier 1 [TBD-4], Goal #1 |
| `scripts/little_loops/pricing.py:10–78` | Source-of-truth pricing rows used here |
| `scripts/little_loops/fsm/executor.py:1295–1305` | Where the accumulator wires in |
| `ENH-2461` | Provides the persistence layer this consumes |
| `FEAT-2123` | Cross-host parity that gates multi-host `--max-cost` |

## Impact

- **Priority**: P2 — high-leverage; first-clamp primitive for runaway cost
- **Effort**: Medium — ~160 LOC across budget module + flag + executor wiring + tests
- **Risk**: Low — additive; guard defaults to `unlimited`; existing runs unchanged
- **Breaking Change**: No — flag is opt-in; default behavior unchanged

## Status

**Open** | Created: 2026-07-04 | Priority: P2

## Session Log

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
