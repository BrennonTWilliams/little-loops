---
id: ENH-1908
type: ENH
priority: P3
status: open
captured_at: '2026-06-03T20:51:54Z'
discovered_date: '2026-06-03'
discovered_by: capture-issue
labels:
- fsm
- fragments
- loops
- dx
decision_needed: false
confidence_score: 96
outcome_confidence: 75
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 16
---

# ENH-1908: Parameterize FSM fragments via runtime params/with bindings

## Summary

FSM shared-state fragments (`scripts/little_loops/loops/lib/*.yaml`) have no
parameterization contract. They are pure YAML mixins resolved at parse time by
`resolve_fragments` (`scripts/little_loops/fsm/fragments.py`) via deep-merge,
with values injected only through ad-hoc runtime `${context.X}` interpolation
documented in prose `description:` fields. There is no typed/required/default
parameter declaration and no validation that a caller supplied the values a
fragment needs — so fragments like `retry_counter` silently misbehave when a
context key is unset, and two states using the same fragment collide on shared
context keys (e.g. `counter_key`).

Add a runtime parameterization mechanism for fragments by **reusing the existing
`ParameterSpec` + `with:` model** already used for sub-loops, rather than
inventing a parallel parse-time system.

## Current Behavior

A fragment "parameterizes" only two ways today, neither enforced:

1. **State-level key override (deep-merge).** A state supplies top-level fields
   (`action`, `on_yes`, `on_no`) that win over the fragment's. Works for direct
   fields; no contract.
2. **Runtime `${context.X}` interpolation.** For values spliced into the
   *interior* of a fragment-owned string (e.g. `retry_counter`'s
   `${context.max_retries}` in `evaluate.target`, or `ll_rubric_score`'s
   `${context.run_dir}`). The fragment hardcodes the placeholder and *hopes* the
   loop's `context:` block (or a runtime injection) defines it.

Failure modes:
- **Silent failure (no enforcement).** `retry_counter`'s `description` says
  "State must supply (via context interpolation): context.counter_key,
  context.max_retries" — but nothing checks it. A loop that forgets silently
  produces wrong behavior at runtime.
- **Cross-reference collision (no per-reference scoping).** Two states using
  `retry_counter` in one loop share `context.counter_key` → shared counter-file
  corruption (the same class of bug the MR-3 / `run_dir` isolation rules fight).
- **No defaults / types.** A fragment cannot declare `max_retries` defaults to 3
  or that it must be an integer.

## Expected Behavior

A fragment declares typed inputs and a reference binds them, with the contract
enforced at validation time and resolution deferred to runtime:

```yaml
# fragment def (lib/common.yaml)
retry_counter:
  parameters:
    counter_key: {type: string, required: true}
    max_retries: {type: integer, default: 3}
  action: |
    FILE=".loops/tmp/${param.counter_key}"
    N=$(cat "$FILE" 2>/dev/null || echo 0); N=$((N+1))
    printf '%s' "$N" > "$FILE"; echo "$N"
  action_type: shell
  evaluate: {type: output_numeric, operator: lt, target: "${param.max_retries}"}

# usage — two states, no collision, no loop-global context: pollution
lint_retry:
  fragment: retry_counter
  with: {counter_key: lint_retries, max_retries: 5}
  on_yes: lint
  on_no: give_up
```

- Missing required params → validation ERROR (not silent runtime failure).
- Each reference's `with:` bindings are scoped to that state's `${param.X}`
  namespace, so two references never collide.
- `ParameterSpec.default` supplies optional values; type is checked.
- Deep-merge override stays for plain state fields (`on_yes`, `action`); `with:`
  is only for values spliced into the fragment's interior. Two non-overlapping
  channels, each with one job.

## Motivation

Fragments have limited reuse value without a real parameter contract — the
current prose-only convention pushes the cost of every fragment's implicit
dependencies onto every caller, and the failures are silent. The sub-loop system
already solved this exact problem with `ParameterSpec` (`type`/`required`/
`default`/`enum values`) + `with:` bindings + three-layer validation
(`_validate_parameters`, `_validate_with_bindings`, runtime enforcement in
`_execute_sub_loop`). Extending that one model to fragments gives a single mental
model — *anything reusable declares `parameters:`; any reference binds via
`with:`* — instead of two parallel systems.

