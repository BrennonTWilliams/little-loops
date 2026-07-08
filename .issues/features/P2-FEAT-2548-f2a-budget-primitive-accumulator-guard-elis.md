---
id: FEAT-2548
title: "F2a \u2014 fsm/budget.py primitive (BudgetAccumulator + BudgetGuard + ELISForecast)\
  \ + BudgetAccumulatorConfig schema + validation + JSON schema"
type: FEAT
priority: P2
status: open
captured_at: '2026-07-08T00:00:00Z'
discovered_date: 2026-07-08
discovered_by: split-from-FEAT-2476
parent: FEAT-2476
relates_to:
- EPIC-2456
- FEAT-2549
- FEAT-2550
- ENH-2475
- ENH-2477
- FEAT-2478
- ENH-2461
- FEAT-2123
labels:
- token-cost
- budget
- fsm
- tier-1
decision_needed: false
confidence_score: 99
outcome_confidence: 85
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

The new top-level field, validator, and JSON Schema block flow downstream through these callers. None require direct edits, but they exercise the new surface and must round-trip cleanly. Per Pass-2 Research Corrections, `_validate_state_cost_limits` is the per-state validator (not top-level `_validate_cost_limits`); `KNOWN_TOP_LEVEL_KEYS` does NOT include `budget_accumulator` (mirror `host_guard` precedent).

**Informational carriers / consumers** (input/output shape providers, no edits required):

