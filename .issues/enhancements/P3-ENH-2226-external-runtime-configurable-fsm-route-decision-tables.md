---
id: ENH-2226
type: ENH
priority: P3
status: cancelled
discovered_date: 2026-06-19
discovered_by: capture-issue
captured_at: '2026-06-19T03:17:41Z'
decision_needed: false
---

# ENH-2226: External/runtime-configurable FSM route decision tables

## Summary

Add the ability to configure FSM loop routing (the `route:` decision table) from outside the loop YAML — via CLI override, a shared config file, or context variables — without editing the loop YAML directly.

## Motivation

Currently, `route:` tables are fixed at YAML authoring time and embedded inline in each loop file. There is no mechanism to:

- Override routing for a specific run without modifying the loop YAML
- Share a decision table across multiple loops or states
- Inject routing policy via `--context` or a config file at invocation time

This makes it hard to experiment with routing variants (A/B test a new routing policy), reuse common dispatch tables, or let downstream callers customize routing behavior without forking the loop.

## Current Behavior

`route:` is a static `dict[str, str]` field on `StateConfig` (`schema.py:425`), populated from YAML at parse time. `RouteConfig.from_dict` (`schema.py:204`) builds it once; the executor resolves it from the frozen state object at runtime (`executor.py:1492`). There is no injection point for external overrides.

## Expected Behavior

At minimum, one of:

1. **Context-variable interpolation in route targets** — allow `route: { IMPLEMENT: "{{context.override_implement_state}}" }` so callers can redirect a single arm without touching the YAML.
2. **Named shared route tables** — define a `route_tables:` block at loop top-level (or in a lib fragment) and reference it as `route: $my_table` from any state.
3. **CLI route-override flag** — `ll-loop run <loop> --route-override IMPLEMENT=gate_b` patches a single arm for one run without editing the file.

> **Selected:** Context-variable interpolation in route targets (Option 1) — runtime interpolation already works in `_resolve_route()`; only two focused fixes to `validation.py` and `run.py` needed.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-18.

**Selected**: Context-variable interpolation in route targets (Option 1)

**Reasoning**: Option 1 is the clear winner because `_resolve_route()` at `executor.py:1524` already calls `interpolate(route, ctx)` on every route target string — the runtime mechanism exists today with zero executor changes required. Only two small, well-scoped fixes are needed: skip `${...}` tokens in the validator's unknown-state check (`validation.py`), and extend the pre-run context scan in `run.py` to include route values. The existing `rl-bandit.yaml` precedent (`target: "${context.reward_target}"`) confirms this pattern is already authoring-safe.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 (context interpolation) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option 2 (named route tables) | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |
| Option 3 (CLI flag) | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- **Option 1**: Runtime already interpolates route values; two fixes to `validation.py` + `run.py` cover all gaps; `rl-bandit.yaml` shows `${context.*}` in non-action config fields is established practice.
- **Option 2**: No `route_tables:` schema precedent; requires new top-level key, reference resolver, and parser changes — high complexity for moderate benefit.
- **Option 3**: Follows `--context` flag model at `__init__.py:233–238`; additive and low-risk, but less flexible than Option 1 which supports dynamic context-driven routing without CLI intervention.

## Success Metrics

- Context-variable interpolation: `{{context.override_state}}` in a `route:` value resolves to the injected context value and routes accordingly
- CLI override: `ll-loop run <loop> --route-override KEY=state_b` redirects the named arm without editing the YAML
- Shared table: a `route_tables:` entry referenced by ≥2 loops produces identical routing behavior across both
- Zero regression: existing loops with static `route:` dicts continue to execute unchanged

## Scope Boundaries

- **In scope**: at least one of — context-variable interpolation in route target values, named `route_tables:` block at loop top-level, CLI `--route-override` flag
- **Out of scope**: changes to evaluator verdict logic, runtime modification of `action_type` or `action`, modifying non-route state transitions, schema changes to state fields other than `route:`

## API/Interface

Depends on approach selected (see Expected Behavior / Options):

