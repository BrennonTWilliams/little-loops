---
id: FEAT-2550
title: "F2c \u2014 executor wiring + loop_complete payload + OTel transport + CostLimitsConfig\
  \ config layer + init/core.py defaults + docs + tests"
type: FEAT
priority: P2
status: cancelled
captured_at: '2026-07-08T00:00:00Z'
discovered_date: 2026-07-08
discovered_by: split-from-FEAT-2476
parent: FEAT-2476
relates_to:
- EPIC-2456
- FEAT-2548
- FEAT-2549
- ENH-2475
- ENH-2477
- FEAT-2478
- ENH-2461
- FEAT-2123
labels:
- token-cost
- budget
- fsm
- cli
- transport
- docs
- tier-1
decision_needed: false
learning_tests_required:
- opentelemetry
---

# FEAT-2550: F2c — executor wiring + loop_complete payload + OTel transport + config layer + docs + tests

> **Split from FEAT-2476** (split 2026-07-08). F2c is the *integration
> layer* — the final step that wires F2a's primitive and F2b's CLI
> flag into the executor end-to-end, plus the config layer, OTel
> transport, event schemas, docs, and the executor-wiring tests.
> **Depends on FEAT-2548** (primitive) and **FEAT-2549** (CLI flag).
> This is the largest of the three children (~18 files) but the
> highest-leverage: it closes the feature.

## Use Case

As an operator running `ll-loop run --max-cost=...`, I want the F2
cost ceiling to actually halt the run at the configured threshold
(±5%), emit a typed non-zero exit code
(`EXIT_CODES["cost_budget_exceeded"] == 1`), surface the result as
OTel span attributes on the `loop_complete` span, and have `ll-init`
emit `cost_limits.*` defaults so the feature is on by default. The
ELIS one-line forecast should print on completion, and `ll-logs`
should display `cost_budget_exceeded` terminations distinctly from
`host_budget_exceeded`. This child is the integration step that
closes the F2 feature end-to-end.

## Summary

Wire `BudgetAccumulator.add(usage)` and `BudgetGuard.check(total)`
into `fsm/executor.py` post-state; handle the
`_pending_cost_budget_exceeded` flag alongside the existing
`_pending_host_budget_exceeded` mirror; extend `loop_complete`
payload with `total_cost_usd` and `cost_unknown_model`; surface
those as OTel span attributes via `_handle_loop_complete`; author
`CostLimitsConfig` (mirrors `LoopRunDefaults`); wire
`ll-init --yes` / `ll-init --plan` to emit `cost_limits.*`
defaults; update event schemas (`cost_budget_warn`,
`cost_budget_exceeded`); update docs (CLI, CONFIGURATION, API,
ARCHITECTURE, LOOPS_GUIDE, EVENT-SCHEMA, HOST_COMPATIBILITY,
schemas/loop_complete.json); add executor-wiring tests.

## Motivation

Without F2c, F2a's primitive and F2b's CLI flag are unwired — no
runtime enforcement, no OTel observation, no `ll-init` defaults,
no docs. F2c is where the feature actually becomes real for users.
Splitting it from F2a/F2b means the F2c PR can be reviewed
independently of the primitive and the CLI surface, and rollouts
of the new exit code / OTel attribute can be staged separately
if needed.

## Current Behavior

- `scripts/little_loops/fsm/executor.py:282-294` — `__init__`
  has `_pending_host_budget_exceeded`; F2c adds
  `_pending_cost_budget_exceeded` alongside.
- `scripts/little_loops/fsm/executor.py:1395-1414` — RSS-budget
  wiring; F2c adds the parallel cost-budget block.
- `scripts/little_loops/fsm/executor.py:582-609` — post-state
  check sequence (host-budget then stall-detector); F2c inserts
  cost-budget between them.
- `scripts/little_loops/fsm/executor.py:2239-2248` — `_finish()`
  payload; F2c extends with `total_cost_usd` /
  `cost_unknown_model`.
- `scripts/little_loops/transport.py:462-477` —
  `_handle_loop_complete`; F2c surfaces OTel span attributes.
