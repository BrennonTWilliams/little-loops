---
id: ENH-2165
type: ENH
priority: P3
status: open
discovered_date: 2026-06-15
discovered_by: capture-issue
captured_at: '2026-06-15T05:45:00Z'
parent: EPIC-2167
blocks:
- ENH-2164
- ENH-2166
relates_to:
- ENH-2164
- ENH-2166
- ENH-2154
---

# ENH-2165: `classify` Evaluator — Stdout-as-Verdict for Single-State Multi-Way `route:`

## Summary

Add a `classify` evaluator type to the FSM (`scripts/little_loops/fsm/evaluators.py`)
whose verdict **is** the action's trimmed stdout token. Paired with an existing
`route:` table, this lets a single shell/python state emit one of N tokens and
dispatch directly to the matching target state in one hop — collapsing the
hand-rolled `output_contains` routing cascades (e.g. `rn-remediate`'s
`route_d_implement → route_d_decide → route_d_wire → route_d_refine` and
`route_conv_*` chains) into a single classifier state.

## Current Behavior

The FSM router (`_route()` in `fsm/executor.py:355`) already supports a full
`route:` table keyed on the verdict string (verified in use by `harness-optimize.yaml`
with the `convergence` evaluator's `target`/`progress`/`stall` verdicts). The
machinery for "verdict string → named target state" exists.

What is missing is a **non-LLM evaluator that yields an arbitrary token as the
verdict**. Every deterministic evaluator collapses output to a fixed verdict set:

- `exit_code` → `yes`/`no`/`error`
- `output_contains` → `yes`/`no` (single-pattern boolean)
- `output_numeric` / `output_json` → `yes`/`no`/`error`
- `convergence` → `progress`/`stall`/`error` (fixed 3-way)

The only evaluators that emit an arbitrary verdict are `llm_structured`
(`evaluators.py:889`, `verdict = str(llm_result.get("verdict", ...))`) — which is
an LLM self-grade — and `convergence`'s fixed vocabulary.

Consequently, any loop that classifies into M>2 deterministic buckets must fan
out into a **cascade of single-pattern `output_contains` states**, one per
bucket, each `on_no` falling through to the next:

```yaml
route_d_implement:
  evaluate: {type: output_contains, source: "${captured.diagnosis.output}", pattern: "IMPLEMENT"}
  on_yes: gate_implement
  on_no: route_d_decide        # fall-through
route_d_decide:
  evaluate: {type: output_contains, source: "${captured.diagnosis.output}", pattern: "DECIDE"}
  on_yes: decide
  on_no: route_d_wire          # fall-through
# ... route_d_wire, route_d_refine ...
```

This is verbose (one state per branch), order-fragile (substring collisions —
`STALLED_NEEDS_DECOMPOSE` matches `NEEDS_DECOMPOSE`), and untestable as a unit.

## Motivation

The `route:` table + `classify` verdict is the missing keystone for declarative,
single-state multi-way routing. It directly unblocks two issues and one real
shipping router:

1. **ENH-2164 (`lib/policy-router`)** — its central design risk (Implementation
   Step 4) is *"the fragment cannot dynamically redirect to an arbitrary state
   name via shell exit code alone."* `classify` is the clean third option beyond
   the verbose `policy_route_<name>` cascade (option a) and the underspecified
   `dynamic_next` executor change (option b): the dispatch fragment emits the
   winning action state name to stdout, `classify` lifts it to the verdict, and a
   `route:` table maps it to the state. **ENH-2164 is `blocked_by` this issue.**

2. **A general `lib/decision-router` engine** (the L1 layer under ENH-2154's
   rubric-router and ENH-2164's policy-router) — a source-agnostic, conjunctive
   rule table that emits a token and routes via `classify` + `route:`.

3. **`rn-remediate.yaml`** — its `diagnose` (`route_d_*`) and `check_convergence`
   (`route_conv_*`) cascades are the existing, battle-tested instance of exactly
   this pattern. Both collapse to a single classifier state once `classify` lands.

## Expected Behavior

A single state classifies and routes:

```yaml
diagnose:
  action_type: shell
  action: |
    # ... compute scores, print exactly one token on the final line ...
    echo "WIRE"
  evaluate:
    type: classify
    # optional: which line to read (default: last non-empty line of stdout)
    source: "${captured.diagnosis.output}"   # optional; defaults to this action's stdout
  route:
    IMPLEMENT: gate_implement
    DECIDE:    decide
    WIRE:      wire
    REFINE:    refine
    DECOMPOSE: emit_needs_decompose
    default:   emit_implement_failed         # unknown/empty token
```

Verdict resolution:
- The verdict is the **trimmed token** read from the configured source (default:
  the last non-empty line of the action's stdout; configurable via `source:` to
  read a captured value or a different line).
- The `route:` table maps the token → target state. `default:` catches any token
  with no explicit row (mirrors the existing `route.default` handling in
  `_route()`).
- Exit-code semantics: a non-zero exit yields verdict `error` (consistent with
  the existing `_EXIT_CODE_AWARE_EVALUATORS` short-circuit — `classify` is NOT
  added to that set, so a crashing classifier routes via `route.error`/`default`
  rather than mis-emitting a token). A clean (exit 0) run with empty stdout yields
  the `default` route.

## Acceptance Criteria

- [ ] `evaluate_classify(output, source, ...)` added to `fsm/evaluators.py`,
      returning `EvaluationResult(verdict=<trimmed token>, details={...})`.
- [ ] `evaluate()` dispatch (`evaluators.py:1428`) routes `eval_type == "classify"`
      to it; schema/config (`EvaluateConfig`) accepts `type: classify` with an
      optional `source:` (defaults to the action's own stdout) and an optional
      `line:` selector (`last` default / `first` / integer index).
- [ ] Token is the trimmed, single-line value; multi-line stdout selects per the
      `line:` rule; leading/trailing whitespace stripped; empty → `default`/error.
- [ ] `classify` is **excluded** from `_EXIT_CODE_AWARE_EVALUATORS` so a non-zero
      exit short-circuits to verdict `error` (no token laundering on crash).
- [ ] `route:` table dispatch on a `classify` verdict works end-to-end via
      `_route()` including the `default:` fallback for unlisted tokens.
- [ ] FSM validation: a `classify` state with a `route:` table whose rows do not
      cover all emitted tokens and has no `default:` is flagged (WARN) as a
      potential dead-end — reuses/extends the MR-4 partial-route check rather than
      adding a new rule. (If MR-4 already covers `route:`-table gaps, document that
      and add a test asserting coverage; otherwise extend it.)
- [ ] `scripts/tests/test_fsm_evaluators.py` gains `TestClassifyEvaluator`:
      trimmed token, multi-line `line:` selection, empty stdout → `default`,
      non-zero exit → `error`, whitespace handling.
- [ ] `scripts/tests/test_fsm_executor.py` (or equivalent) gains an integration
      test: a `classify` state + `route:` table dispatches to the correct target
      for ≥3 distinct tokens plus a `default` case.
- [ ] `docs/guides/LOOPS_GUIDE.md` documents the `classify` evaluator alongside the
      existing evaluator catalog, with the single-state multi-way routing example.

## Implementation Steps

1. **Add `evaluate_classify()`** to `fsm/evaluators.py` near `evaluate_output_contains`.
   Read the source (default `output`), apply the `line:` selector, strip, return
   the token as the verdict. Empty → return a sentinel that `_route()` resolves to
   `default` (simplest: verdict = empty string; `_route()` already falls to
   `route.default` when the verdict is not in `routes`).
2. **Wire dispatch** in `evaluate()` (`evaluators.py:1428`). Do **not** add
   `classify` to `_EXIT_CODE_AWARE_EVALUATORS` — let the existing `exit_code != 0`
   short-circuit produce `error` for crashed classifiers.
3. **Extend `EvaluateConfig`** (wherever evaluator config is parsed) with the
   optional `source:` and `line:` fields; interpolate `source:` like other
   evaluators (`output_numeric` target interpolation is the pattern to follow).
4. **Confirm `_route()` coverage** — it already handles `routes[verdict]` and
   `route.default` (`executor.py:355`). Add a test that a `classify` verdict lands
   on `default` when unlisted.
5. **Validation rule** — confirm MR-4 (`partial_route_ok`) reasoning extends to a
   `route:` table missing `default:`. Extend the check in `fsm/validation.py` if it
   only inspects `on_yes`/`on_no` shorthands today.
6. **Tests + docs** per Acceptance Criteria.
7. **(Optional, separate PR) Migrate `rn-remediate`** `route_d_*` / `route_conv_*`
   cascades to single `classify` states as the first real-world adopter — validates
   the primitive against a shipping router. Keep out of this issue's scope to keep
   the executor change small and independently reviewable.

## Scope Boundaries

- **In scope**: the `classify` evaluator, its config (`source:`, `line:`), dispatch
  wiring, `route:`-table `default:` coverage validation, unit + integration tests,
  LOOPS_GUIDE entry.
- **Out of scope**: building `lib/policy-router` (ENH-2164) or a general
  `lib/decision-router` on top of this; migrating `rn-remediate` (optional
  follow-on); weighted/probabilistic verdicts; regex-extracted verdicts (the token
  is a literal line — callers compute it in the action body).

## Impact

- **Priority**: P3 — small, high-leverage executor primitive; unblocks ENH-2164
  and a general decision-router; no blocking dependency of its own.
- **Effort**: Small — one evaluator function (~15–25 LOC), dispatch + config wiring,
  a validation tweak, and tests. The `route:` machinery already exists.
- **Risk**: Low — purely additive evaluator type; no change to existing verdict
  vocabularies or `_route()` resolution order; exit-code semantics inherit the
  established short-circuit.
- **Breaking Change**: No.

## API/Interface

New evaluator type in `scripts/little_loops/fsm/evaluators.py`:

```yaml
evaluate:
  type: classify
  source: "${captured.<name>.output}"   # optional; default = this action's stdout
  line: last                            # optional; last (default) | first | <int index>
```

- Verdict = trimmed token from the selected line of `source`.
- Pair with `route:` (token → state, plus `default:` and `error:`).
- Non-zero action exit → verdict `error` (routes via `route.error`/`default`).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` (new `evaluate_classify` + dispatch case)
- `scripts/little_loops/fsm/executor.py` (config parse for `source:`/`line:`; `_route()` already supports the table — verify only)
- `scripts/little_loops/fsm/validation.py` (extend MR-4 `route:`-table `default:` coverage if needed)
- `docs/guides/LOOPS_GUIDE.md` (evaluator catalog entry + routing example)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/lib/policy-router.yaml` (ENH-2164) — consumes `classify` for its dispatch handoff
- `scripts/little_loops/loops/rn-remediate.yaml` — candidate first adopter (optional follow-on)

### Similar Patterns
- `evaluate_output_contains` (`evaluators.py:312`) — closest existing evaluator; model the source/line handling on it
- `evaluate_convergence` (`evaluators.py:351`) — existing arbitrary-ish verdict vocabulary (`progress`/`stall`) routed via a `route:` table in `harness-optimize.yaml`
- `_route()` (`executor.py:355`) — the table dispatch + `default:` resolution this builds on

### Tests
- `scripts/tests/test_fsm_evaluators.py` — `TestClassifyEvaluator` (token trim, line select, empty→default, non-zero→error)
- `scripts/tests/test_fsm_executor.py` — integration: `classify` + `route:` dispatch across ≥3 tokens + `default`

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — evaluator catalog + single-state multi-way routing example

### Configuration
- N/A — no config-schema changes beyond the evaluator's own `source:`/`line:` fields

## Related Key Documentation

- [`scripts/little_loops/fsm/evaluators.py`](../../scripts/little_loops/fsm/evaluators.py) — evaluator implementations + `evaluate()` dispatch
- [`scripts/little_loops/fsm/executor.py`](../../scripts/little_loops/fsm/executor.py) — `_route()` table resolution this enables
- [`scripts/little_loops/loops/harness-optimize.yaml`](../../scripts/little_loops/loops/harness-optimize.yaml) — existing `route:` table + multi-verdict evaluator reference
- [`scripts/little_loops/loops/rn-remediate.yaml`](../../scripts/little_loops/loops/rn-remediate.yaml) — `route_d_*` / `route_conv_*` cascades this collapses; real-world validation target
- ENH-2164 (`lib/policy-router`) — blocked on this; consumes `classify` for routing handoff
- ENH-2154 (`lib/rubric-router`) — the degenerate single-aggregate case of the broader dimensional-router family

## Labels

`enh`, `loops`, `fsm`, `evaluators`, `dx`

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-06-15T05:45:00Z - manual