- **Option 1 (context interpolation)** — no new public API; route values accept `{{context.*}}` refs via the existing `interpolate()` path in `executor.py`
- **Option 2 (named tables)** — new `route_tables:` top-level key in loop YAML; states reference via `route: $table_name`
- **Option 3 (CLI flag)** — `ll-loop run <loop> --route-override KEY=STATE [--route-override KEY2=STATE2]`

## Implementation Steps

1. Audit `RouteConfig` and `StateConfig` in `schema.py` to understand the parse-time freeze point.
2. Pick the lightest approach (context interpolation is probably the smallest delta — `_resolve_route` in `executor.py:1524` already calls `interpolate()`; check if `route:` values are passed through it).
3. If interpolation already threads through `_resolve_route`, the only change may be allowing `context.*` refs in route values and documenting it.
4. Add tests verifying a context variable redirects routing to the expected state.
5. Update `LOOPS_REFERENCE.md` with the new syntax.
6. Update `docs/guides/LOOPS_GUIDE.md`, `docs/reference/CLI.md`, and `docs/reference/API.md` (see Documentation subsection in Integration Map).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Apply the `${...}` filter at the error-emission site in `validate_fsm` (validation.py ~line 959-964), NOT inside `get_referenced_states`** — `get_referenced_states()` feeds `_find_reachable_states`, `_dominated_by_any`, `_find_bypass_path_any`, and `_validate_artifact_overwrite`; modifying it would break graph-traversal correctness for those callers. Only skip the unknown-state error when `ref` matches `^\$\{[^}]+\}` or `VARIABLE_PATTERN` at the emit site.
- Add tests to `test_fsm_validation.py` — this file directly tests `validate_fsm` and is the canonical location for the validator-skip tests (in addition to the `test_fsm_schema.py` tests already planned).
- Add a pre-run scan test to `test_ll_loop_errors.py` — mirrors `TestMissingContextVariables.test_missing_context_input_clear_error` (line 248) but with the missing context key referenced in a route value rather than an action.
- `docs/guides/LOOPS_GUIDE.md`, `docs/reference/CLI.md`, `docs/reference/API.md` — three additional doc files need updating beyond `LOOPS_REFERENCE.md`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical discovery — Option 1 runtime is already implemented:**
`_resolve_route()` at `scripts/little_loops/fsm/executor.py:1524` unconditionally calls `interpolate(route, ctx)` for every route target string. The `InterpolationContext` includes `self.fsm.context`, which holds all `--context KEY=VALUE` CLI overrides by the time routing fires. This means a route value like `${context.override_state}` already resolves correctly at runtime — **no executor changes are required for Option 1**.

**Two blockers to fix for Option 1:**
1. **Validator rejects `${...}` tokens as unknown states** — `StateConfig.get_referenced_states()` at `scripts/little_loops/fsm/schema.py:621` returns raw route value strings including `${...}` templates; `validate_fsm()` in `scripts/little_loops/fsm/validation.py` checks these against `fsm.states` keys, so `${context.foo}` is flagged as "referenced unknown state". Fix: skip strings matching the interpolation pattern (`^\$\{[^}]+\}$` or `VARIABLE_PATTERN` from `interpolation.py`) in the unknown-state check.
2. **Pre-run context scan misses route values** — `cmd_run()` at `scripts/little_loops/cli/loop/run.py:232–249` scans only `state.action` and `state.evaluate.prompt` for `${context.<key>}` refs; missing keys in route values produce an `InterpolationError` at routing time rather than a helpful pre-run message. Fix: extend `templates` list in that scan to include `state.route.routes.values()`, `state.route.default`, `state.route.error`, and the shorthand fields (`on_yes`, `on_no`, etc.).

**Interpolation syntax discrepancy in issue body:**
The `## Expected Behavior / Options` section uses `{{context.*}}` double-brace syntax, but the actual interpolation engine (`scripts/little_loops/fsm/interpolation.py:interpolate`) uses `${context.*}` dollar-brace syntax. The correct YAML authoring syntax for Option 1 is `route: { IMPLEMENT: "${context.override_implement_state}" }`.

