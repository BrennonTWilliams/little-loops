---
id: FEAT-2548
title: "F2a — fsm/budget.py primitive (BudgetAccumulator + BudgetGuard + ELISForecast) + BudgetAccumulatorConfig schema + validation + JSON schema"
type: FEAT
priority: P2
status: open
captured_at: "2026-07-08T00:00:00Z"
discovered_date: 2026-07-08
discovered_by: split-from-FEAT-2476
parent: FEAT-2476
relates_to: [EPIC-2456, FEAT-2549, FEAT-2550, ENH-2475, ENH-2477, FEAT-2478, ENH-2461, FEAT-2123]
labels:
  - token-cost
  - budget
  - fsm
  - tier-1
decision_needed: false
---

# FEAT-2548: F2a — fsm/budget.py primitive + BudgetAccumulatorConfig + validation + JSON schema

> **Split from FEAT-2476** (split 2026-07-08; see FEAT-2476 for umbrella scope,
> motivation, and parent EPIC-2456 context). F2a lands the *primitive layer* —
> the self-contained library plus its config schema, validation, and JSON Schema
> definition. F2b (FEAT-2549) consumes the flag; F2c (FEAT-2550) wires it into
> the executor and config layer. The data-flow dependency is **a → b → c**.

## Summary

Author `scripts/little_loops/fsm/budget.py` (~120 LOC) with three classes
mirroring the structural twin `fsm/host_guard.py`:

- **`BudgetAccumulator`** — accumulates per-state USD cost from
  `pricing.estimate_cost_usd()` into a running total. Mirror of
  `HostGuard.record_subproc_rss()` (returns `True` exactly once on
  crossing `max_cost_usd`).
- **`BudgetGuard`** — typed `GuardDecision` (`OK` / `WARN` / `HALT`)
  based on accumulated spend vs. ceiling and `warn_at` threshold.
- **`ELISForecast`** — one-line weighted least-squares regression
  over per-state cost history; `fit(state_history)` returns
  `(slope, intercept)`; `predict(steps_ahead)` extrapolates.

Plus the `BudgetAccumulatorConfig` dataclass, `KNOWN_TOP_LEVEL_KEYS`
whitelist, `_validate_cost_limits()` validator, JSON Schema mirror,
and `fsm/__init__.py` re-exports.

## Use Case

As an F2 implementor wiring `--max-cost` into `ll-loop`, I need a
self-contained `BudgetAccumulator` / `BudgetGuard` / `ELISForecast`
library plus its `BudgetAccumulatorConfig` dataclass so the executor
and CLI layers (FEAT-2549, FEAT-2550) can consume a typed, validated
cost-ceiling primitive without recreating it from scratch. The
primitive lives under `fsm/` next to its structural twin
`host_guard.py` and is unit-tested in isolation against synthetic
`ActionResult(usage_events=[...])` fixtures before any executor
wiring exists.

## Motivation

The `fsm/host_guard.py` precedent (ENH-2452/ENH-2453) is the
structural twin and lives under `fsm/` — dominant precedent for
where accumulator+guard primitives belong. Splitting the primitive
out as its own issue means F2b and F2c can each land in a focused
PR without dragging the rest of the surface along, and the
primitive can be unit-tested in isolation against synthetic
`ActionResult(usage_events=[TokenUsage(...)])` fixtures before any
executor wiring exists.

## Current Behavior

- `scripts/little_loops/pricing.py:58-78` `estimate_cost_usd()` —
  reusable cost calculator.
- `scripts/little_loops/fsm/cost_graph.py` (ENH-2477, completed) —
  per-state cost aggregation; F2 reads `usage.jsonl` from this
  layer.
- `scripts/little_loops/fsm/host_guard.py` — structural twin:
  `HostGuardConfig`, `HostGuard.record_subproc_rss()` (returns `True`
  once on cross), `GuardDecision` enum.
- `scripts/little_loops/issue_history/summary.py:184` —
  `statistics.linear_regression(range(n), values).slope` — the
  better B1 template for `ELISForecast` (per refine-pass research).