- `scripts/little_loops/config/features.py:611-654` —
  `LoopRunDefaults` round-trip; F2c adds `CostLimitsConfig`.
- `scripts/little_loops/init/core.py:96-100, 184-193` —
  `loop_clear_default` / `loop_show_diagrams_default`; F2c adds
  `loop_max_cost_default`.
- `scripts/little_loops/cli/loop/_helpers.py:1601-1618` —
  `run_foreground` completion print; F2c adds the ELIS forecast
  line alongside.
- `scripts/little_loops/cli/loop/info.py:379-383` — `loop_complete`
  renderer; F2c surfaces `total_cost_usd` for richer display.
- `scripts/little_loops/cli/logs.py:1752, 1769, 1778` —
  `_derive_loop_outcome` / `_parse_terminal_event`; F2c parses
  `cost_budget_exceeded` for `ll-logs` display.
- `scripts/little_loops/fsm/types.py:24-27` —
  `ExecutionResult.terminated_by` docstring; F2c adds
  `"cost_budget_exceeded"`.
- `scripts/little_loops/generate_schemas.py:196+` — `stall_detected`
  event schema; F2c adds `cost_budget_warn` /
  `cost_budget_exceeded` entries.

## Expected Behavior

- `ll-loop run --max-cost=0.05` halts at the configured ceiling
  ±5% on representative workloads and **never** exceeds it.
- At 80% of the ceiling the run emits a soft warning
  (continues). At 100% it emits a hard-stop and exits with
  code 1 (`EXIT_CODES["cost_budget_exceeded"]`).
- On completion, the run prints an ELIS one-line regression
  forecast: `ELIS forecast: predicted $X.XXXX | measured
  $Y.YYYY | err=+N.N%`.
- `loop_complete` event payload includes `total_cost_usd` (float,
  ≥0, rounded 4dp) and `cost_unknown_model` (boolean).
- OTel `loop_complete` span attributes surface `total_cost_usd`
  and `cost_unknown_model` when present.
- `cost_limits.max_cost_per_run` and `cost_limits.warn_at` are
  honored when `--max-cost` is absent (backfill from
  `.ll/ll-config.json`).
- `ll-init --yes` / `ll-init --plan` emit `cost_limits.*`
  defaults into `.ll/ll-config.json:91-96`.
- `ll-logs` displays `cost_budget_exceeded` terminations
  distinctly from `host_budget_exceeded`.

## Proposed Solution

### Executor wiring (4 sites in `fsm/executor.py`)

1. **`__init__` (`:282-294`)** — add:
   ```python
   self._budget: BudgetAccumulator | None = (
       BudgetAccumulator(fsm.budget_accumulator)
       if fsm.budget_accumulator is not None
       else None
   )
   self._pending_cost_budget_warn: bool = False
   self._pending_cost_budget_exceeded: bool = False
   ```

2. **Post-state accumulator + guard emit (`:1395-1414`)** —
   immediately after the RSS-budget block, add the parallel
   `add_state_usage` / `cost_budget_warn` / `cost_budget_exceeded`
   emit block. Use the `_run_action()` token-usage aggregation at
   `:1365` / `:1382-1392` as the data source.

3. **Post-state-execution check (`:582-609`)** — handle
   `_pending_cost_budget_exceeded` between the existing
   `_pending_host_budget_exceeded` (`:632-633`) and
   stall-detector blocks.

4. **`_finish()` payload (`:2239-2248`)** — extend with
   `total_cost_usd` (rounded 4dp) and `cost_unknown_model`
   keys.

### Type / event schema (3 sites)

5. **`fsm/types.py:24-27`** — `ExecutionResult.terminated_by`
   docstring add `"cost_budget_exceeded"`.

6. **`generate_schemas.py:196+`** — add `cost_budget_warn` and
   `cost_budget_exceeded` schema entries next to
   `stall_detected`.

7. **`docs/reference/schemas/loop_complete.json`** — extend
   schema with `total_cost_usd` (number, ≥0) and
   `cost_unknown_model` (boolean) payload fields.

### OTel transport (1 site)

