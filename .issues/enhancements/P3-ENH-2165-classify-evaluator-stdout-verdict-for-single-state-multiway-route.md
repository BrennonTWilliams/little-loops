---
id: ENH-2165
type: ENH
priority: P3
status: done
discovered_date: 2026-06-15
discovered_by: capture-issue
captured_at: '2026-06-15T05:45:00Z'
completed_at: '2026-06-15T23:20:04Z'
parent: EPIC-2167
blocks:
- ENH-2164
- ENH-2166
relates_to:
- ENH-2164
- ENH-2166
- ENH-2154
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 23
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

The FSM router (`_route()` in `fsm/executor.py:1367`) already supports a full
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
(`evaluators.py:889`, `verdict = str(llm_result.get("verdict", "error"))`) — which is
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
      potential dead-end. This requires a **new** validation rule (not MR-4): MR-4
      only fires for LLM-judged states (`llm_structured`/`check_semantic`) and
      explicitly exempts any state that has a `route:` table, so it never applies to
      `classify` states. The new rule checks: `evaluate.type == "classify"` and
      `state.route is not None` and `state.route.default is None` → WARNING.
      Suppressible via `partial_route_ok: true` (same loop-level flag).
- [ ] `scripts/tests/test_fsm_evaluators.py` gains `TestClassifyEvaluator` (after
      `TestConvergenceEvaluator` at line 350): trimmed token, multi-line `line:`
      selection, empty stdout → `default`, non-zero exit → `error`, whitespace
      handling. Dispatcher test in `TestEvaluateDispatcher` (line 409) adds
      `test_dispatch_classify` exercising exit-code short-circuit (non-member of
      `_EXIT_CODE_AWARE_EVALUATORS` at line 1464).
- [ ] `scripts/tests/test_fsm_executor.py` (`TestRouting`, line 1142) gains an
      integration test: a `classify` state + `route:` table dispatches to the
      correct target for ≥3 distinct tokens plus a `default` case.
- [ ] `scripts/tests/test_fsm_validation.py` gains a test asserting the new
      classify-route-default WARNING fires when `default:` is absent and is
      suppressed by `partial_route_ok: true`.
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
3. **Extend `EvaluateConfig`** in `fsm/schema.py` (dataclass at line 25). The
   `source: str | None = None` field (line 81) already exists — no change needed
   there. Add `line: str | int | None = None` for the line selector. Extend the
   `Literal[...]` on the `type` field to include `"classify"`. The executor resolves
   `source:` at lines 1326–1334 before calling `evaluate()` — individual evaluator
   functions including `evaluate_classify()` simply receive the pre-resolved `output`
   string; no source-interpolation logic belongs in the evaluator itself.
4. **Confirm `_route()` coverage** — it already handles `routes[verdict]` and
   `route.default` (`executor.py:1367`, resolution order: exact match → `_` default
   → `_error` key). Add a test that a `classify` verdict lands on `default` when
   unlisted.