## Key design finding: resolution MUST be at runtime, not parse time

An initial design considered resolving fragment params at **parse time** (inside
`resolve_fragments`, substituting a `${param.X}` namespace and expanding it away
before the dataclass exists). An audit of every interpolation reference in every
`lib/*.yaml` fragment **disproves** that this is sufficient:

- `ll_rubric_score` interpolates `${context.run_dir}`. Per `.claude/CLAUDE.md`,
  **the runner injects `run_dir` as `.loops/runs/<loop>-<timestamp>/` at
  execution start** — it is constant for the loop instance but **not knowable
  when `resolve_fragments` runs**. A parse-time substitution would have nothing
  to substitute.
- `playwright_screenshot` (`file_url`, `screenshot_path`, typically derived from
  `run_dir`) and `ll_commit` (`commit_message`, typically generated) follow the
  same "constant-per-loop but runtime-only" pattern.
- `retry_counter` (`counter_key`, `max_retries`) and `ll_loop_run` (`loop_name`)
  are the only genuine parse-time constants.

So fragment params must resolve at **runtime** (when `run_dir`, `captured.*`,
etc. are all available). This one decision also means a naive parse-time
`requires:` validator would **false-positive on `run_dir`** (flag it "missing"
because it is runner-injected, not authored) — any validation must be
runtime-injection-aware or whitelist runner-injected vars.

Audit detail: no fragment *executable body* references `prev`/`result`/`state`/
`loop`/`env`/`messages`; only `context.*`. `captured.*` appears only in
`parse_tagged_json`'s prose (it deliberately ships no default `action`).

## Proposed Solution

Extend the runtime `parameters:` / `with:` model to fragment references:

1. Fragments may declare a top-level `parameters:` block per fragment, reusing
   the existing `ParameterSpec` dataclass (`schema.py`) verbatim.
2. A state's `fragment:` reference may carry a `with:` map binding those params
   (same keyword as sub-loop calls).
3. `resolve_fragments` merges the fragment body into the state (as today) and
   carries the `with:` bindings onto the resulting `StateConfig` (new field —
   **not** the existing `params:` field, which holds MCP tool args; use a
   distinct name e.g. `fragment_bindings`).
4. The executor exposes bindings as a `${param.X}` namespace in the per-state
   `InterpolationContext`, applying `ParameterSpec` defaults / required-checks /
   type validation at runtime (mirror `_execute_sub_loop` logic).
5. Add cross-validation (analogous to `_validate_with_bindings`) so unknown
   bindings and missing required params are caught at `load_and_validate`.

### Rejected alternatives

- **Parse-time-only `${param}` substitution** — rejected: cannot serve the
  `run_dir`/`file_url` class of runtime-injected per-loop constants (see finding
  above).
- **Validation-only `requires:` list** — rejected as insufficient: closes the
  silent-failure gap but delivers no actual parameterization (no per-reference
  scoping, no defaults), and false-positives on runner-injected vars.
- **Promote parameterized fragments to sub-loops** — rejected for single-state
  shapes: sub-loops are runtime black-box calls with their own executor frame /
  lifecycle / timeout, far too heavy for "a state with a hole," and cannot
  splice a single state inline into the parent's graph.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/fragments.py` — `resolve_fragments()` (line 64): carry `with:` bindings from the state dict onto the merged result; `_deep_merge()` (line 41) already handles plain fields and need not change
- `scripts/little_loops/fsm/schema.py` — `ParameterSpec` (lines 209–252): reuse verbatim; `StateConfig` (lines 354–505): add new `fragment_bindings: dict[str, Any]` field (distinct from existing `params:` which holds MCP tool args and `with_` which holds sub-loop bindings); `FSMLoop.from_dict()` (line 1022): add `parameters:` parsing to fragment definitions
- `scripts/little_loops/fsm/interpolation.py` — `InterpolationContext.resolve()` (lines 68–105): add `"param"` dispatch case alongside existing `"context"`, `"env"`, `"captured"` etc.; `InterpolationContext` dataclass (line 38): add `param: dict[str, Any]` field
- `scripts/little_loops/fsm/executor.py` — `_build_context()` (lines 1567–1584): populate `param` namespace from `state.fragment_bindings` with defaults applied and required-checks enforced (mirror `_execute_sub_loop()` lines 524–545)
- `scripts/little_loops/fsm/validation.py` — add `_validate_fragment_bindings()` analogous to `_validate_with_bindings()` (lines 327–401); runner-injected-var (`run_dir`) whitelist needed to avoid false-positive required-param errors

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `parameters:` key to `fragments.additionalProperties` sub-schema (referencing `parameterSpec`); update `stateConfig.with` description from "Only valid when 'loop' is set" to also cover fragment references [Agent 2 finding]
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — `score` state uses `fragment: ll_rubric_score` with no `with:` bindings; must add `with: {run_dir: "${context.run_dir}", ...}` after `ll_rubric_score` gains required params, or `load_and_validate` and `test_builtin_loops.py` will fail [Agent 1 finding]