8. **`transport.py:462-477`** — `_handle_loop_complete()`
   surfaces `total_cost_usd` (rounded 4dp) and
   `cost_unknown_model` as OTel span attributes when present.

### Config layer (3 sites)

9. **`config/features.py:611-654`** — author
   `CostLimitsConfig` dataclass with `max_cost_per_run: float =
   0.0`, `warn_at: float = 0.8`,
   `cost_unknown_model_fallback: str = "permissive"`.
   `to_dict()` / `from_dict()` skip-if-default mirror
   `LoopRunDefaults:611-632`.

10. **`config/__init__.py:76-128`** — add `CostLimitsConfig` to
    `__all__` next to `LoopRunDefaults`.

11. **`init/core.py:96-100, 184-193`** — add
    `loop_max_cost_default` choice (mirror
    `loop_clear_default:184` / `loop_show_diagrams_default:186`)
    so `ll-init --yes` / `ll-init --plan` emit `cost_limits.*`
    defaults into `.ll/ll-config.json:91-96`.

### CLI completion / display (3 sites)

12. **`cli/loop/_helpers.py:1601-1618`** — `run_foreground()`
    completion block prints the ELIS forecast line alongside
    the existing per-state cost table.

13. **`cli/loop/info.py:379-383`** — `loop_complete` renderer
    surfaces `total_cost_usd` (and `cost_unknown_model`) for
    richer `ll-loop info` displays.

14. **`cli/logs.py:1752, 1769, 1778`** —
    `_derive_loop_outcome` / `_parse_terminal_event` parse
    `cost_budget_exceeded` and `total_cost_usd` for `ll-logs`
    display.

### Documentation (8 sites)

15. `docs/reference/CLI.md:14, 545-590` — register `--max-cost`
    in the `Common Flags` table and `ll-loop run` section;
    document the ELIS forecast format.

16. `docs/reference/CONFIGURATION.md:393-396` — add a
    `cost_limits` config table documenting `max_cost_per_run`
    and `warn_at` keys (parallel to existing `rate_limits.*`
    table).

17. `docs/reference/API.md:62` — add `little_loops.fsm.budget`
    to the `little_loops.fsm` Module Overview table.

18. `docs/reference/API.md:4335, 5346-5405, 4924-4925` — author
    `little_loops.fsm.budget` Python module reference (mirror
    existing `little_loops.fsm.host_guard` template at those
    lines).

19. `docs/reference/EVENT-SCHEMA.md:579-638, 953, 1057, 1100` —
    extend `loop_complete` event schema prose with
    `total_cost_usd` and `cost_unknown_model` keys.

20. `docs/reference/HOST_COMPATIBILITY.md:132` — note
    `opencode` / `codex` usage-event caveat (gates cross-host
    `--max-cost` parity on FEAT-2123).

21. `docs/guides/LOOPS_GUIDE.md:149-191` — author
    `budget_accumulator:` block docs (mirror `host_guard:`
    block template at those lines).

22. `docs/ARCHITECTURE.md` — add a "Token cost layer" subsection
    documenting the BudgetAccumulator / BudgetGuard /
    ELISForecast primitives (the EPIC-2456 central doc pass
    owns this).

### Tests (4 sites)

23. `scripts/tests/test_transport.py:707-720` — extend
    `test_end_to_end_span_hierarchy` to assert
    `total_cost_usd` (and `cost_unknown_model`) surface as OTel
    span attributes on `loop_complete` when present.

24. `scripts/tests/test_generate_schemas.py:41, 162-168` —
    extend for the new `cost_budget_warn` /
    `cost_budget_exceeded` event entries and the
    `total_cost_usd` / `cost_unknown_model` `loop_complete`
    payload fields.

25. `scripts/tests/test_loop_cli_defaults.py:130-206` — extend
    `TestLoopRunDefaultsDataclass` to cover `cost_limits.*`
    backfill from `.ll/ll-config.json` into `args.max_cost`
    when the CLI flag is absent.

26. New `scripts/tests/test_fsm_executor.py` test for executor
    cost-budget wiring (mirror `TestExecutorRssBudget` in
    `scripts/tests/test_host_guard.py:509-573`).

