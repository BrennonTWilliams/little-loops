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
decision_needed: false
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Stale anchor: `executor.py:1295-1305` is the `_resolve_next_state()` interceptor hook loop, NOT cache aggregation.** The actual per-action aggregation that produces the `usage` payload a budget guard would consume is in `FSMExecutor._run_action()` at `scripts/little_loops/fsm/executor.py:1378-1393` (sums `result.usage_events: list[TokenUsage]` — `subprocess_utils.py:44-52` — into `action_complete` payload). The RSS-budget wiring sits at `executor.py:1395-1414` and is the structural twin for `BudgetAccumulator.add(...)`.
- **`.ll/ll-config.json` does NOT yet document `cost_limits.*` keys.** The issue summary claim "config-schema.json already documents" is stale per `FEAT-2470` line 150 confirmation and a fresh grep of `.ll/ll-config.json:91-96` (only `loops.run_defaults` is present). Tier 1 lands the keys; the per-loop YAML `budget_accumulator:` block is the primary path (mirrors `host_guard.max_cumulative_subproc_mb`).
- **Data source for the ELIS forecast is `<run_dir>/usage.jsonl` (run-local), NOT `.ll/history.db`.** `usage.jsonl` is written by `PersistentExecutor._handle_event()` at `scripts/little_loops/fsm/persistence.py:637-655` keyed on `self._executor.current_state`. ENH-2461 proposes a future `usage_event` table at `session_store._MIGRATIONS`, but that is not yet implemented.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The 5-step plan above has three distinct implementation-choice decisions an
implementer must resolve before coding; /ll:decide-issue is required prior to
`/ll:wire-issue`. Documented below as candidates — pick one per `/ll:decide-issue`.

#### Decision A — Budget module placement

- **Option A1 (issue proposal)**: New module `scripts/little_loops/fsm/budget.py` next to `fsm/host_guard.py`. Pros: matches `host_guard.py` sibling; `fsm/` is where accumulator+guard primitives live. Cons: re-uses `pricing.estimate_cost_usd` only.
- **Option A2**: Extend `scripts/little_loops/pricing.py` with `BudgetAccumulator` / `BudgetGuard` next to `estimate_cost_usd`. Pros: pricing and accumulation colocated; ELIS lives where the data lives. Cons: pricing.py becomes more than pricing — crosses a clean package boundary.
- **Option A3**: Top-level `scripts/little_loops/budget.py`. Pros: `cost_limits` becomes a first-class concept adjacent to `pricing`. Cons: breaks the existing `fsm/` location for executor-coupled accumulators (`rate_limit_circuit.py`, `host_guard.py`, `stall_detector.py` are all `fsm/`).

> **Selected:** A1 — `host_guard.py` is the structural twin and lives under `fsm/`; dominant precedent.

The dominant precedent is **A1** — `host_guard.py` is the structural twin and lives under `fsm/`. Recommended.

#### Decision B — ELIS implementation style

- **Option B1**: Pure-Python OLSE dataclass in `fsm/budget.py` mirroring `stats.wilson_ci` shape (`stats.py:13-39`) — no new dependencies. `fit(state_history)` returns `(slope, intercept)`; `predict(steps)` extrapolates. Pure function, no scikit-learn.
- **Option B2**: Add `scipy.stats.linregress` dependency. Pros: more robust small-sample statistics. Cons: violates the project's "no scipy" convention (`grep -r scipy scripts/little_loops` returns no hits).
- **Option B3**: Numpy polyfit. Cons: introduces numpy, not currently in dependency tree.

> **Selected:** B1 — greenfield, no existing ELIS/OLS/WLS implementation to conflict with; matches the project's no-scipy/no-numpy convention.

The codebase has **zero** existing ELIS / OLS / WLS implementations; this is greenfield. B1 is dominant.

#### Codebase Research Findings (refine pass 2026-07-05)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Better B1 template found**: `scripts/little_loops/issue_history/summary.py:171-196`
  `_calculate_trend(values: list[float]) -> str` already performs a one-line
  linear regression via stdlib **`statistics.linear_regression(range(n),
  values).slope`** (Python 3.11+, no scipy/numpy) — normalizes slope by
  average value, buckets into increasing/decreasing/stable. This is a closer
  precedent for `ELISForecast.fit()/.predict()` than `stats.py:wilson_ci()`
  (which is Wilson-interval math, not regression); use `_calculate_trend`'s
  `statistics.linear_regression` call as the primary template and
  `wilson_ci` only for the dataclass/guard-clause shape.

#### Decision C — Config schema placement (per-state overhead keys)