- `scripts/little_loops/stats.py:13-39` `wilson_ci()` — greenfield
  template for dataclass/guard-clause shape (use only for shape, not
  for the regression math).

## Expected Behavior

- `BudgetAccumulator(config).add(usage) -> bool` returns `True`
  exactly once when accumulated cost first crosses
  `config.max_cost_usd`.
- `BudgetGuard.check(acc_total) -> GuardDecision` returns
  `OK | WARN | HALT` based on `total / max_cost_usd` vs.
  `config.warn_at` (default 0.8).
- `ELISForecast.fit(state_history).predict(steps_ahead) -> float`
  projects final cost; ≤15% error on held-out synthetic series.
- `BudgetAccumulatorConfig` round-trips via `to_dict()` /
  `from_dict()` (skip-if-default mirror `HostGuardConfig`).
- `KNOWN_TOP_LEVEL_KEYS` whitelists `"budget_accumulator"` and
  `"cost_limits"` so `validate_fsm()` does not warn "unknown
  top-level key".
- `_validate_cost_limits(fsm, defined_states)` returns
  `ValidationError` list rejecting `max_cost_usd < 0` and
  `warn_at ∉ [0, 1]`.
- `fsm-loop-schema.json` declares the `budget_accumulator:` block
  shape (mirror of `host_guard`).

## Proposed Solution

1. **`scripts/little_loops/fsm/budget.py`** (new, ~120 LOC):
   - `BudgetAccumulatorConfig` dataclass — `enabled: bool = True`,
     `max_cost_usd: float = 0.0` (0 = disabled), `warn_at: float = 0.8`,
     `cost_unknown_model_fallback: str = "permissive"` (one of
     `"permissive"`, `"warn"`, `"halt"`).
   - `BudgetAccumulator(config)` — `add(usage: TokenUsage) -> bool`,
     `total_usd: float`, `cumulative_state_count: int`,
     `cost_unknown_model: bool` properties.
   - `GuardDecision` dataclass — `action: Literal["ok", "warn", "halt"]`,
     `used_pct: float | None`, `total_usd: float | None`,
     `target: str | None = None`.
   - `BudgetGuard(config).check(total: float) -> GuardDecision`.
   - `ELISForecast` — `fit(state_history: list[float]) -> ELISForecast`,
     `predict(steps_ahead: int) -> float`. Uses
     `statistics.linear_regression(range(n), values)` per
     `summary.py:184`.
   - Module-level `__all__` exporting the public surface.

2. **`scripts/little_loops/fsm/schema.py`** — add
   `BudgetAccumulatorConfig` to `FSMLoop` at the top-level field
   (mirror `host_guard: HostGuardConfig = field(default_factory=HostGuardConfig)`
   at `:1115`):
   ```python
   budget_accumulator: BudgetAccumulatorConfig = field(
       default_factory=BudgetAccumulatorConfig
   )
   ```
   Wire `to_dict()` / `from_dict()` round-trip near the `host_guard`
   block (`:1201-1203`, `:1254-1256`).

3. **`scripts/little_loops/fsm/validation.py`**:
   - `KNOWN_TOP_LEVEL_KEYS` (`:175`) — add `"budget_accumulator"` and
     `"cost_limits"`.
   - New `_validate_cost_limits(fsm: FSMLoop, defined_states: set[str]) -> list[ValidationError]`
     near `_validate_host_guard` (`:2158`). Reject `max_cost_usd < 0`
     and `warn_at ∉ [0, 1]`.
   - `validate_fsm()` dispatcher (`:1085`) — append
     `errors.extend(_validate_cost_limits(fsm, defined_states))` near
     the existing `_validate_host_guard(...)` call site.

4. **`scripts/little_loops/fsm/fsm-loop-schema.json`** — mirror the
   `host_guard` block to add a top-level `budget_accumulator:`
   JSON Schema definition. Use `ll-generate-schemas` to
   auto-regenerate from the dataclass for parity with the rest of
   the schema (the manual edit is a fallback).