## Integration Map

### Files to Modify (code)

- `scripts/little_loops/fsm/executor.py` (4 sites)
- `scripts/little_loops/fsm/types.py`
- `scripts/little_loops/generate_schemas.py`
- `scripts/little_loops/transport.py`
- `scripts/little_loops/config/features.py`
- `scripts/little_loops/config/__init__.py`
- `scripts/little_loops/init/core.py`
- `scripts/little_loops/cli/loop/_helpers.py` (completion block)
- `scripts/little_loops/cli/loop/info.py`
- `scripts/little_loops/cli/logs.py`

### Files to Modify (docs)

- `docs/reference/CLI.md`
- `docs/reference/CONFIGURATION.md`
- `docs/reference/API.md` (3 sites)
- `docs/reference/EVENT-SCHEMA.md`
- `docs/reference/HOST_COMPATIBILITY.md`
- `docs/guides/LOOPS_GUIDE.md`
- `docs/ARCHITECTURE.md`
- `docs/reference/schemas/loop_complete.json`

### Tests

- `scripts/tests/test_transport.py`
- `scripts/tests/test_generate_schemas.py`
- `scripts/tests/test_loop_cli_defaults.py`
- `scripts/tests/test_fsm_executor.py` (extension for
  `TestExecutorCostBudget` mirroring `TestExecutorRssBudget`)

### Dependent Files (read-only consumers, no changes)

- `scripts/little_loops/fsm/persistence.py:637-655` —
  `PersistentExecutor._handle_event` writes `usage.jsonl`;
  F2c reads via the existing journal, no schema break.
- `scripts/little_loops/cli/loop/_helpers.py:1652-1714` —
  `_print_usage_summary()` unchanged (F2c extends the
  completion block, not the per-state table).
- `scripts/little_loops/cli/loop/_helpers.py:1740-1796` —
  `_print_ab_summary()` is a downstream consumer of cost
  verdict data; review for `--max-cost` / cost-limit awareness
  (read-only unless verdict logic changes).

### Out-of-F2c-scope (deferred to FEAT-2123 / ENH-2461)