**Option 3 model:** The `--route-override KEY=STATE` flag would follow the exact same registration pattern as `--context` in `scripts/little_loops/cli/loop/__init__.py:233–238` (`action="append"`, `metavar="KEY=VALUE"`) and the same injection loop in `cmd_run()` lines 150–154. The patch would apply to `fsm.states[state_name].route.routes[verdict] = target_state` after FSM load and before the executor is constructed.

**Correction — `_route()` line number:**
`_route()` is defined at `executor.py:1469` (Integration Map shows "~1492"; accurate anchor is 1469). All branches call `_resolve_route()`: `routes[verdict]` (line 1495), `route.default` (line 1497), `route.error` (lines 1499, 1501), `on_yes/on_no/on_error/on_partial/on_blocked` (lines 1506–1516), and `extra_routes[verdict]` (line 1520). Every routing path already threads through `interpolate()`.

**Concrete run.py fix — all fields to add to the pre-run scan:**
The pre-run scan at `run.py:236–238` must extend `templates` with ALL route-target fields per state. In addition to `state.route.routes.values()`, `state.route.default`, and `state.route.error`, also scan: `state.on_yes`, `state.on_no`, `state.on_error`, `state.on_partial`, `state.on_blocked`, and `state.extra_routes.values()`. These are all string fields resolved via `_resolve_route()` at runtime.

**Test pattern for `test_ll_loop_errors.py` route-value variant:**
Model `test_missing_context_input_clear_error` (line 248) — write a loop YAML via `tmp_path / ".loops" / "<loop>.yaml"` with `write_text`, use `monkeypatch.chdir(tmp_path)` + `patch.object(sys, "argv", ["ll-loop", "run", "<loop>"])` + `main_loop()`. The route-value variant should include a state with `route: { IMPLEMENT: "${context.next_state}" }` and assert `result == 1` with the missing key name visible in `captured.err`.

## Related