5. **`scripts/little_loops/fsm/__init__.py`** — re-export
   `BudgetAccumulator`, `BudgetGuard`, `ELISForecast`,
   `BudgetAccumulatorConfig` so `from little_loops.fsm import ...`
   works (otherwise `fsm.budget` symbols are reachable only by
   full path).

### Codebase Research Findings — Twin-Pattern Reinforcement

_Added by `/ll:refine-issue` — concrete anchors from codebase-pattern-finder:_

**Skip-if-default `to_dict` body** (the exact shape to mirror for `BudgetAccumulatorConfig`) — from `scripts/little_loops/fsm/host_guard.py:84-107`:
```python
def to_dict(self) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not self.enabled:
        result["enabled"] = self.enabled
    if self.cooldown_ms != 500:
        result["cooldown_ms"] = self.cooldown_ms
    # ... every field compared against its declared default
    return result
```
Each field is compared to its declared default value; non-default values land in the output dict. Mirror this for `BudgetAccumulatorConfig` (compare `enabled: True`, `max_cost_usd: 0.0`, `warn_at: 0.8`, `cost_unknown_model_fallback: "permissive"` against their declared defaults).

**Skip-if-default `from_dict` body** — from `scripts/little_loops/fsm/host_guard.py:109-123`:
```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> HostGuardConfig:
    return cls(
        enabled=data.get("enabled", True),
        cooldown_ms=data.get("cooldown_ms", 500),
        warn_pct=float(data.get("warn_pct", 75.0)),
        # ...
        max_cumulative_subproc_mb=data.get("max_cumulative_subproc_mb", 0),
        on_budget_exceeded=data.get("on_budget_exceeded", "route"),
        budget_state=data.get("budget_state"),
    )
```
Note `float(...)` casts on percentage fields; apply the same coercion to `warn_at`. Default-constructed `from_dict({})` must equal `cls()`.

**One-shot accumulator latch** — from `scripts/little_loops/fsm/host_guard.py:397-417` (`record_subproc_rss`):
```python
def record_subproc_rss(self, label: str, peak_rss_mb: float) -> bool:
    self.cumulative_subproc_mb += peak_rss_mb
    self.subproc_samples.append((label, peak_rss_mb))
    if (
        self.budget_enabled
        and not self._budget_fired
        and self.cumulative_subproc_mb > self.config.max_cumulative_subproc_mb
    ):
        self._budget_fired = True
        return True
    return False
```
Mirror exactly for `BudgetAccumulator.add(usage: TokenUsage) -> bool`: accumulate cost via `estimate_cost_usd(usage.model, usage.input_tokens, usage.output_tokens, usage.cache_read_tokens, usage.cache_creation_tokens)`, append to `state_history`, check the `_budget_fired` latch, return `True` exactly once on crossing. Pair with a `budget_enabled` `@property` returning `self.config.max_cost_usd > 0` to short-circuit when the ceiling is 0 (the "0 = disabled" convention).

**Two-tier discriminator for `cost_unknown_model`** — `estimate_cost_usd` returns `None` for unknown models. Mirror the `HostGuard` "probe failure → action='ok'" graceful-degrade pattern: when `estimate_cost_usd` returns `None`, set `self.cost_unknown_model = True` and apply `BudgetGuard.check()`'s `cost_unknown_model_fallback` policy (`"permissive"` → no-op, `"warn"` → return `WARN`, `"halt"` → return `HALT`).

**ELISForecast math** — use `statistics.linear_regression(range(n), state_history).slope` AND `.intercept` (the existing summary.py:184 code only consumes `.slope`; `ELISForecast.predict(steps_ahead)` projects at `intercept + slope * (n - 1 + steps_ahead)`). Require `n >= 2` (matching the ENH-698 prohibition on `len(values) < 3` short-circuit only when used as a "stable" classifier; `ELISForecast` should return some sentinel like `0.0` or raise on `n < 2` to match the `_calculate_trend` `len < 3` early-return shape).