### Fragment Files to Migrate
- `scripts/little_loops/loops/lib/common.yaml` — `retry_counter` fragment (lines 23–38): migrate `${context.counter_key}` and `${context.max_retries}` in `action` and `evaluate.target` to `parameters:` block + `${param.X}` namespace
- `scripts/little_loops/loops/lib/harness.yaml` — `ll_rubric_score` fragment: migrate `${context.run_dir}`, `${context.rubric}`, `${context.pass_threshold}` to `parameters:` + `${param.X}` (note: `run_dir` is runner-injected, so caller binds it via `with: {run_dir: "${context.run_dir}"}`)
- `scripts/little_loops/loops/lib/cli.yaml` — `ll_loop_run` fragment (line 130, `${context.loop_name}`): bonus migration candidate, same pattern

### Dependent Files (Callers/Importers)
- Any loop YAML using `fragment: retry_counter` or `fragment: ll_rubric_score` — will need `with:` bindings added after migration (opt-in; fragments without `parameters:` are unchanged)
- ~35 loops across `scripts/little_loops/loops/` use `fragment:` states; only those referencing migrated fragments need changes

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — confirmed user of `fragment: ll_rubric_score` at `score` state; the only built-in loop referencing this fragment; will need `with:` bindings post-migration [Agent 1 finding]
- 30 loops total use `fragment:` states (Agent 1 enumerated all); no other built-in loop uses `fragment: retry_counter` or `fragment: ll_rubric_score` per grep results

### Similar Patterns
- Sub-loop `with:` pipeline (exact model to mirror): `executor.py:_execute_sub_loop()` lines 524–545 — interpolate → apply defaults → enforce required → merge into context
- Static cross-validation: `validation.py:_validate_with_bindings()` lines 327–401 — unknown key check (lines 361–371), missing required check (lines 374–384), type check (lines 387–399); static check skips `"${"` values (interpolated at runtime)
- `ParameterSpec` parsing pattern: `schema.py:FSMLoop.from_dict()` lines 1041–1043

### Tests
- `scripts/tests/test_fsm_fragments.py` — extend existing file; pattern: `TestCommonYamlNewFragments` (line 522) for real-YAML integration; `_write_lib()` helper for unit tests
- `scripts/tests/test_fsm_executor.py` — extend; primary model is `TestSubLoopWithBindings` (line 6277) with `MockActionRunner` (line 31) and `_write_child()` helper pattern
- `scripts/tests/test_fsm_validation.py` — extend for `_validate_fragment_bindings()` coverage
- `scripts/tests/test_fsm_schema.py` — extend `TestParameterSpec` (line 2365) for `fragment_bindings` field round-trip

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_interpolation.py` — extend for `param` namespace dispatch in `InterpolationContext.resolve()` after `param: dict[str, Any]` field is added [Agent 1 finding]
- `scripts/tests/test_builtin_loops.py` — calls `load_and_validate` on all built-in loops; will fail for `generator-evaluator.yaml` if `ll_rubric_score` gains required params but the loop YAML is not updated with `with:` bindings — update this loop as part of the migrate step [Agent 3 finding]
- `scripts/tests/test_fsm_fragments.py` — `TestLlRubricScoreFragment.test_ll_rubric_score_resolves_in_loop` (line 1492) calls `resolve_fragments` with no `with:` bindings; safe as long as the resolved dict structure is unchanged, but must add `with:` bindings if the test is extended to call `load_and_validate` [Agent 3 finding]

### Documentation
- N/A — no user-facing docs reference fragment parameterization contract

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `StateConfig` field table missing `fragment_bindings`; `InterpolationContext` field table and supported-namespaces table missing `param` namespace entry [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — `fragment:` key description (line 330) says "parse-time only" — inaccurate for parameterized fragments; `### Typed parameter bindings` section covers `with:` for sub-loops only [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — "parse-time only" statement (line 3304) becomes partially inaccurate; `retry_counter` usage example (line 3119) becomes outdated post-migration; fragment catalog entries list `context:` keys rather than `with:` bindings [Agent 2 finding]
- `skills/create-loop/reference.md` — `#### fragment (Optional)` section says "parse-time only"; `### lib/common.yaml fragments` table `retry_counter` row and `### lib/harness.yaml fragments` table `ll_rubric_score` row describe wrong "Caller must supply" channel [Agent 2 finding]