- The issue's step 4 lists `cost_ceiling_per_state` / `cost_warn_at` on the loop YAML schema. **Sibling ENH-2477 owns these schema keys** (per `ENH-2477` § Current Behavior line 24-30; insertion target `schema.py:457`). FEAT-2476's `_validate_cost_limits` should validate the per-state overrides only if ENH-2477 lands first; otherwise, defer. Recommended: place the F2 fields only on `FSMLoop` top-level (`budget_accumulator: BudgetAccumulatorConfig` at `schema.py:1018-1020`, mirroring `host_guard`).

#### Decision D — Warn threshold default

- Default 0.8 (80%) of `max_cost_usd` matches the `host_guard.warn_pct = 75` precedent loosely; AC says "80%" — keep at 0.8.

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

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md:579-638, 953, 1057, 1100` — extend
  `loop_complete` event schema prose with `total_cost_usd` and
  `cost_unknown_model` keys
- `docs/reference/HOST_COMPATIBILITY.md:132` — note `opencode` / `codex`
  usage-event caveat (gates cross-host `--max-cost` parity on FEAT-2123)
- `docs/reference/API.md:4335, 5346-5405, 4924-4925` — author
  `little_loops.fsm.budget` Python module reference (mirror existing
  `little_loops.fsm.host_guard` template at those lines)
- `docs/guides/LOOPS_GUIDE.md:149-191` — author `budget_accumulator:`
  block docs (mirror `host_guard:` block template at those lines)
- `docs/reference/CONFIGURATION.md:393-396` — author `cost_limits.*`
  sub-table (parallel to existing `rate_limits.*` table at those lines)

### Configuration

- `cost_limits.max_cost_per_run` (USD) — primary runtime ceiling
- `cost_limits.warn_at` (default 0.8) — soft warning threshold
- Loop YAML: `cost_ceiling_per_state`, `cost_warn_at` per-state overrides

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/features.py:611-654` —
  `LoopRunDefaults`/`LoopsConfig` dataclass must gain a
  `cost_limits: CostLimitsConfig` field (or accept top-level
  `cost_limits` via `LoopsConfig.from_dict` round-trip) so `cost_limits.*`
  keys survive load/save of `.ll/ll-config.json`
- `scripts/little_loops/config/__init__.py:76-128` — `__all__` exports
  must include `CostLimitsConfig`
- `scripts/little_loops/init/core.py:96-100, 184-193` —
  `loop_max_cost_default` choice (or schema-default fallback) so
  `ll-init --yes` / `ll-init --plan` emit `cost_limits.*` keys into
  `.ll/ll-config.json:91-96`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The integration surface spans the following *additional* files beyond what the
issue lists — these were uncovered by the parallel research agents and are
required for the implementation to compile/run end-to-end.

#### Additional Files to Modify (research-found)

- `scripts/little_loops/fsm/validation.py:174-200` — extend `KNOWN_TOP_LEVEL_KEYS`
  frozenset to whitelist `"cost_limits"` and `"budget_accumulator"` so
  `validate_fsm` doesn't warn "unknown top-level key".
- `scripts/little_loops/fsm/validation.py:1038-1060` — append `_validate_cost_limits(fsm, defined_states)`
  call in the `validate_fsm()` dispatcher; new function near `validation.py:2051-2176`
  (`_validate_host_guard`) is the canonical template.
- `scripts/little_loops/fsm/fsm-loop-schema.json:274-318` — mirror the
  `host_guard` schema block to add a top-level `budget_accumulator:` JSON Schema
  definition (see commit auto-generated by `ll-generate-schemas` for the
  analogous `host_guard` block).
- `scripts/little_loops/cli/loop/_helpers.py:1313-1379` — `run_background` re-exec
  forwarding must append `--max-cost=$arg` to `cmd` (mirrors `max_iter` at
  line 1319); otherwise detached runs silently drop the flag.
- `scripts/little_loops/cli/loop/_helpers.py:30-38` — add `"cost_budget_exceeded": 1`
  to `EXIT_CODES` so `run_foreground()` at `:1644` returns the typed exit code.
  (`host_budget_exceeded` is not in EXIT_CODES today; F2 should add its key
  proactively for consistency.)
- `scripts/little_loops/cli/loop/_helpers.py:1605-1616` — extend the
  `run_foreground()` completion block to print the ELIS forecast one-line
  alongside the existing completion print.
- `scripts/little_loops/cli/loop/lifecycle.py:280, 464-465` — register
  `--max-cost` for the `resume` subparser (mirroring
  `add_handoff_threshold_arg` / `add_context_limit_arg` at the same lines).
- `scripts/little_loops/fsm/executor.py:2239-2248` — extend `_finish()` payload
  with `total_cost_usd` and `cost_unknown_model` keys so the OTel transport
  can surface them as span attributes.