- ENH-2166 (implemented `classify + route:` pattern in rn-remediate)
- ENH-2165 (added `classify` evaluator)
- `scripts/little_loops/fsm/schema.py` — `RouteConfig`, `StateConfig`
- `scripts/little_loops/fsm/executor.py` — `_route()` (line 1469), `_resolve_route()` (line 1524)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — `RouteConfig`, `StateConfig` (parse-time freeze point)
- `scripts/little_loops/fsm/executor.py` — `_route()` (line 1469), `_resolve_route()` (line 1524)
- `docs/guides/LOOPS_REFERENCE.md` — document new route syntax

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation.py` — `StateConfig.get_referenced_states()` extracts raw route value strings and `validate_fsm()` checks them against `fsm.states` keys; must be updated for Option 1 to skip `${...}` placeholders rather than rejecting them as unknown states
- `scripts/little_loops/cli/loop/run.py:cmd_run` (line 89) — loads and validates FSM, injects `--context KEY=VALUE` into `fsm.context` at line 154; pre-run context scan at lines 232–249 covers only `state.action` and `state.evaluate.prompt` (not route values) — must extend to route values for Option 1
- `scripts/little_loops/cli/loop/__init__.py:run_parser` (lines 233–238) — defines `--context` flag; serves as the `add_argument` model for the new `--route-override` flag needed by Option 3

### Similar Patterns
- Existing `interpolate()` usage throughout `executor.py` for context-variable substitution in action and prompt fields
- `scripts/little_loops/fsm/executor.py:_resolve_route` (line 1524): already calls `interpolate(route, ctx)` for every route target value — the runtime mechanism for Option 1 exists today; no executor changes needed
- `scripts/little_loops/fsm/schema.py:EvaluateConfig.tolerance` typed as `float | str | None` to support `${context.*}` substitution — the same pattern of making a schema field accept template syntax applies to Option 1
- `scripts/little_loops/loops/rl-bandit.yaml` — `target: "${context.reward_target}"` under `evaluate:` shows existing `${context.*}` usage in non-action config fields (closest precedent for route value interpolation)
- `scripts/tests/test_fsm_schema.py:test_current_state_reference_allowed` (line 945) — shows the pattern for teaching the validator to allow a special token in route values; same mechanism needed for `${...}` placeholders

### Tests
- `scripts/tests/test_fsm_executor.py` — existing routing tests; add test verifying `${context.override_state}` in a route value resolves correctly; follow `TestActionTypeMcpTool._make_mcp_fsm()` pattern (line 419) for inline FSM construction with `FSMLoop` + `StateConfig` + `RouteConfig`
- `scripts/tests/test_fsm_interpolation.py` — existing interpolation unit tests; add test for context key resolving to a state name string via `InterpolationContext`
- `scripts/tests/test_fsm_schema.py` — add test that `validate_fsm()` does NOT flag `${context.*}` tokens as unknown states (follow `test_current_state_reference_allowed` at line 945 as the pattern); also add tests for `get_referenced_states()` excluding `${...}` tokens from its returned set; models: `TestFSMValidation.test_current_state_reference_allowed` (line 945), `TestEvaluatorValidation.test_convergence_interpolation_tolerance_skips_validation` (line 1390)
- `scripts/tests/test_fsm_validation.py` — directly tests `validate_fsm`; add a test that `${context.*}` tokens in `route.routes` values, `route.default`, `on_yes`, and `on_no` do NOT produce unknown-state errors (follow `TestExtraRoutesReachability` at line 50 as the structural model) [Wiring pass added by `/ll:wire-issue`]
- `scripts/tests/test_ll_loop_errors.py` — add a test that the pre-run context scan in `cmd_run` catches a `${context.target_state}` reference in a route value when `--context target_state=...` is missing; model: `TestMissingContextVariables.test_missing_context_input_clear_error` (line 248) [Wiring pass added by `/ll:wire-issue`]
- `scripts/tests/test_ll_loop_execution.py` — integration test that a loop with a `${context.override_state}` route value executes correctly end-to-end when `--context override_state=target_state` is supplied

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — new syntax section for external/runtime route configuration
- `docs/guides/LOOPS_GUIDE.md` — Variable Interpolation section (line 336) already mentions routing targets; add a sentence that `ll-loop validate` now accepts `${...}` tokens in route values [Wiring pass added by `/ll:wire-issue`]
- `docs/reference/CLI.md` — `ll-loop validate` description (~line 603) currently says "All referenced states exist"; add a note that `${...}` interpolation tokens are excluded from this check [Wiring pass added by `/ll:wire-issue`]
- `docs/reference/API.md` — `RouteConfig` entry (lines 4434-4437) shows only static string values in examples; add a note that route values accept `${context.*}` interpolation syntax [Wiring pass added by `/ll:wire-issue`]

### Configuration
- N/A

## Impact

- **Priority**: P3 - Medium priority enhancement; route configuration flexibility is valuable for loop authors but not blocking core functionality
- **Effort**: Small - Two focused fixes (skip `${...}` tokens in `validation.py` unknown-state check; extend pre-run context scan in `run.py` to include route values)
- **Risk**: Low - Additive changes only; existing loops with static `route:` dicts execute unchanged; runtime interpolation mechanism already exists
- **Breaking Change**: No

## Labels

`enhancement`, `fsm`, `routing`, `interpolation`

## Status

**Open** | Created: 2026-06-19 | Priority: P3

---

## Session Log
- `/ll:refine-issue` - 2026-06-19T15:48:58 - `9dc761a6-9b86-4ce1-ad31-5b60a51c47f0.jsonl`
- `/ll:format-issue` - 2026-06-19T15:43:21 - `5ffca186-abfe-4185-97e9-e6ae830e10ed.jsonl`
- `/ll:wire-issue` - 2026-06-19T03:51:37 - `abbe9067-db8f-4d7c-8849-5d5a1e2a7ead.jsonl`
- `/ll:decide-issue` - 2026-06-19T03:40:58 - `2a4d8a56-cb18-4817-9724-740e4c1e15f7.jsonl`
- `/ll:refine-issue` - 2026-06-19T03:30:42 - `7246f1b0-c60a-4639-aac4-6038698839cb.jsonl`
- `/ll:format-issue` - 2026-06-19T03:21:02 - `efc645e0-778e-4fbf-9f70-b32df76a91bc.jsonl`
- `/ll:capture-issue` - 2026-06-19T03:17:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/546354e6-5520-427c-b4d8-a9c8a1f4198c.jsonl`