- `scripts/little_loops/cli/loop/info.py:1244` — calls `fsm.to_dict()` for terminal loop dumps; round-trip compatibility for the new `budget_accumulator` block is exercised here (verified by `test_builtin_loops.py:46-54` walking every builtin through `validate_fsm`). [Agent 1]
- `scripts/little_loops/cli/loop/layout.py:19` — imports `StateConfig`; relevant only IF `cost_limits` lands as a per-state field (per Research Correction #2 at issue :300). [Agent 1]
- `scripts/little_loops/fsm/cost_graph.py:25` — imports `estimate_cost_usd`; sister cost-aggregation module (ENH-2477). Shares the `estimate_cost_usd(usage) → float | None` shape that `BudgetAccumulator.add_state_usage()` will consume; keep signature parity. [Agent 1]
- `scripts/little_loops/fsm/types.py:86` — `usage_events: list[TokenUsage] = field(default_factory=list)` on `ActionResult`. The F2c executor will feed these into the accumulator. [Agent 1]
- `scripts/little_loops/subprocess_utils.py:45` — `TokenUsage` dataclass (5 required fields: `input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, model`). Input shape `BudgetAccumulator.add_state_usage` accepts. [Agent 1]
- `scripts/little_loops/pricing.py:58-78` — `estimate_cost_usd(model, input_tokens, output_tokens, cache_read_tokens=0, cache_creation_tokens=0) → float | None`. Returns `None` for unrecognized models — the trigger for `BudgetAccumulator.cost_unknown_model = True` and the `cost_unknown_model_fallback` policy. [Agent 1]

**Out-of-scope** (F2b/FEAT-2549 or F2c/FEAT-2550 owned; listed for tracking only, NOT edited by F2a):
- `scripts/little_loops/cli/loop/__init__.py:151-165, 484-493` — argparse `--no-host-guard`/`--host-guard-budget-mb` precedent (F2b mirrors with `--no-budget-accumulator`/`--max-cost`)
- `scripts/little_loops/cli/loop/run.py:132-135` — `cmd_run` override on `fsm.host_guard` (F2b mirror)
- `scripts/little_loops/cli/loop/lifecycle.py:532-536` — resume override on `fsm.host_guard.enabled` (F2c mirror)
- `scripts/little_loops/cli/loop/_helpers.py:1442-1446` — `run_background`/`queue` forwarding (F2b mirror)
- `scripts/little_loops/fsm/executor.py:301-311, 582, 634-638, 656, 1390, 1480-1491, 1552, 2136-2151` — `HostGuard` construction in FSMExecutor (F2c mirror)
- `scripts/little_loops/fsm/runners.py:19` — `RssSampler` import (F2c mirror)
- `scripts/little_loops/fsm/runners.py` (TokenUsage aggregation, F2c)
- `scripts/little_loops/init/core.py:21, 32` — config-schema.json default threading (F2c)
- `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/development/TROUBLESHOOTING.md`, `docs/reference/EVENT-SCHEMA.md`, `docs/reference/schemas/`, `docs/reference/CONFIGURATION.md` — documentation (F2c)

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

**Pass-2 verification findings** (added by `/ll:refine-issue --auto`; all anchors re-verified against the live tree — no implementation has landed yet, `scripts/little_loops/fsm/budget.py` does NOT exist on disk):

- **`Pricing.return-None semantics`** — `scripts/little_loops/pricing.py:58` `estimate_cost_usd(model, input_tokens, output_tokens, cache_read_tokens=0, cache_creation_tokens=0) -> float | None`. Returns `None` for unrecognized `model` strings (mirror of the recommendation in the existing Codebase Research Findings at the proposed-solution block above). The `None`-return path is the trigger for `BudgetAccumulator.cost_unknown_model` and the `cost_unknown_model_fallback` policy in `BudgetGuard.check(...)`.

- **`add()` vs `add_state_usage()` naming inconsistency** — Proposed Solution Step 1 names the API `add(usage) -> bool` (line 115). The Tests section enumerates a method named `add_state_usage` (line 293). Pick one and use it consistently; the token-usage input is per-state (one FSM state emits one or more `TokenUsage` records into `ActionResult.usage_events`), so `add_state_usage(usage: TokenUsage) -> bool` reads more precisely. Either is acceptable; **recommended** name is `add_state_usage` (matches the throttle/usage-journal vocabulary used by `CostReport.from_usage_jsonl` at `cost_graph.py:183-254`).

- **`GuardDecision` field justification** — host_guard's twin (`GuardDecision` at `host_guard.py:304-322`) carries `action, used_pct, cooldown_seconds, target, relieved`. The proposed `GuardDecision(action, used_pct, total_usd, target)` drops `cooldown_seconds` (no sleep primitive for budget — F2c/FEAT-2550 routes/aborts instead) and `relieved` (no hysteresis — budget either fires the latch once or stays armed). The drops are intentional; mirror them as stated, do not silently re-introduce the host_guard fields.

- **`budget_enabled` is implicit, not explicit in Proposed Solution Step 1** — the Codebase Research Findings block above (around line 209) calls for a `budget_enabled` `@property` returning `self.config.max_cost_usd > 0`. The Proposed Solution Step 1 lists `BudgetAccumulator` with `total_usd`, `cumulative_state_count`, and `cost_unknown_model` only. Add `budget_enabled: bool` to the property list in Step 1 (mirror host_guard `budget_enabled` at `host_guard.py:392-394`) so the latch short-circuit path matches the documented precedent.

- **`_validate_cost_limits` vs `_validate_state_cost_limits` — implementation must follow Correction #2** — Correction #2 already says `cost_limits` is a per-state field (sibling to `cost_ceiling`). The Proposed Solution Step 3 still invokes `_validate_cost_limits(fsm: FSMLoop, defined_states)` and dispatches from `validate_fsm()` at the top-level. Implement to follow Correction #2: write `_validate_state_cost_limits(state_name, state, path)` and dispatch from the per-state loop (the loop that calls `_validate_state_cost_ceiling` near `validation.py:934-936`), not from the `validate_fsm` body at `:1262`. The Proposed Solution text and Step 3 anchor numbers are stale on this point.

- **JSON Schema block placement** — the `host_guard` block ends at `fsm-loop-schema.json:335` (additionalProperties:false at line 334). The next sibling block, `prompt_size_guard`, starts at `fsm-loop-schema.json:336`. Place the new `budget_accumulator:` block **immediately after `prompt_size_guard`** (alphabetically ordered: `b`udget_accumulator before `h`ost_guard before `p`rompt_size_guard — wait, insertion is at the alphabetically-correct position, which is BEFORE `host_guard` since `b` < `h`). Reorder so `budget_accumulator` precedes `host_guard` at lines ~273-274 (currently `host_guard` block starts there).

- **`fsm/__init__.py` `__all__` insertion point** — the alphabetized list (`fsm/__init__.py:170-250`) currently contains no `B`-prefixed entries other than the embedded ones. Insert `BudgetAccumulator`, `BudgetAccumulatorConfig`, `BudgetGuard`, `ELISForecast`, `GuardDecision` alphabetically — `BudgetAccumulator` between existing entries near `B`-position, `BudgetAccumulatorConfig` adjacent, `BudgetGuard` adjacent, `ELISForecast` between `E`-prefixed and `F`-prefixed entries, `GuardDecision` after the `G`-prefixed entries. The Grouped import (`fsm/__init__.py:135-152`) also needs the new names added inside `from little_loops.fsm.budget import (...)` — but only IF `BudgetAccumulatorConfig` truly belongs on `FSMLoop` (it does, per the proposed solution); `HostGuardConfig` is NOT in this group import today, so `BudgetAccumulatorConfig` would actually be the first `FSMLoop`-level dataclass in the group import. Either precedent is defensible; mirror the `HostGuardConfig` non-re-export (let consumers import via `from little_loops.fsm.budget import BudgetAccumulatorConfig`).

- **Test-method catalog to model** — the verification pass enumerated all 10 `TestHostGuardValidation` methods (`test_defaults_valid`, `test_route_requires_pressure_state`, `test_pressure_state_must_be_declared`, `test_invalid_on_pressure_value`, `test_critical_below_warn`, `test_pct_out_of_range`, `test_budget_route_requires_budget_state`, `test_budget_state_must_be_declared`, `test_on_abort_route_must_be_declared`, `test_invalid_on_budget_exceeded`). The `_validate_state_cost_limits` test class should cover the equivalent rejected-config cases: `max_cost_usd < 0`, `warn_at ∉ [0, 1]`, `warn_at > ceiling_ratio` (if any), and (if per-state-nested) per-state coverage-required checks.

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

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_builtin_loops.py:46-54` — `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` walks every builtin loop YAML through `validate_fsm` (plus `test_all_parse_as_yaml` at :39, `test_all_have_description_field` at :56). Built-in loops do not set `budget_accumulator` or `cost_limits` (default `0.0`/`None`), so the new validator must NOT trip on defaults. Confirmed no built-in loop references `budget_accumulator` (Grep-verified zero matches). [Agent 3]
- `scripts/tests/test_fsm_flow.py:325` — `test_all_builtin_loops_still_load` globs every builtin `*.yaml` and calls `load_and_validate`. Same coverage as `test_builtin_loops.py`. [Agent 3]
- `scripts/tests/test_builtin_loops.py:8581` — `TestLoopReferencesResolve` — references-parsing gate; should pass unchanged. [Agent 3]
- `scripts/tests/test_general_task_loop.py:43` — `test_validates_as_fsm` round-trips `general-task.yaml` builtin; relevant if `cost_limits` lands per-state. [Agent 3]
- `scripts/tests/test_fsm_fragments.py:789-791` — `TestLoadAndValidateIntegration.test_import_and_fragments_keys_no_warning` and `:829 test_fragments_key_no_warning` — `KNOWN_TOP_LEVEL_KEYS` whitelist integration. Per Research Correction #1 (issue :298), do NOT add `budget_accumulator` to the whitelist, so these tests must continue to pass without edit. [Agent 3]
- `scripts/tests/test_fsm_inheritance.py:6` (file-level integration with `load_and_validate`/`KNOWN_TOP_LEVEL_KEYS`) — no F2a edit; the new field defaults absorb cleanly. [Agent 3]

### Tests Update Required (added by `/ll:wire-issue`)

- `scripts/tests/test_cli_loop_layout.py:120-145` — `_make_state_dict()` fixture at :120-145 enumerates `StateConfig` defaults (includes `"cost_ceiling": None` at line 144). **IF `cost_limits` lands as a per-state field on `StateConfig` per Research Correction #2**, add `"cost_limits": None` here. This is a concrete edit conditional on the RC#2 decision. [Agent 1 + Agent 3]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be added to Proposed Solution steps 1-5 during implementation:_

N. **`scripts/little_loops/fsm/schema.py:20`** — add `from little_loops.fsm.budget import BudgetAccumulatorConfig` parallel to the existing `from little_loops.fsm.host_guard import HostGuardConfig`. Proposed Solution Step 2 (issue :128-136) implies this but does not state the import line explicitly. [Agent 1]

N+1. **`scripts/little_loops/fsm/__init__.py:170-250`** alphabetized `__all__` — insert `BudgetAccumulator`, `BudgetAccumulatorConfig`, `BudgetGuard`, `ELISForecast`, `GuardDecision` at the alphabetically-correct positions per Pass-2 finding #7 (issue :290): `Budget*` entries adjacent near `B`-position, `ELISForecast` between `E`- and `F`-prefixed entries, `GuardDecision` after `G`-prefixed entries. Also update the Grouped import block at :135-152 (`from little_loops.fsm.budget import (...)`). [Agent 1]

N+2. **Per-state `cost_limits` placement (if RC#2 decides per-state)** — write `_validate_state_cost_limits(state_name, state, path)` and dispatch from the per-state loop at `validation.py:934-936` (alongside `_validate_state_cost_ceiling` at :941), NOT from `validate_fsm` body at :1262. Add `cost_limits` field to `StateConfig` near `cost_ceiling` at `schema.py:565`. Update the `_validate_state_cost_limits` test in `scripts/tests/test_fsm_validation.py` to use the per-state pattern (mirror `TestCostCeilingValidation` at :676-746). [Agent 2]

N+3. **No-regression verification for known-top-level-keys whitelist** — Per Research Correction #1 (issue :298), `budget_accumulator` MUST NOT be added to `KNOWN_TOP_LEVEL_KEYS` (mirror `host_guard`/`prompt_size_guard`/`cost_ceiling`, none of which are in the whitelist today). Verify `scripts/tests/test_fsm_schema.py:1689-1806` patterns (`test_unknown_top_level_keys_warn`, `test_known_keys_no_warning`, `test_commands_key_no_warning`, `test_required_inputs_key_no_warning`) and `scripts/tests/test_fsm_fragments.py:789-791` still pass after implementation. No new test class needed; the existing assertions cover the new field's absence-from-whitelist automatically. [Agent 2 + Agent 3]

N+4. **No-regression verification for builtin loops** — run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_flow.py` after implementation. None of the builtin loops reference `budget_accumulator` or `cost_limits` (Grep-verified zero matches across `loops/`); the new validator/field must not trip on defaults. [Agent 3] 

N+5. **CLI/info round-trip smoke test** — `scripts/little_loops/cli/loop/info.py:1244` calls `fsm.to_dict()` for terminal loop dumps. Verify `ll-loop info <file.yaml>` on the `examples/` sample loops still produces clean output (the new top-level field appears with skip-if-default, per `HostGuardConfig.to_dict()` parity at `host_guard.py:84-107`). No edit required; just a smoke verification step.

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
- `/ll:confidence-check` - 2026-07-08T23:15:00 - `f67bde41-aa84-4a1b-ad27-e8c1f9ebcae7.jsonl`
- `/ll:wire-issue` - 2026-07-08T22:40:15 - `1e19d2a6-39cb-4104-99bb-22306a4c69f1.jsonl`
- `/ll:refine-issue` - 2026-07-08T22:25:20 - `b84b69a0-56ff-48e1-86cd-c6975ea93ac9.jsonl`
- `/ll:refine-issue` - 2026-07-08T21:40:43 - `f59d4918-2bde-4d86-8cf8-b501d4199e20.jsonl`
- `/ll:capture-issue` (split) - 2026-07-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d276935-0474-4bff-85e3-154d56cf1226.jsonl`