- `scripts/little_loops/fsm/executor.py:582-609` — handle
  `_pending_cost_budget_exceeded` flag alongside the existing
  `_pending_host_budget_exceeded` / stall-detector check sequence
  (insert between host-budget and stall-detector blocks).
- `scripts/little_loops/fsm/types.py:24-27` — extend `ExecutionResult.terminated_by`
  docstring to include `"cost_budget_exceeded"`.
- `scripts/little_loops/transport.py:462-477` — `_handle_loop_complete()` should
  surface `total_cost_usd` (and `cost_unknown_model`) as OTel span attributes.
- `scripts/little_loops/generate_schemas.py:196+` — add `cost_budget_warn` and
  `cost_budget_exceeded` schema entries next to the existing `stall_detected`
  event schema entry.
- `docs/reference/CLI.md:14, 545-590` — register the `--max-cost` flag in the
  `Common Flags` table and `ll-loop run` section; document the ELIS one-line
  forecast format alongside the existing per-state cost table column reference.
- `docs/reference/CONFIGURATION.md` — add a `cost_limits` config table
  documenting `max_cost_per_run` and `warn_at` keys (no entries currently).
- `docs/reference/API.md:62` — add `little_loops.fsm.budget` to the
  `little_loops.fsm` Module Overview table.
- `docs/ARCHITECTURE.md` — add a "Token cost layer" subsection documenting
  the BudgetAccumulator / BudgetGuard / ELISForecast primitives (the
  EPIC-2456 central doc pass owns this).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/features.py:611-654` — author
  `CostLimitsConfig` dataclass alongside `LoopRunDefaults` (`to_dict`
  skip-if-default round-trip mirror)
- `scripts/little_loops/config/__init__.py:76-128` — export
  `CostLimitsConfig` in `__all__` next to existing `LoopRunDefaults`
- `scripts/little_loops/init/core.py:96-100, 184-193` — add
  `loop_max_cost_default` choice (mirror `loop_clear_default:184` /
  `loop_show_diagrams_default:186`) so `ll-init --yes` /
  `ll-init --plan` emit `cost_limits.*` defaults into
  `.ll/ll-config.json:91-96`
- `scripts/little_loops/fsm/__init__.py:76-241` — re-export
  `BudgetAccumulator`, `BudgetGuard`, `ELISForecast`,
  `BudgetAccumulatorConfig` at the `fsm/` top level (otherwise
  `fsm.budget` symbols are reachable only by full path)
- `docs/reference/schemas/loop_complete.json` — extend `loop_complete`
  schema with `total_cost_usd` (number, ≥0) and `cost_unknown_model`
  (boolean) payload fields (mirror existing `duration_ms` entry)

#### Dependent Files (Callers/Importers) — research-confirmed

- `scripts/little_loops/cli/loop/_helpers.py:1608-1614` — `_print_usage_summary()`
  is called from `run_foreground()`. F2 will print the ELIS forecast line
  alongside this call without modifying it.
- `scripts/little_loops/cli/loop/_helpers.py:1652-1714` — existing
  `_print_usage_summary()` (read-only consumer of `usage.jsonl`) must remain
  bit-identical; F2 only extends the completion block, not the per-state table.
- `scripts/little_loops/loops/general-task.yaml`, `loops/deep-research.yaml`,
  others — opt into `--max-cost` defaults via `budget_accumulator:` per-loop YAML.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py:379-383` — `loop_complete` event
  renderer must extend to surface `total_cost_usd` (and
  `cost_unknown_model`) for richer `ll-loop info` displays
- `scripts/little_loops/cli/loop/_helpers.py:1740-1796` — `_print_ab_summary()`
  is a downstream consumer of cost verdict data; review for `--max-cost`
  / cost-limit awareness (read-only consumer unless verdict logic changes)
- `scripts/little_loops/cli/loop/lifecycle.py:503-504` — resume path applies
  `no_host_guard` mirror at `:503-504`; add the `max_cost` override
  alongside
- `scripts/little_loops/fsm/persistence.py:637-655` —
  `PersistentExecutor._handle_event` writes `usage.jsonl`; F2 reads via
  the existing journal, no schema break (but verifies `cost_unknown_model`
  flag carries through)
- `scripts/little_loops/cli/logs.py:1752, 1769, 1778` —
  `_derive_loop_outcome` / `_parse_terminal_event` parse `loop_complete`
  for `cost_budget_exceeded` / `total_cost_usd` display in `ll-logs`

#### Coordination notes (deferred — out of F2 scope)

- `scripts/little_loops/fsm/runners.py:46-180, 298-318`,
  `scripts/little_loops/issue_manager.py:112, 165, 210-278, 566-614, 917`,
  `scripts/little_loops/parallel/worker_pool.py:712-715, 764-806, 881-894, 979-1044`
  — cross-host `on_usage` callback wiring. F2's `ll-loop` scope excludes
  these paths; cross-host parity (so `--max-cost` doesn't silently
  NO-OP on Codex/OpenCode) is gated on **FEAT-2123**.