5. **Validation rule** — MR-4 does NOT apply here: `_validate_partial_route_dead_end()`
   (validation.py:1357) only fires for LLM-judged states and explicitly skips any
   state with a `route:` table. Add a **new** classify-specific check in
   `fsm/validation.py`: if `evaluate.type == "classify"` and `state.route` exists
   but `state.route.default is None`, emit a WARNING ("classify route: table has no
   default: — unknown tokens will dead-end"). Suppressible via `partial_route_ok:
   true`. Also add `"classify": []` to `EVALUATOR_REQUIRED_FIELDS` (line 64) — this
   automatically registers `classify` in `NON_LLM_EVALUATOR_TYPES` (line 81),
   satisfying the MR-1 non-LLM evaluator gate.
6. **Update `fsm-loop-schema.json`** to add `"classify"` to the evaluator type enum
   so YAML authors get schema validation in editors.
7. **Tests + docs** per Acceptance Criteria.
8. **(Optional, separate PR) Migrate `rn-remediate`** `route_d_*` (lines 265–301) /
   `route_conv_*` (lines 548–581) cascades to single `classify` states — validates
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
- `scripts/little_loops/fsm/evaluators.py` — new `evaluate_classify()` near line 312 + dispatch `elif` in `evaluate()` at line 1428; do NOT add to `_EXIT_CODE_AWARE_EVALUATORS` (local frozenset at line 1464)
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig` dataclass (line 25): extend `type` Literal to include `"classify"`; add `line: str | int | None = None` field (`source:` already exists at line 81)
- `scripts/little_loops/fsm/validation.py` — add `"classify": []` to `EVALUATOR_REQUIRED_FIELDS` (line 64); add new classify-route-default WARNING check (not MR-4 extension — `_validate_partial_route_dead_end()` at line 1357 does not apply to `classify` states or states with `route:` tables)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `"classify"` to the evaluator type enum for editor schema validation
- `scripts/little_loops/fsm/executor.py` — `source:` resolution already exists at lines 1326–1334; `_route()` at line 1367 already supports the full `route:` table including `default:` — verify only, no changes expected
- `docs/guides/LOOPS_GUIDE.md` (evaluator catalog entry + routing example)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/lib/policy-router.yaml` (ENH-2164) — consumes `classify` for its dispatch handoff
- `scripts/little_loops/loops/rn-remediate.yaml` — candidate first adopter (optional follow-on)

### Similar Patterns
- `evaluate_output_contains` (`evaluators.py:312`) — closest existing evaluator; note `source:` is NOT read inside this function — the executor pre-resolves it at lines 1326–1334 and passes the result as `output`; model the evaluator body on this function but `source:` handling is already done upstream
- `evaluate_convergence` (`evaluators.py:351`) — existing arbitrary-ish verdict vocabulary (`progress`/`stall`/`target`) routed via a `route:` table in `harness-optimize.yaml` (`gate` state, lines 177–189)
- `_route()` (`executor.py:1367`) — the table dispatch + `default:` resolution this builds on; resolution order: exact verdict key → `_` (default) → `_error` key

### Tests
- `scripts/tests/test_fsm_evaluators.py` — `TestClassifyEvaluator` after `TestConvergenceEvaluator` (line 350); dispatcher test in `TestEvaluateDispatcher` (line 409)
- `scripts/tests/test_fsm_executor.py` — integration in `TestRouting` (line 1142): `classify` + `route:` dispatch across ≥3 tokens + `default`
- `scripts/tests/test_fsm_validation.py` — new classify-route-default WARNING check + `partial_route_ok` suppression

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — evaluator catalog + single-state multi-way routing example

### Configuration
- N/A — no config-schema changes beyond the evaluator's own `source:`/`line:` fields

## Related Key Documentation

- [`scripts/little_loops/fsm/evaluators.py`](../../scripts/little_loops/fsm/evaluators.py) — evaluator implementations + `evaluate()` dispatch (line 1428); `_EXIT_CODE_AWARE_EVALUATORS` local frozenset (line 1464)
- [`scripts/little_loops/fsm/schema.py`](../../scripts/little_loops/fsm/schema.py) — `EvaluateConfig` dataclass (line 25); `source:` field (line 81); `RouteConfig.from_dict()` (line 198); `FSMLoop.partial_route_ok` (line 979)
- [`scripts/little_loops/fsm/executor.py`](../../scripts/little_loops/fsm/executor.py) — `source:` resolution at lines 1326–1334; `_route()` table resolution at line 1367
- [`scripts/little_loops/fsm/validation.py`](../../scripts/little_loops/fsm/validation.py) — `EVALUATOR_REQUIRED_FIELDS` (line 64); `NON_LLM_EVALUATOR_TYPES` (line 81); `_is_llm_judged()` (line 1338); `_validate_partial_route_dead_end()` MR-4 (line 1357)
- [`scripts/little_loops/loops/harness-optimize.yaml`](../../scripts/little_loops/loops/harness-optimize.yaml) — existing `route:` table + `convergence` multi-verdict evaluator (`gate` state, lines 177–189)
- [`scripts/little_loops/loops/rn-remediate.yaml`](../../scripts/little_loops/loops/rn-remediate.yaml) — `route_d_*` (lines 265–301) / `route_conv_*` (lines 548–581) cascades this collapses; real-world validation target
- ENH-2164 (`lib/policy-router`) — blocked on this; consumes `classify` for routing handoff
- ENH-2154 (`lib/rubric-router`) — the degenerate single-aggregate case of the broader dimensional-router family

## Labels

`enh`, `loops`, `fsm`, `evaluators`, `dx`

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-15T23:00:08 - `fd395ee8-f0ae-4416-8230-2303026d309b.jsonl`
- `/ll:refine-issue` - 2026-06-15T22:52:03 - `f21b695c-86db-45cc-a3e7-4fc0e4d191e4.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `fa2a0dab-ebd0-4f63-8592-ab02f036f461.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `dff9956f-1025-4a35-a9a7-839ff501fa71.jsonl`
- `/ll:format-issue` - 2026-06-15T22:37:53 - `1b107727-bab7-42ec-9537-98919c7f947e.jsonl`
- `/ll:capture-issue` - 2026-06-15T05:45:00Z - manual