**fsm-loop-schema.json mirror** — at `scripts/little_loops/fsm/fsm-loop-schema.json:274-335` (the `host_guard:` block), copy the structure:
```json
"budget_accumulator": {
  "type": "object",
  "description": "Cumulative-USD budget primitive (FEAT-2548). Default-disabled (max_cost_usd=0); set max_cost_usd > 0 to enable.",
  "properties": {
    "enabled": { "type": "boolean", "default": true, ... },
    "max_cost_usd": { "type": "number", "default": 0.0, "minimum": 0, ... },
    "warn_at": { "type": "number", "default": 0.8, "minimum": 0, "maximum": 1, ... },
    "cost_unknown_model_fallback": { "type": "string", "enum": ["permissive", "warn", "halt"], "default": "permissive", ... }
  },
  "additionalProperties": false
}
```
Hand-edit per Research Correction #3 (do NOT invoke `ll-generate-schemas`).

**Tests** — model the new test file after `scripts/tests/test_host_guard.py` rather than the Throttle-cost-ceiling twin. Classes to mirror:
- `TestHostGuardConfig` (test_host_guard.py:104-152) → `TestBudgetAccumulatorConfig` for the four-field dataclass round-trip + FSMLoop-level integration (`test_fsm_loop_roundtrip`, `test_fsm_loop_default_omits_host_guard_key`).
- `TestHostGuardDecisions` (test_host_guard.py:269-338) → `TestBudgetGuard` for `OK/WARN/HALT` action discrimination.
- `TestHostGuardValidation` (test_host_guard.py:599-655) → `TestBudgetValidation` for `_validate_cost_limits` rejecting `max_cost_usd < 0` and `warn_at ∉ [0, 1]`.
- `MockActionRunner` fixture (test_usage_journal.py:17-52) for `TokenUsage` lists in `TestBudgetAccumulator.test_add_state_usage` cases.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/budget.py` (new) — primitive
- `scripts/little_loops/fsm/schema.py` — `BudgetAccumulatorConfig` field
- `scripts/little_loops/fsm/validation.py` — `KNOWN_TOP_LEVEL_KEYS` + `_validate_cost_limits`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema mirror
- `scripts/little_loops/fsm/__init__.py` — re-exports

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified file anchors** (from codebase-locator + codebase-analyzer):

- Twin primitive: `scripts/little_loops/fsm/host_guard.py` — `HostGuardConfig` (line 49-123), `HostGuard` (line 325), `GuardDecision` (line 304-322); `ON_PRESSURE_VALUES = frozenset({"cool_down", "route", "abort"})` and `ON_BUDGET_VALUES = frozenset({"route", "abort"})` at lines 41-43.
- Twin field on FSMLoop: `scripts/little_loops/fsm/schema.py:1115` — `host_guard: HostGuardConfig = field(default_factory=HostGuardConfig)`.
- Twin FSMLoop wiring: `scripts/little_loops/fsm/schema.py:1201-1203` (to_dict), `:1254-1256` (from_dict), `:1309` (construction positional).
- Twin import: `scripts/little_loops/fsm/schema.py:20` — `from little_loops.fsm.host_guard import HostGuardConfig`.
- Twin validator: `scripts/little_loops/fsm/validation.py:2158` — `_validate_host_guard(fsm: FSMLoop, defined_states: set[str]) -> list[ValidationError]`.
- Twin validator dispatcher: `scripts/little_loops/fsm/validation.py:1262` — `errors.extend(_validate_host_guard(fsm, defined_states))` (NOT line 1085; that anchor in the issue body points at the dispatcher's broader region, but the `_validate_host_guard` call sits inside the late-validation block at 1262).
- `KNOWN_TOP_LEVEL_KEYS` whitelist: `scripts/little_loops/fsm/validation.py:175-221` — does NOT include `host_guard`, `cost_ceiling`, or `prompt_size_guard` (these are accepted implicitly via `FSMLoop.from_dict` defaults; see "Research Corrections" below).
- Per-state sibling validators (template for any future per-state cost shape, NOT for the top-level `_validate_cost_limits`): `_validate_state_cost_ceiling` at `validation.py:941`.
- `CostCeilingConfig` exists at `scripts/little_loops/fsm/schema.py:326`; `StateConfig.cost_ceiling` at `:565` — sibling budget-like per-state primitive (ENH-2477); useful as a state-nested precedent.
- Pricing primitive: `scripts/little_loops/pricing.py:58-78` — `estimate_cost_usd(model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens) -> float | None` returns `None` for unknown models.
- Per-state cost aggregation: `scripts/little_loops/fsm/cost_graph.py` — `PerStateCost` (`:41`), `CostReport` (`:106`), `from_usage_jsonl()` (`:183-254`).
- `TokenUsage`: `scripts/little_loops/subprocess_utils.py:45` — `@dataclass` with five required fields: `input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, model`.
- ELIS template: `scripts/little_loops/issue_history/summary.py:171-196` — `_calculate_trend()` uses `statistics.linear_regression(range(n), values).slope` and exposes the pattern; note `ELISForecast` will use both `.slope` AND `.intercept` (the existing call only consumes `.slope`).
- `stats.py:13-39` `wilson_ci()` — guard-clause shape template (`raise ValueError` at top, then return).
- `fsm/__init__.py` re-export pattern: `CostCeilingConfig` re-exported at lines 139, 176 — mirror for `BudgetAccumulatorConfig`.
- `fsm-loop-schema.json:274-335` — `host_guard:` hand-maintained JSON Schema block (additionalProperties: false at the bottom; "Default-enabled..." description pattern).
- Test template (twin surface):
  - `scripts/tests/test_host_guard.py:104-152` — `TestHostGuardConfig` (skip-if-default roundtrip; full FSMLoop round-trip with non-defaults; default-omits-key assertion)
  - `scripts/tests/test_host_guard.py:599-655` — `TestHostGuardValidation` (top-level validator via `validate_fsm()`)
- Action-runner fixture for `usage_events` lists: `scripts/tests/test_usage_journal.py:17-52` — `MockActionRunner` (injects `ActionResult(usage_events=[TokenUsage(...)])`); a `RssActionRunner` analog lives at `test_host_guard.py:55`.

**Re-exports** — `host_guard` and `HostGuardConfig` are imported from their own submodule (`little_loops.fsm.host_guard`); they are NOT re-exported from `fsm/__init__.py`. `CostCeilingConfig` IS re-exported (from `fsm/__init__.py:139, 176`). FEAT-2548 can pick either precedent; the issue spec already calls for re-exports (preferred), which mirrors `CostCeilingConfig`'s behavior.

### Research Corrections

_Facts in the original issue body that research contradicted:_

1. **`KNOWN_TOP_LEVEL_KEYS` should NOT need `budget_accumulator` added.** The issue says (lines 99-101, 141-142) the whitelist must add `"budget_accumulator"` and `"cost_limits"` so `validate_fsm()` does not warn. But the actual twin precedent (`host_guard`) is NOT in `KNOWN_TOP_LEVEL_KEYS` today (neither are `cost_ceiling`/`prompt_size_guard`); they pass through the unknown-key check because the unknown-key warning is gated by `from_dict` defaults and `validate_fsm` does not emit that warning for absent-but-defaulted top-level keys. **Recommended:** do NOT add `budget_accumulator` to `KNOWN_TOP_LEVEL_KEYS` — stay consistent with the existing pattern. If a "unknown top-level key" warning surfaces during implementation, document it separately.

2. **`cost_limits` is a per-state field, not a top-level key.** The issue lists it as a top-level key alongside `budget_accumulator`. But the validator signature proposed — `_validate_cost_limits(fsm: FSMLoop, defined_states: set[str])` — takes `defined_states` (state names) and references `cost_limits` per the spec at line 102. Closer reading of the existing schema (per-state `cost_ceiling` at `StateConfig.cost_ceiling:565`, validator `_validate_state_cost_ceiling` at validation.py:941) suggests `cost_limits` should be a `StateConfig` field, not an `FSMLoop` field. **Recommended:** if `cost_limits` is per-state, add it to `StateConfig` in `fsm/schema.py` near `cost_ceiling` and write `_validate_state_cost_limits` instead of (or in addition to) `_validate_cost_limits`. If the spec truly intends `cost_limits` as a top-level alias for `budget_accumulator`, refactor the issue text accordingly.

3. **`ll-generate-schemas` does NOT generate `fsm-loop-schema.json`.** The issue (line 154) recommends "Use `ll-generate-schemas` to auto-regenerate from the dataclass for parity with the rest of the schema (the manual edit is a fallback)." In reality `ll-generate-schemas` (`scripts/little_loops/generate_schemas.py:569, 588`) emits LLEvent JSON Schemas into `docs/reference/schemas/*.json` only — it does not touch `fsm-loop-schema.json`. The latter is hand-maintained under `scripts/little_loops/fsm/fsm-loop-schema.json`. **Recommended:** treat this as a hand-edit mirroring the `host_guard` block at lines 274-335; do NOT call `ll-generate-schemas` as part of F2a. The issue's proposed Solution Step 4 should be "hand-edit `fsm-loop-schema.json`" with no generator invocation.

4. **Validator dispatcher line** — `_validate_host_guard` is dispatched at `fsm/validation.py:1262`, not `:1085`. The issue cites `:1085` as the call site. The number 1085 is roughly the start of the validate_fsm body block (`:1085-1272`), but the specific `_validate_host_guard(...)` line is `:1262`. **Recommended:** use `:1262` as the precise anchor for the new `_validate_cost_limits(...)` call site.

5. **Test template location** — The issue says `TestBudgetValidation` should mirror `TestThrottleValidation` at `test_fsm_validation.py:623-671` and `TestBudgetAccumulatorConfig` mirror `TestThrottleConfig` at `test_fsm_schema.py:2694-2742`. But the twin (`TestHostGuardValidation`) lives in `test_host_guard.py:599-655` and `TestHostGuardConfig` lives in `test_host_guard.py:104-152`. **Recommended:** the closer twin for both `TestBudgetAccumulator` / `TestBudgetGuard` / `TestELISForecast` is `TestHostGuardConfig` in `test_host_guard.py`; the validator tests should mirror `TestHostGuardValidation` in the same file. New tests should land in `scripts/tests/test_fsm_budget.py` (a new file aligned with the new module), but reference `TestHostGuard*` patterns from `test_host_guard.py` when modeling individual test methods.

### Tests

- `scripts/tests/test_fsm_budget.py` (new) — accumulator / guard / ELIS tests:
  - `TestBudgetAccumulator` — `add_state_usage` crosses `max_cost_usd` once, returns `True` on cross.
  - `TestBudgetGuard` — `check()` returns `OK / WARN / HALT` per threshold.
  - `TestELISForecast` — fit 5 known samples, predict next, error ≤15% on synthetic held-out series.
  - `TestUnknownModel` — `cost_unknown_model=True` propagates; guard is permissive (`cost_unknown_model_fallback="permissive"`).
- Use `MockActionRunner` from `scripts/tests/test_usage_journal.py:17-52`
  for pre-built `ActionResult(usage_events=[TokenUsage(...)])` lists.
- `TestBudgetValidation` in `scripts/tests/test_fsm_validation.py`
  mirroring `TestThrottleValidation` (`:623-671`).
- `TestBudgetAccumulatorConfig` in `scripts/tests/test_fsm_schema.py`
  mirroring `TestThrottleConfig` (`:2694-2742`).

### No-regression baselines

- `scripts/tests/test_pricing.py` (TestModelPricing /
  TestEstimateCostUsd) — unchanged.
- `scripts/tests/test_host_guard.py` — unchanged (twin surface,
  must remain bit-identical in spirit).

## Acceptance Criteria

- `BudgetAccumulator.add(usage).total_usd == sum(estimate_cost_usd)`
  on 5-state synthetic series (within 1e-6 rounding).
- `BudgetAccumulator.add(...)` returns `True` exactly once when
  cumulative cost first exceeds `max_cost_usd`; subsequent calls
  return `False`.
- `BudgetGuard.check(total)` returns `OK` for `total < warn_at * ceiling`,
  `WARN` for `warn_at * ceiling ≤ total < ceiling`, `HALT` for
  `total ≥ ceiling`.
- `ELISForecast.fit([1.0, 2.0, 3.0, 4.0, 5.0]).predict(6) == 6.0`
  ±0.01 (linear series).
- `ELISForecast` ≤15% error on a synthetic held-out geometric
  series (10 samples fit, 5 predict).
- `BudgetAccumulatorConfig.to_dict()` round-trips with
  `BudgetAccumulatorConfig.from_dict()` (skip-if-default parity with
  `HostGuardConfig`).
- `validate_fsm(fsm_with_budget_accumulator)` returns no warnings;
  `validate_fsm(fsm_with_negative_max_cost)` returns ≥1
  `ValidationError`.
- `python -m pytest scripts/tests/` exits 0 (no regressions in
  `test_pricing.py` / `test_host_guard.py` / `test_cost_graph.py`).

## Scope Boundaries

- **In**: primitive library + config dataclass + validation +
  JSON Schema definition + fsm/__init__.py re-exports.
- **Out**: CLI flag (F2b / FEAT-2549); executor wiring
  (F2c / FEAT-2550); config layer (`CostLimitsConfig`,
  `init/core.py` defaults — F2c); OTel transport (F2c); docs
  (F2c).
- **Out of scope**: scipy/numpy dependency (use stdlib
  `statistics.linear_regression`); cross-host `usage_events`
  parity (gated on FEAT-2123).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/fsm/host_guard.py` | Structural twin: `HostGuardConfig`, `HostGuard.record_subproc_rss`, `GuardDecision` |
| `scripts/little_loops/pricing.py:58-78` | `estimate_cost_usd()` for accumulator |
| `scripts/little_loops/issue_history/summary.py:184` | `statistics.linear_regression(range(n), values).slope` — B1 template |
| `scripts/little_loops/stats.py:13-39` | `wilson_ci()` — greenfield template for dataclass shape |
| `scripts/little_loops/subprocess_utils.py:44-56` | `TokenUsage` dataclass — accumulator input |
| `scripts/little_loops/fsm/schema.py:1115` | `host_guard: HostGuardConfig` — twin field anchor |
| `scripts/little_loops/fsm/schema.py:1201-1203, 1254-1256` | `to_dict` / `from_dict` for `host_guard` — round-trip precedent |
| `scripts/little_loops/fsm/validation.py:175` | `KNOWN_TOP_LEVEL_KEYS` — whitelist anchor |
| `scripts/little_loops/fsm/validation.py:2158` | `_validate_host_guard` — template for `_validate_cost_limits` |
| `scripts/little_loops/fsm/validation.py:1085` | `validate_fsm` dispatcher — call site for new validator |
| `scripts/little_loops/fsm/fsm-loop-schema.json` | JSON Schema — mirror `host_guard` block |
| `scripts/tests/test_host_guard.py:75-89` | `make_prompt_fsm()` factory — test template |
| `scripts/tests/test_fsm_validation.py:623-671` | `TestThrottleValidation` — template |
| `scripts/tests/test_fsm_schema.py:2694-2742` | `TestThrottleConfig` — template |
| `scripts/tests/test_usage_journal.py:17-52` | `MockActionRunner` with `usage_events` |
| `FEAT-2476` | Parent umbrella; F2 motivation + scope |
| `EPIC-2456` | Grandparent EPIC; F2 § Goal #1 |

## Impact

- **Priority**: P2 — first-clamp primitive for runaway cost.
- **Effort**: Small — ~120 LOC + ~200 LOC tests.
- **Risk**: Low — greenfield; existing surface unchanged.
- **Breaking Change**: No — additive only; new module + new schema field with default.

## Status

**Open** | Created: 2026-07-08 | Priority: P2 | Split from FEAT-2476

## Session Log
- `/ll:refine-issue` - 2026-07-08T21:40:43 - `f59d4918-2bde-4d86-8cf8-b501d4199e20.jsonl`
- `/ll:capture-issue` (split) - 2026-07-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d276935-0474-4bff-85e3-154d56cf1226.jsonl`