### Configuration
- N/A

## API/Interface

New YAML authoring contract for fragments (opt-in; existing fragments unchanged):

```yaml
# Fragment definition — new top-level `parameters:` block
retry_counter:
  parameters:
    counter_key: {type: string, required: true}
    max_retries: {type: integer, default: 3}
  action: ...

# Fragment reference — new optional `with:` map on the state
lint_retry:
  fragment: retry_counter
  with: {counter_key: lint_retries, max_retries: 5}
```

New Python surface:
- `StateConfig.fragment_bindings: dict[str, Any]` — new field on `StateConfig` (schema.py line ~433 region) carrying `with:` bindings from a fragment reference. **Distinct from** `StateConfig.with_` (YAML `with:` for sub-loop states, line 433) and `StateConfig.params` (MCP tool args). In `from_dict()`, populate `fragment_bindings` when `data.get("fragment")` is set, `with_` when `data.get("loop")` is set — a state cannot have both.
- `InterpolationContext.param: dict[str, Any]` — new field (interpolation.py line ~38 region); `resolve()` dispatches `"param"` namespace to this dict. **Deliberately separate from `context`** — unlike sub-loop bindings which land in `context` (executor.py line 545), fragment bindings get their own namespace to avoid `context:` pollution and enable per-state scoping.
- `load_and_validate` — new cross-validation pass `_validate_fragment_bindings()`: unknown bindings flagged, missing required params flagged, runner-injected vars (`run_dir`, `started_at`, `loop_name`) whitelisted to avoid false-positive required-param errors at static check time

## Implementation Steps

1. **`schema.py`**: Add `fragment_bindings: dict[str, Any] = field(default_factory=dict)` to `StateConfig` (near line 433 after `with_`). In `StateConfig.from_dict()`, populate it from `data.get("with", {})` when `data.get("fragment")` is set. Add `fragment_bindings` to `to_dict()`. Fragment-level `parameters:` parsing already works via `ParameterSpec.from_dict()` (line 244) — fragments are dicts in the lib YAMLs, not `FSMLoop` objects, so parsing happens in `resolve_fragments` not `FSMLoop.from_dict`.

2. **`fragments.py`**: In `resolve_fragments()` (line 64), after `_deep_merge(frag_copy, state_dict)` (line 138), extract the `"with"` key from the merged result before removing `"fragment"` — store it as `"fragment_bindings"` in the resulting state dict so `StateConfig.from_dict()` picks it up. Also parse and validate any `parameters:` block on the fragment definition (store alongside merged state or carry separately for cross-validation).

3. **`interpolation.py`**: Add `param: dict[str, Any] = field(default_factory=dict)` to `InterpolationContext` (line 38). In `resolve()` (line 68), add a `"param"` dispatch branch: `elif namespace == "param": return _get_nested(self.param, path, ...)`.

4. **`executor.py`**: In `_build_context()` (line 1567), after constructing `InterpolationContext`, populate `param` from `state.fragment_bindings` with defaults applied and required checked — mirror the `_execute_sub_loop()` pattern at lines 524–545: interpolate values, apply `param_spec.default` for unbound optional params, raise `ValueError` for missing required params.

5. **`validation.py`**: Add `_validate_fragment_bindings(fsm, loop_dir)` called from `load_and_validate()` alongside `_validate_with_bindings()` (line 1474). Structure mirrors `_validate_with_bindings()` (lines 327–401): iterate states with `state.fragment is not None`, load fragment's `parameters:` dict, check unknown keys, check missing required keys, skip static type check for `"${"` values. Whitelist runner-injected vars (`run_dir`, `loop_name`, `started_at`) from required-param errors.