#### Similar Patterns (research-confirmed)

- `scripts/little_loops/fsm/host_guard.py` (full file) — canonical precedent;
  `HostGuardConfig` dataclass, `HostGuard.record_subproc_rss()` accumulator,
  `GuardDecision` typed return, `_pending_host_budget_exceeded` flag, and
  `host_budget_exceeded` exit code are the structural twin of F2.
- `scripts/little_loops/fsm/schema.py:281-321` — `ThrottleConfig` cleanest
  precedent for `CostLimitsConfig` shape (`enabled`, `warn_pct`, `on_exceeded`,
  `on_exceeded_state`).
- `scripts/little_loops/stats.py:13-39` — `wilson_ci()` is the greenfield
  template for `ELISForecast.fit() / .predict()` (no scipy).
- `scripts/little_loops/cli_args.py:75-150` — `add_handoff_threshold_arg`,
  `add_context_limit_arg`, `add_max_workers_arg` helpers; if `--max-cost` is
  to be reused across `ll-auto` / `ll-sprint` / `ll-parallel`, add
  `add_max_cost_arg(parser)` here.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_usage_journal.py:17-52` — pre-built `MockActionRunner`
  consumes pre-built `ActionResult(usage_events=[TokenUsage(...)])`
  lists; reuse this drop-in mock for `TestBudgetAccumulator` /
  `TestExecutorCostBudget` rather than the `MockActionRunner` at
  `scripts/tests/test_fsm_executor.py:33-106`, which does not surface
  `usage_events`

#### Tests (research-mapped)

- `scripts/tests/test_fsm_budget.py` (new) — accumulator / guard / ELIS forecast
  tests; **use `scripts/tests/test_host_guard.py:75-89` (`make_prompt_fsm`
  factory) and `:509-573` (`TestExecutorRssBudget` class) as the structural
  template**. Tests must include:
  - `TestBudgetAccumulator` — `add_state_usage` crosses `max_cost_usd` once,
    returns `True` on cross.
  - `TestBudgetGuard` — `check()` returns `OK / WARN / HALT` per threshold.
  - `TestELISForecast` — fit 5 known samples, predict next, error ≤15% on
    synthetic held-out series.
  - `TestExecutorCostBudget` — `test_budget_route`, `test_budget_abort`,
    mirror host-guard equivalents.
- `scripts/tests/test_cli_max_cost.py` (new) — CLI-level: `--max-cost=0.05`
  halts at ceiling ±5%, never exceeds, propagates non-zero exit. Use the
  pattern in `scripts/tests/test_fsm_executor.py:6167` (`test_budget_enforcement_triggers_exhaust`).
- `scripts/tests/test_fsm_validation.py:623-671` (`TestThrottleValidation`) —
  template for `TestBudgetValidation` (rejection-of-negative ceiling, route
  requires declared state).
- `scripts/tests/test_fsm_schema.py:2694-2742` (`TestThrottleConfig`) —
  template for `TestBudgetAccumulatorConfig` round-trip serialization tests.
- **Existing baselines that must not regress**: `scripts/tests/test_pricing.py`
  (TestModelPricing / TestEstimateCostUsd) and
  `scripts/tests/test_usage_reporter.py` (TestPrintUsageSummary).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_args.py:401-440` — add `TestAddMaxCostArg` mirroring
  `TestAddHandoffThresholdArg`; default `None`, accepts `float`, rejects
  non-numeric with `SystemExit`
- `scripts/tests/test_transport.py:707-720` — extend
  `test_end_to_end_span_hierarchy` to assert `total_cost_usd` (and
  `cost_unknown_model`) surface as OTel span attributes on `loop_complete`
  when present
- `scripts/tests/test_generate_schemas.py:41, 162-168` — extend for the
  new `cost_budget_warn` / `cost_budget_exceeded` event entries and the
  `total_cost_usd` / `cost_unknown_model` `loop_complete` payload fields
- `scripts/tests/test_ll_loop_parsing.py:360-381` — add resume subparser
  registration test mirroring `test_handoff_threshold_registered_on_real_resume_parser`
- `scripts/tests/test_loop_cli_defaults.py:130-206` — extend
  `TestLoopRunDefaultsDataclass` to cover `cost_limits.*` backfill from
  `.ll/ll-config.json` into `args.max_cost` when the CLI flag is absent

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The 9 procedural steps above are correct but lack the concrete file-anchor
pinning an implementer needs to act without grepping. Replace the implicit
"add BudgetAccumulator wiring" with these anchor-pinned edits:

1. **Author `scripts/little_loops/fsm/budget.py`** with `BudgetAccumulator`
   (mirrors `fsm/host_guard.py:392-417`), `BudgetGuard` (mirrors
   `_validate_host_guard` shape at `validation.py:2051-2176`), `ELISForecast`
   (mirrors `stats.py:13-39` shape).
2. **Schema field** — `scripts/little_loops/fsm/schema.py:1018-1020`:
   ```python
   budget_accumulator: BudgetAccumulatorConfig = field(default_factory=BudgetAccumulatorConfig)
   ```
   Wire `to_dict()` / `from_dict()` round-trip near the `host_guard` block.
3. **CLI flag** — `scripts/little_loops/cli/loop/__init__.py:156-165` (immediately
   after `--host-guard-budget-mb`). Use `type=float, default=None, metavar="USD"`
   plus a validator: `if args.max_cost is not None and args.max_cost <= 0`.
4. **`cmd_run` override** — `scripts/little_loops/cli/loop/run.py:133-134`
   (mirroring `host_guard_budget_mb` line 133-134):
   ```python
   if getattr(args, "max_cost", None) is not None:
       fsm.budget_accumulator.max_cost_usd = args.max_cost
   ```
5. **Background re-exec forwarding** — `scripts/little_loops/cli/loop/_helpers.py:1313-1379`
   (after `max_iter` at `:1319`); without this, detached `ll-loop run` invocations
   silently drop the flag.
6. **Resume subparser registration** — `scripts/little_loops/cli/loop/lifecycle.py:280, 464-465`
   (mirroring `add_handoff_threshold_arg` / `add_context_limit_arg`).
7. **Executor wiring**:
   - `scripts/little_loops/fsm/executor.py:282-294` (`__init__`):
     ```python
     self._budget: BudgetAccumulator | None = (
         BudgetAccumulator(fsm.budget_accumulator) if fsm.budget_accumulator is not None else None
     )
     self._pending_cost_budget_warn: bool = False
     self._pending_cost_budget_exceeded: bool = False
     ```
   - `scripts/little_loops/fsm/executor.py:1395-1414` (immediately after the
     RSS budget block) — add the parallel `add_state_usage` / `cost_budget_warn`
     / `cost_budget_exceeded` emit block.
   - `scripts/little_loops/fsm/executor.py:582-609` (between stall-detector
     and host-budget blocks) — handle `_pending_cost_budget_exceeded`.
8. **Exit code table** — `scripts/little_loops/cli/loop/_helpers.py:30-38`:
   add `"cost_budget_exceeded": 1` to `EXIT_CODES`.
9. **Validation** — `scripts/little_loops/fsm/validation.py:1038-1060`
   (`validate_fsm()` dispatcher) — append `errors.extend(_validate_cost_limits(fsm, defined_states))`;
   new function near `:2051-2176` (template) plus `KNOWN_TOP_LEVEL_KEYS`
   whitelist at `:174-200`.
10. **JSON schema** — `scripts/little_loops/fsm/fsm-loop-schema.json:274-318`
    mirror the `host_guard` block; auto-regenerate via `ll-generate-schemas`.
11. **Event schemas** — `scripts/little_loops/generate_schemas.py:196+`
    add `cost_budget_warn` and `cost_budget_exceeded` schema entries next to
    the `stall_detected` entry.
12. **ELIS one-line forecast** — `scripts/little_loops/cli/loop/_helpers.py:1605-1616`
    (alongside the existing `print(f"{completion_prefix}: ...")` line) print:
    ```
    ELIS forecast: predicted ${p:.4f} | measured ${m:.4f} | err={(m-p)/m*100:+.1f}%
    ```
13. **OTel span attribute** — `scripts/little_loops/transport.py:462-477`
    surface `total_cost_usd` / `cost_unknown_model` from `loop_complete` payload.
14. **Tests** — add `scripts/tests/test_fsm_budget.py` and
    `scripts/tests/test_cli_max_cost.py`; mirror `scripts/tests/test_host_guard.py:75-89`
    factories and `:509-573` `TestExecutorRssBudget` class shape; ensure
    `python -m pytest scripts/tests/` exits 0.
15. **Docs** — `docs/reference/CLI.md:14, 545-590` (`--max-cost` flag entry
    + ELIS forecast format), `docs/reference/CONFIGURATION.md` (`cost_limits`
    config table), `docs/reference/API.md:62` (`fsm.budget` module entry),
    `docs/ARCHITECTURE.md` ("Token cost layer" subsection).