- `scripts/little_loops/fsm/runners.py:46-180, 298-318`,
  `scripts/little_loops/issue_manager.py:112, 165, 210-278, 566-614, 917`,
  `scripts/little_loops/parallel/worker_pool.py:712-715, 764-806, 881-894, 979-1044`
  — cross-host `on_usage` callback wiring. F2's `ll-loop` scope
  excludes these paths; cross-host parity (so `--max-cost`
  doesn't silently NO-OP on Codex/OpenCode) is gated on
  FEAT-2123.

## Acceptance Criteria

- `ll-loop run --max-cost=1.00` exits at $1.00 ± 5% on
  representative workloads and never exceeds.
- 80% of ceiling emits a soft warning; 100% emits hard-stop
  with typed non-zero exit code 1 and
  `terminated_by: "cost_budget_exceeded"`.
- ELIS forecast line prints on completion; forecast error ≤15%
  on held-out trace sets.
- `cost_limits.max_cost_per_run` is honored when `--max-cost`
  is absent (config backfill).
- `loop_complete` event payload includes `total_cost_usd` and
  `cost_unknown_model`.
- OTel `loop_complete` span attributes include
  `total_cost_usd` (rounded 4dp) and `cost_unknown_model` when
  present.
- `ll-init --yes` / `ll-init --plan` emit `cost_limits.*`
  defaults.
- `ll-logs` displays `cost_budget_exceeded` distinctly.
- `python -m pytest scripts/tests/` exits 0 (no regressions in
  `test_pricing.py`, `test_host_guard.py`, `test_cost_graph.py`,
  `test_transport.py`, `test_generate_schemas.py`,
  `test_loop_cli_defaults.py`).

## Scope Boundaries

- **In**: executor wiring, OTel transport, event schemas,
  `CostLimitsConfig`, `init/core.py` defaults, all docs, all
  tests.
- **Out**: primitive library (F2a / FEAT-2548); CLI surface
  (F2b / FEAT-2549).
- **Out of scope**: cross-host parity (gated on FEAT-2123);
  `history.db` `usage_event` table (gated on ENH-2461);
  `ll-auto` / `ll-sprint` / `ll-parallel` shared
  `--max-cost` flag (only if those surfaces request it).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/fsm/executor.py:282-294` | `__init__` — `_pending_host_budget_exceeded` twin |
| `scripts/little_loops/fsm/executor.py:582-609` | Post-state check sequence anchor |
| `scripts/little_loops/fsm/executor.py:632-633` | `_pending_host_budget_exceeded` handling — twin |
| `scripts/little_loops/fsm/executor.py:1382-1392` | Per-action `TokenUsage` aggregation (F2c data source) |
| `scripts/little_loops/fsm/executor.py:1395-1414` | RSS-budget wiring — twin for F2c accumulator block |
| `scripts/little_loops/fsm/executor.py:2239-2248` | `_finish()` payload — extend with cost fields |
| `scripts/little_loops/fsm/types.py:24-27` | `ExecutionResult.terminated_by` docstring |
| `scripts/little_loops/transport.py:462-477` | `_handle_loop_complete` OTel attribute surfacing |
| `scripts/little_loops/config/features.py:611-654` | `LoopRunDefaults` — mirror for `CostLimitsConfig` |
| `scripts/little_loops/init/core.py:96-100, 184-193` | `loop_clear_default` / `loop_show_diagrams_default` — mirror |
| `scripts/little_loops/cli/loop/_helpers.py:1601-1618` | `run_foreground` completion print anchor |
| `scripts/little_loops/cli/loop/info.py:379-383` | `loop_complete` renderer |
| `scripts/little_loops/cli/logs.py:1752, 1769, 1778` | `_derive_loop_outcome` / `_parse_terminal_event` |
| `scripts/little_loops/generate_schemas.py:196+` | `stall_detected` event schema — mirror |
| `scripts/tests/test_host_guard.py:509-573` | `TestExecutorRssBudget` — template for `TestExecutorCostBudget` |
| `FEAT-2548` | Depends-on: primitive library |
| `FEAT-2549` | Depends-on: CLI flag |
| `FEAT-2476` | Parent umbrella |

## Impact

- **Priority**: P2 — first-clamp primitive for runaway cost.
- **Effort**: Large — ~250 LOC across ~18 files (code +
  tests + docs).
- **Risk**: Low — additive; OTel attribute is best-effort;
  CLI default is `unlimited`; existing runs unchanged.
- **Breaking Change**: No — opt-in flag; new payload fields
  default to absent.

## Status

**Open** | Created: 2026-07-08 | Priority: P2 | Split from FEAT-2476
**Depends on**: FEAT-2548 (primitive), FEAT-2549 (CLI flag)

## Codebase Research Findings

_Added by `/ll:refine-issue` — codebase-verified anchor corrections, dependency status, and pattern references for the implementer._

### Anchor Drift Table (verified 2026-07-08)

Many of the line ranges cited in **Current Behavior** and **Proposed Solution**
have drifted since the issue was drafted (because F2a/F2b work is concurrent
and the executor / `_helpers.py` have been edited). Use the corrected anchors
below; the originals are noted for traceability.

| Issue anchor | What it points to | Current actual location | Notes |
|---|---|---|---|
| `executor.py:282-294` | `__init__` host-budget block | `executor.py:300-314` | `__init__` itself is defined at line 159; the host-budget flag block sits at 300-314 |
| `executor.py:1395-1414` | RSS-budget wiring | `executor.py:1476-1495` | Lines 1395-1414 currently hold the `prompt_size_guard` block (unrelated). RSS-record emit lives at 1476-1495 |
| `executor.py:2239-2248` | `_finish()` payload | `executor.py:2320-2360` | 2239-2248 is inside the `_sleep_with_heartbeat` docstring (unrelated). `_finish()` is at 2320-2360 with payload at 2322-2329 |
| `executor.py:1365` / `:1382-1392` | `_run_action` / TokenUsage aggregation | `executor.py:1462-1474` | `_run_action` def is at 1365 (matches); the per-action usage aggregation is at 1462-1474, not 1382-1392 (that's the prompt-size guard body) |
| `executor.py:582-609` | Post-state check sequence | `executor.py:582-660` | Block extended past 609 — RSS routing logic lives at 625-659 |
| `types.py:24-27` | `terminated_by` docstring | `types.py:23-30` | Docstring runs 23-30 (extra "host_pressure_abort"/"host_budget_exceeded" lines added) |
| `cli/loop/info.py:379-383` | `loop_complete` renderer | `cli/loop/info.py:518-525` | Lines 379-383 are the loop-list TOTAL printer (unrelated). The `loop_complete` event handler is at line 518 |
| `cli/logs.py:1752, 1769, 1778` | `_derive_loop_outcome` / `_parse_terminal_event` | `cli/logs.py:1751-1770` / `1773-1789` | Close; 1752 lands inside `_derive_loop_outcome` (def at 1751); 1778 is inside `_parse_terminal_event`'s body |
| `_helpers.py:1601-1618` | Completion print block | `_helpers.py:1651-1734` | Lines 1601-1618 are the `_follow_callback` wiring (unrelated). The completion summary is at 1651-1734; ELIS forecast should print just before line 1706 |
| `_helpers.py:1652-1714, 1740-1796` | Downstream consumers | `_helpers.py:1742-1767` / `1770-1851` | `_print_usage_summary` is at 1742-1767; `_print_ab_summary` is at 1770-1851 (not 1740-1796) |
| `api.md:4335` / `4924-4925` / `5346-5405` | `host_guard` Python module reference | `api.md:5603-5650+` | All three cited anchors are unrelated sections (`WORKFLOW_TEMPLATES` at 4335; `RouteConfig` at 4924-4925; `fsm.persistence` at 5356-5405). The `host_guard` module reference sits at ~5603-5650 |
| `fsm/persistence.py:637-655` | `usage.jsonl` journal | `fsm/persistence.py:710-740` | 637-655 is the events.jsonl archive (`shutil.copy2`) block; actual `usage.jsonl` write is at 710-740 inside `_handle_event` |
| `generate_schemas.py:196+` | `stall_detected` schema mirror | `generate_schemas.py:196-208` | `stall_detected` schema sits at 196-208 (anchor is correct); note other events around it: `retry_exhausted` 172, `cycle_detected` 183, `rate_limit_exhausted` 209 |

### F2a Dependency Status (CRITICAL)

**`scripts/little_loops/fsm/budget.py` does not exist yet.** F2a (FEAT-2548)
must land before F2c can be implemented. The planned public API (per the
FEAT-2548 spec) that F2c imports:

```python
from little_loops.fsm.budget import (
    BudgetAccumulator,        # .add(usage: TokenUsage) -> bool  (one-shot latch)
    BudgetAccumulatorConfig,  # max_cost_usd=0.0, warn_at=0.8, cost_unknown_model_fallback="permissive"
    BudgetGuard,              # .check(total: float) -> GuardDecision
    GuardDecision,            # @dataclass action: Literal["ok", "warn", "halt"], total_usd, used_pct, target
    ELISForecast,             # .fit(state_history: list[float]) -> self; .predict(steps_ahead: int) -> float
)
```

**TokenUsage** dataclass (input to `BudgetAccumulator.add`) lives at
`scripts/little_loops/subprocess_utils.py:45` with fields
`input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, model`.

**ELIS forecast pattern** (B1 template) — the existing `statistics.linear_regression` consumer is `_calculate_trend()` at
`scripts/little_loops/issue_history/summary.py:171-196`. F2a's `ELISForecast.predict()` uses **both** `.slope` AND `.intercept` (returns `intercept + slope * (n - 1 + steps_ahead)`), unlike `_calculate_trend()` which consumes only `.slope`.

**F2a field anchor on `FSMLoop`**: per FEAT-2548, `budget_accumulator: BudgetAccumulatorConfig = field(default_factory=BudgetAccumulatorConfig)` slots in next to the existing `host_guard: HostGuardConfig` field at `scripts/little_loops/fsm/schema.py:1115`.

### Pattern Mirrors Already in Codebase

| F2c change | Mirror pattern in codebase |
|---|---|
| Skip-if-default `to_dict`/`from_dict` for `CostLimitsConfig` | `HostGuardConfig.to_dict()` at `scripts/little_loops/fsm/host_guard.py:84-107` (NOT `LoopRunDefaults.to_dict()` — that does not exist) |
| One-shot accumulator latch | `HostGuard.record_subproc_rss(label, peak_rss_mb) -> bool` at `host_guard.py:392-417` (returns True exactly once on first cross) |
| `__init__` pending-flag declaration | `executor.py:300-323` (two-flag pattern: `_pending_host_pressure_abort` + `_pending_host_budget_exceeded`) |
| Post-state pending flag consume + route/abort | `executor.py:629-660` (3-action shape: `route:<state>` / `abort` / typed error) |
| Per-action telemetry emit + flag set | `executor.py:1476-1495` (gated on `budget_enabled`; emits `host_subproc_rss` per-action; sets `_pending_host_budget_exceeded` on cross) |
| `GuardDecision` 3-tier discriminator | `host_guard.py:351-390` (`<warn_pct` → "ok"; `>=warn_pct <critical_pct` → "cooldown"; `>=critical_pct` → "route"/"abort"). F2a mirrors with `BudgetGuard.check()` returning "ok"/"warn"/"halt" |
| `--max-cost` argparse | `cli/loop/__init__.py:156-165` (`--host-guard-budget-mb` precedent) |
| `cmd_run` override application | `cli/loop/run.py:132-135` (`host_guard_budget_mb` override pattern) |
| Lifecycle resume override | `cli/loop/lifecycle.py:532-536` (`no_host_guard` / `no_prompt_size_guard` precedent) |
| Event schema generation | `generate_schemas.py:196-208` (`stall_detected` schema with `_schema()` helper at line 57-74) |
| Test fixture | `RssActionRunner` at `scripts/tests/test_host_guard.py:54-72` — F2c needs a `CostActionRunner` returning fixed `usage_events` |
| `TestExecutorRssBudget` test structure | `test_host_guard.py:509-573` (tests: `test_budget_route`, `test_budget_abort`; uses `make_budget_fsm()` factory at 478-506) |
| OTel attribute surfacing | `transport.py:462-477` (`_handle_loop_complete`; `set_status` is current pattern). **Note**: `set_attribute` is NOT currently called anywhere in `transport.py` — F2c introduces it as a new pattern |
| OTel test assertion | `test_transport.py:708-732` (`test_end_to_end_span_hierarchy`; uses `span_by_name` lookup + `exporter.get_finished_spans()`) |
| LoopRunDefaults round-trip test | `test_loop_cli_defaults.py:130-206` (`TestLoopRunDefaultsDataclass`; one test per field; local imports inside test methods) |
| Event schema test | `test_generate_schemas.py:20-65, 150-194` (file-count assertion + per-event payload assertions; F2c bumps count from 39 → 41) |
| Init config emission | `init/core.py:188-198` (uses `schema_default("loops.run_defaults.clear")` to resolve JSON-Schema defaults) |
| Doc module reference template | `docs/reference/API.md:5603-5650` (`little_loops.fsm.host_guard` reference — the actual anchor for F2c's `little_loops.fsm.budget` mirror) |

### Critical Gaps the Implementer Must Close (Beyond the Issue Text)

1. **`EXIT_CODES` dict at `cli/loop/_helpers.py:64-77` does NOT include `host_budget_exceeded` or `cost_budget_exceeded` today.** The current keys are
   `terminal/interrupted/handoff → 0; max_steps/timeout/cycle_detected/stall_detected/user_stopped/system_signal → 1`. F2b/F2c must add `"cost_budget_exceeded": 1` to the dict (the
   `run_foreground` consumer at line 1734 falls back via `EXIT_CODES.get(result.terminated_by, 1)`, so `host_budget_exceeded` already exits 1 implicitly — adding the explicit entry is documentation/discoverability, not new behavior).

2. **`_derive_loop_outcome` at `cli/logs.py:1751-1770` does NOT currently map `host_budget_exceeded` to any outcome bucket** — it falls through to the `final_state` keyword check. **F2c should add BOTH `host_budget_exceeded` AND `cost_budget_exceeded` to the mapping** (a new `"budget-exceeded"` outcome bucket is the cleanest mirror, or reuse `"error"`). This is a parity fix that should land with the `cost_budget_exceeded` addition.

3. **OTel `_handle_loop_complete` reads `event.get("outcome", "")`** at `transport.py:471`, but the executor's `loop_complete` payload today does NOT emit an `"outcome"` key (only `final_state, iterations, terminated_by, error`). This is a thin/dangling read unrelated to F2c, but worth noting because F2c's `total_cost_usd` / `cost_unknown_model` payload fields will be the first non-dangling reads of additional keys via the OTel path.

4. **`_handle_action_complete` at `transport.py:457-460` is currently empty** (just closes the action span) — per-action `input_tokens`, `output_tokens`, etc., are NOT surfaced as OTel span attributes today. They are added as span events via `_add_span_event` (line 484) with string-converted attributes. F2c's `set_attribute` calls on the loop span are the **first use of `set_attribute` in the file** — implementer should add an import if not already imported (`from opentelemetry.trace import StatusCode` is imported at line 463; `set_attribute` is a method on the span object, not a separate import).

5. **Test fixture gap**: `scripts/tests/test_host_guard.py:54-72` defines `RssActionRunner(peak_rss_mb: float)`. F2c needs an analogous `CostActionRunner(usage_events: list[TokenUsage])` fixture in the new `test_fsm_executor.py` file. The `make_prompt_fsm()` factory at `test_host_guard.py:75-89` is the template for an `make_cost_fsm()` factory.

6. **Issue cites `docs/reference/schemas/loop_complete.json` for the `total_cost_usd` / `cost_unknown_model` extension** — verified: file exists at the path. F2c extends the `properties` dict (does NOT add to `required` — both new fields are optional per the existing pattern for token fields).

7. **ENH-2461 / `history.db` `usage_event` table** (cited as out-of-scope in the issue) — F2c does NOT touch the history store. The cost verdict stays event-stream-only; cross-host `on_usage` callback wiring remains deferred to FEAT-2123.

### Cross-References Verified

- **FEAT-2548 (F2a primitive)** — `fsm/budget.py` planned; F2c imports the public API listed above. The F2a field on `FSMLoop` is at `fsm/schema.py:1115` (next to `host_guard`).
- **FEAT-2549 (F2b CLI flag)** — adds `--max-cost` argparse at `cli/loop/__init__.py:156-165` (after `--host-guard-budget-mb`); applies override at `cli/loop/run.py:132-135` and `cli/loop/lifecycle.py:532-536`; adds `EXIT_CODES["cost_budget_exceeded"] = 1` entry.
- **FEAT-2476 (parent umbrella)** — F2c closes the F2 feature end-to-end after F2a/F2b land.
- **EPIC-2456 (token cost reduction)** — central doc pass owns the "Token cost layer" subsection in `docs/ARCHITECTURE.md`; F2c extends `docs/ARCHITECTURE.md` only with the OTel/loop_complete references.
- **ENH-2475 / ENH-2477 / FEAT-2478** — sibling features in the same epic; F2c does NOT depend on these but shares the `cost_unknown_model` semantic.
- **ENH-2461 (history.db usage_event)** — out-of-scope; F2c stays event-stream-only.
- **FEAT-2123 (cross-host `--max-cost` parity)** — out-of-scope; cross-host `on_usage` callback wiring deferred.

## Session Log
- `/ll:refine-issue` - 2026-07-08T21:55:10 - `895df25a-6139-4608-9fa5-31338e190a73.jsonl`
- `/ll:capture-issue` (split) - 2026-07-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d276935-0474-4bff-85e3-154d56cf1226.jsonl`
- `/ll:refine-issue` - 2026-07-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d276935-0474-4bff-85e3-154d56cf1226.jsonl`