6. **Migrate + test**: Update `retry_counter` in `lib/common.yaml` (lines 23–38) to use `parameters:` + `${param.counter_key}` / `${param.max_retries}`. Update `ll_rubric_score` in `lib/harness.yaml` similarly. Add tests in `test_fsm_fragments.py` extending `TestCommonYamlNewFragments` (line 522) and in `test_fsm_executor.py` extending `TestSubLoopWithBindings` (line 6277) covering: missing required → `ValueError`, default applied, two states with same fragment + distinct `counter_key` bindings do not share a counter file, `run_dir` binding resolves at runtime.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/fsm/fsm-loop-schema.json` — add `parameters:` to `fragments.additionalProperties` sub-schema referencing existing `parameterSpec` definition; update `stateConfig.with` description from "Only valid when 'loop' is set" to "Valid when 'loop' is set (sub-loop) or 'fragment' is set (fragment binding)"
8. Update `scripts/little_loops/loops/oracles/generator-evaluator.yaml` — add `with:` bindings to `score` state's `fragment: ll_rubric_score` reference (e.g. `with: {run_dir: "${context.run_dir}", rubric: ..., pass_threshold: ...}`) so `load_and_validate` and `test_builtin_loops.py` continue to pass
9. Extend `scripts/tests/test_fsm_interpolation.py` — add tests for `param` namespace dispatch in `InterpolationContext.resolve()`
10. Update docs: `docs/reference/API.md` (add `fragment_bindings`/`param` to field tables), `docs/generalized-fsm-loop.md` (fix "parse-time only" on `fragment:` and `with:` sections), `docs/guides/LOOPS_GUIDE.md` (fix line 3304 statement, update fragment catalog), `skills/create-loop/reference.md` (fix `fragment` section and catalog rows for `retry_counter`/`ll_rubric_score`)

## Backwards Compatibility

Additive. Existing fragments using `${context.X}` keep working (context
interpolation is unchanged); `parameters:`/`with:` on fragments is opt-in.
Migrate fragments opportunistically.

## Success Metrics

- A fragment with a `required` param errors at validation when unbound (no
  silent runtime failure).
- Two states using `retry_counter` with distinct `counter_key` bindings do not
  share a counter file.
- `ll_rubric_score` migrated to `${param.run_dir}` still resolves at runtime.

## Scope Boundaries

- In: fragment `parameters:`/`with:`, runtime `param` namespace, validation,
  migration of `retry_counter` + `ll_rubric_score`.
- Out: changing the sub-loop param system; mutating the deep-merge override
  channel for plain fields; auto-migrating all fragments.

## Impact

- **Priority**: P3 — medium-priority DX enhancement; silent fragment failures are a real pain point but non-blocking for current work
- **Effort**: Medium — touches 5 core FSM files and `lib/` fragment defs, but reuses `ParameterSpec` dataclass and existing interpolation engine verbatim; net new surface is small
- **Risk**: Low — fully additive and opt-in; existing `${context.X}` interpolation is unchanged; no breaking changes to callers
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` § Loop Authoring | Meta-loop / `run_dir` isolation rules; run_dir injection |
| `docs/reference/API.md` | `little_loops.fsm.*` module reference |

## Labels

fsm, fragments, loops, dx

## Session Log
- `/ll:ready-issue` - 2026-06-03T22:52:59 - `d193d018-be06-4883-8cf3-cffe37701288.jsonl`
- `/ll:confidence-check` - 2026-06-03T23:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/90c5e727-ed9a-45d8-88a6-ae460a5218af.jsonl`
- `/ll:wire-issue` - 2026-06-03T22:48:35 - `5897e8be-dce8-424a-bce0-7c0623343503.jsonl`
- `/ll:refine-issue` - 2026-06-03T22:40:51 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:format-issue` - 2026-06-03T21:01:44 - `b833547d-130c-42f1-b9a5-75900748b2de.jsonl`
- `/ll:capture-issue` - 2026-06-03T20:51:54Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b1cd9a64-5656-4d3a-9168-942bbb1958da.jsonl`

## Status

open