#### Codebase Research Findings (refine pass 2026-07-05) — anchor corrections

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 6 anchor is wrong-file, not just drifted**: the resume-subparser
  registration for `--max-cost` (mirroring `add_handoff_threshold_arg` /
  `add_context_limit_arg`) lives in **`scripts/little_loops/cli/loop/__init__.py:280,
  464`**, not `scripts/little_loops/cli/loop/lifecycle.py`. `lifecycle.py`
  only contains `cmd_resume`'s *runtime* handoff-threshold env logic
  (lines 507-513) — no subparser/argparse registration. This same wrong-file
  reference also appears in this issue's Acceptance Criteria ("Resume
  parity") and Related Key Documentation table rows — all three should read
  `cli/loop/__init__.py`, not `lifecycle.py`, for the registration anchor.
  `lifecycle.py:503-504` (the `no_host_guard` override mirror) remains a
  correct anchor for the *runtime* `max_cost` override alongside resume.
- **Step 9 anchor drifted**: `validate_fsm()` itself starts at **line 980**
  in `scripts/little_loops/fsm/validation.py`, not 1038. Lines 1038-1060 is
  inside the per-state validation loop body, not the function signature —
  find the dispatcher's existing `_validate_host_guard(...)` call site
  (search within the function body, not at the literal 1038-1060 offset)
  and append `_validate_cost_limits(...)` alongside it.
- **Minor drift, no action needed**: `KNOWN_TOP_LEVEL_KEYS` frozenset closes
  at line ~218-219, not 200 (opening line 174 is still correct); the
  `run_foreground()` completion-print block is lines 1601-1618, not
  1605-1616. Both still land in the same functions/blocks described.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by the wiring research and must be
included alongside the implementation steps above. They are net-new
surfaces uncovered by Agent 1 (Callers), Agent 2 (Side-Effects), and
Agent 3 (Test Gaps) — not duplicates of the research-pinned steps 1-15._

16. **`scripts/little_loops/config/features.py:611-654`** — author
    `CostLimitsConfig` dataclass with `max_cost_per_run`, `warn_at`,
    `cost_unknown_model_fallback`. `to_dict()` / `from_dict()`
    skip-if-default mirror `LoopRunDefaults` precedent at `:611-632`.
    Without this, `BRConfig.load()` cannot round-trip `cost_limits.*`
    and `ll-loop` reads `None` for `--max-cost` defaults.
17. **`scripts/little_loops/config/__init__.py:76-128`** — add
    `CostLimitsConfig` to `__all__` next to `LoopRunDefaults`.
18. **`scripts/little_loops/init/core.py:96-100, 184-193`** — add
    `loop_max_cost_default` choice (mirror `loop_clear_default:184`)
    so `ll-init --yes` and `ll-init --plan` emit `cost_limits.*`
    defaults into `.ll/ll-config.json:91-96`.
19. **`scripts/little_loops/fsm/__init__.py:76-241`** — re-export
    `BudgetAccumulator`, `BudgetGuard`, `ELISForecast`,
    `BudgetAccumulatorConfig`. Otherwise `fsm.budget` symbols are
    reachable only by full path and the module is invisible to
    `from little_loops.fsm import …` consumers.
20. **`docs/reference/schemas/loop_complete.json`** — extend schema
    for `loop_complete` event with `total_cost_usd` (number, ≥0) and
    `cost_unknown_model` (boolean). Required for OTel transport and
    `ll-logs` consumers to read the new payload keys.
21. **Tests — net-new files referenced by Agent 3**:
    - `scripts/tests/test_cli_args.py:401-440` — `TestAddMaxCostArg`
      mirroring `TestAddHandoffThresholdArg`
    - `scripts/tests/test_transport.py:707-720` —
      `test_end_to_end_span_hierarchy` extended to assert OTel span
      attribute surfacing of `total_cost_usd` / `cost_unknown_model`
    - `scripts/tests/test_generate_schemas.py:41, 162-168` — schema
      extension for new event entries and `loop_complete` payload fields
    - `scripts/tests/test_ll_loop_parsing.py:360-381` — resume subparser
      registration test for `--max-cost`
    - `scripts/tests/test_loop_cli_defaults.py:130-206` — config-default
      backfill of `cost_limits.max_cost_per_run` into `args.max_cost`
      when the CLI flag is absent
22. **Documentation — net-new files referenced by Agent 2**:
    - `docs/reference/EVENT-SCHEMA.md:579-638, 953, 1057, 1100`
      (`loop_complete` schema prose for new payload fields)
    - `docs/reference/HOST_COMPATIBILITY.md:132` (cross-host caveat;
      gates cross-host `--max-cost` on FEAT-2123)
    - `docs/reference/API.md:4335, 5346-5405, 4924-4925` (`fsm.budget`
      module reference; mirror `fsm.host_guard` template at those lines)
    - `docs/guides/LOOPS_GUIDE.md:149-191` (`budget_accumulator:` block;
      mirror `host_guard:` template at those lines)
    - `docs/reference/CONFIGURATION.md:393-396` (`cost_limits.*`
      sub-table; parallel to `rate_limits.*` table at those lines)
23. **Awareness — out-of-F2-scope, deferred to FEAT-2123 / ENH-2461**:
    `fsm/runners.py:46-180, 298-318`,
    `issue_manager.py:112, 165, 210-278, 566-614, 917`,
    `parallel/worker_pool.py:712-715, 764-806, 881-894, 979-1044`
    carry the cross-host `on_usage` callback path that supplies
    `usage_events` to F2. While `ll-loop` scope excludes them, F2 may
    emit `cost: n/a (unknown model)` on hosts lacking this plumbing
    until FEAT-2123 lands.
24. **Awareness — adjacent consumer, no F2 changes**:
    `cli/loop/info.py:379-383` (`loop_complete` event renderer) and
    `cli/loop/_helpers.py:1740-1796` (`_print_ab_summary` cost
    verdict) may want to surface `total_cost_usd` for richer displays;
    F2 itself only emits the data and does not modify these renderers.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The issue's 5 acceptance criteria are necessary but incomplete. Add the
following observability, validation, and cross-CLI acceptance criteria
discovered during research:

- **Exit code**: `ll-loop run --max-cost=0.01` exits with code `1` and emits
  `terminated_by: "cost_budget_exceeded"` on the loop_complete event (requires
  `EXIT_CODES` entry in `cli/loop/_helpers.py:30-38`).
- **`--max-cost` forwarding in detached runs**: `ll-loop run --max-cost=1.00 --detach`
  followed by `ll-loop resume` preserves the ceiling; absence is silently dropped
  if `_helpers.py:1313-1379` isn't updated.
- **Resume parity**: `ll-loop resume --max-cost=...` accepts the same flag
  (registration at `cli/loop/__init__.py:280, 464` — corrected from
  `lifecycle.py`, which has no subparser registration; runtime override
  application is at `cli/loop/lifecycle.py:503-504`).
- **JSON schema round-trip**: loop YAMLs declaring `budget_accumulator:` pass
  `ll-loop validate`; `validate_fsm()` (defined at `fsm/validation.py:980`)
  warns when `max_cost_usd < 0` or `warn_at ∉ [0, 1]`.
- **OTel attribute**: on completion, `OTelTransport` surfaces
  `total_cost_usd` (rounded to 4 dp) as a span attribute when present
  (`transport.py:462-477`).
- **Cross-host parity (deferred)**: on hosts where `result.usage_events` is
  empty (Codex / OpenCode without FEAT-2123 surfaced usage), `--max-cost` is
  a NO-OP and emits a one-time warning event; no hard-stop. Gates on FEAT-2123.
- **Unknown-model fallback**: when `estimate_cost_usd()` returns `None`,
  the ELIS forecast line prints `cost: n/a (unknown model)` and the guard
  is permissive (does not HALT on unknown-cost rows). Mirrors existing
  `_print_usage_summary` `has_unknown_model` semantics.
- **No-regression baselines**: `scripts/tests/test_pricing.py` and
  `scripts/tests/test_usage_reporter.py` continue to pass unmodified.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The table above cites the wrong anchor for `executor.py` and is missing the
configuration / docs / JSON schema dependencies the implementation actually
needs. Add these rows (corrected and additional):

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/fsm/executor.py:1382-1392` | Corrected anchor — actual per-action `TokenUsage` aggregation; F2 wires `BudgetAccumulator.add()` immediately after |
| `scripts/little_loops/fsm/executor.py:1395-1414` | RSS-budget wiring — structural twin for `BudgetAccumulator` |
| `scripts/little_loops/fsm/executor.py:282-294` | `FSMExecutor.__init__` — `self._budget` / `_pending_cost_budget_exceeded` field setup |
| `scripts/little_loops/fsm/executor.py:582-609` | Post-state-execution check sequence — handles `_pending_cost_budget_exceeded` (mirror host-budget) |
| `scripts/little_loops/fsm/host_guard.py` | Canonical precedent — `HostGuardConfig`, `record_subproc_rss`, `_pending_host_budget_exceeded` |
| `scripts/little_loops/fsm/validation.py:174-200` | `KNOWN_TOP_LEVEL_KEYS` — whitelist `cost_limits` / `budget_accumulator` |
| `scripts/little_loops/fsm/validation.py:1038-1060` | `validate_fsm()` dispatcher — append `_validate_cost_limits(...)` |
| `scripts/little_loops/fsm/validation.py:2051-2176` | `_validate_host_guard` — template for `_validate_cost_limits` |
| `scripts/little_loops/fsm/fsm-loop-schema.json:274-318` | JSON Schema mirror — `host_guard` block shape for `budget_accumulator` |
| `scripts/little_loops/fsm/schema.py:281-321` | `ThrottleConfig` — cleanest precedent for `BudgetAccumulatorConfig` shape |
| `scripts/little_loops/fsm/schema.py:1018-1020` | `host_guard` field on `FSMLoop` — insert `budget_accumulator` here |
| `scripts/little_loops/cli/loop/__init__.py:122-303` | `run_parser` — add `--max-cost` after `--host-guard-budget-mb:156-165` |
| `scripts/little_loops/cli/loop/run.py:122-164` | CLI override application — add `max_cost` mirror at `:133-134` |
| `scripts/little_loops/cli/loop/_helpers.py:30-38` | `EXIT_CODES` — add `"cost_budget_exceeded": 1` |
| `scripts/little_loops/cli/loop/_helpers.py:1313-1379` | `run_background` re-exec — forward `--max-cost` (mirror `max_iter:1319`) |
| `scripts/little_loops/cli/loop/_helpers.py:1601-1618` | `run_foreground` completion — print ELIS forecast line (corrected from 1605-1616) |
| `scripts/little_loops/cli/loop/__init__.py:280, 464` | Resume subparser — register `--max-cost` (corrected: not `lifecycle.py`, which has no subparser registration) |
| `scripts/little_loops/cli/loop/lifecycle.py:503-504` | Resume path — apply `max_cost` runtime override alongside `no_host_guard` mirror |
| `scripts/little_loops/cli/loop/_helpers.py:1652-1714` | `_print_usage_summary` — read-only consumer (no changes) |
| `scripts/little_loops/transport.py:462-477` | `_handle_loop_complete` — surface `total_cost_usd` OTel attribute |
| `scripts/little_loops/fsm/types.py:24-27` | `ExecutionResult.terminated_by` — extend docstring with `"cost_budget_exceeded"` |
| `scripts/little_loops/subprocess_utils.py:44-56` | `TokenUsage` dataclass — data source for `BudgetAccumulator.add()` |
| `scripts/little_loops/stats.py:13-39` | `wilson_ci()` — greenfield template for `ELISForecast` |
| `scripts/little_loops/generate_schemas.py:196+` | `stall_detected` event schema — template for `cost_budget_warn` / `cost_budget_exceeded` |
| `scripts/little_loops/cli_args.py:75-150` | `add_max_workers_arg` / `add_handoff_threshold_arg` — if `--max-cost` becomes shared, add `add_max_cost_arg()` |
| `scripts/tests/test_host_guard.py:75-89` | `make_prompt_fsm()` factory — template for budget tests |
| `scripts/tests/test_host_guard.py:509-573` | `TestExecutorRssBudget` — template for `TestExecutorCostBudget` |
| `scripts/tests/test_fsm_schema.py:2694-2742` | `TestThrottleConfig` — template for `TestBudgetAccumulatorConfig` round-trip |
| `scripts/tests/test_fsm_validation.py:623-671` | `TestThrottleValidation` — template for `TestBudgetValidation` |
| `docs/reference/CLI.md:14, 545-590` | Public CLI reference — register `--max-cost` flag + ELIS forecast line |
| `docs/reference/CONFIGURATION.md` | Configuration reference — add `cost_limits.*` table |
| `docs/reference/API.md:62` | Python module reference — add `little_loops.fsm.budget` |
| `docs/reference/loops.md` | Loop YAML reference — `budget_accumulator` block |
| `docs/ARCHITECTURE.md` | Architecture — "Token cost layer" subsection (EPIC-2456 central doc pass) |
| `.ll/ll-config.json:91-96` | `loops.run_defaults` — site to add `cost_limits` config block (Tier 1) |
| `config-schema.json` | JSON Schema — must add `cost_limits` keys before runtime config is honored |

## Impact

- **Priority**: P2 — high-leverage; first-clamp primitive for runaway cost
- **Effort**: Medium — ~160 LOC across budget module + flag + executor wiring + tests
- **Risk**: Low — additive; guard defaults to `unlimited`; existing runs unchanged
- **Breaking Change**: No — flag is opt-in; default behavior unchanged

## Status

**Open** | Created: 2026-07-04 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-07-05T05:28:38 - `0dd2f4a0-5634-48f9-b6d1-6c46f2d01c58.jsonl`
- `/ll:decide-issue` - 2026-07-05T05:19:14 - `24fd5b80-284c-4979-a68e-8175dca88a5f.jsonl`
- `/ll:wire-issue` - 2026-07-05T05:03:44 - `e2c32cf7-41b3-4238-8159-397c566f5606.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:53:57 - `8c12fca6-38f6-4c73-9351-ad9e1a4928e3.jsonl`

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
