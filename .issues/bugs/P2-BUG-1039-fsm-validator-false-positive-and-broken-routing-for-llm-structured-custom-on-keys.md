---
discovered_commit: 31d60756
discovered_branch: main
discovered_date: 2026-04-11T00:00:00Z
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 71
---

# BUG-1039: FSM validator false-positive and broken routing for `llm_structured` custom `on_*` keys

## Summary

Users can define `llm_structured` evaluators with a custom `schema` that returns non-standard verdicts (e.g., `done`, `complete`, `continue`). The natural routing pattern is `on_<verdict>: target_state` (e.g., `on_done: final`). Two bugs exist: (1) `ll-loop validate` fires a false-positive "State is not reachable" warning for any state only referenced via a custom `on_*` key, and (2) at runtime, custom `on_*` routing resolves to `None` and fails with "No valid transition". The feature is completely non-functional end-to-end.

## Location

- **File**: `scripts/little_loops/fsm/schema.py`
- **Lines**: 284–317 (`StateConfig.from_dict()` — drops unrecognized `on_*` keys)
- **Lines**: 319–350 (`get_referenced_states()` — never sees custom keys)
- **File**: `scripts/little_loops/fsm/executor.py`
- **Lines**: 746–758 (`_route()` — hardcoded shorthand list, no dynamic fallback)
- **File**: `scripts/little_loops/fsm/validation.py`
- **Lines**: 419–446 (`_find_reachable_states()` BFS — misses custom targets)
- **Lines**: 244–250 (`_validate_state_routing()` `has_shorthand` check — also missing `on_blocked`)

## Steps to Reproduce

1. Define a loop YAML using an `llm_structured` evaluator with a custom `schema` that returns non-standard verdicts (e.g., `done`, `retry`).
2. Add `on_done: final` / `on_retry: check` routing keys on the evaluating state.
3. Run `ll-loop validate` — observe false-positive warning: `State 'final' is not reachable`.
4. Run the loop; when the evaluator returns verdict `done`, observe runtime error: `No valid transition for verdict 'done'`.

## Current Behavior

Given a loop YAML:
```yaml
check:
  evaluate:
    type: llm_structured
    schema:
      properties:
        verdict: { type: string, enum: [done, retry] }
  on_done: final
  on_retry: check
final:
  terminal: true
```

1. `ll-loop validate` warns: `State 'final' is not reachable` (false positive)
2. Running the loop and receiving verdict `done` fails at runtime: `No valid transition for verdict 'done'`

## Expected Behavior

1. `ll-loop validate` reports zero warnings for `final`.
2. A verdict of `done` routes to `final` at runtime.

## Motivation

The `llm_structured` + custom schema pattern is the primary way to give loops type-safe, domain-specific verdict routing. Any loop author using non-standard verdicts (e.g., `done`/`retry` instead of `yes`/`no`) cannot route at all — the feature is completely non-functional end-to-end. This blocks a core use case for structured LLM evaluation loops and produces misleading validator warnings that erode trust in `ll-loop validate`.

## Root Cause

Two-layer gap in how `on_*` keys are handled:

**Layer 1 — Schema deserialization (`schema.py:284–317`)**: `StateConfig.from_dict()` only extracts a hardcoded set of `on_*` keys (`on_yes`, `on_success`, `on_no`, `on_failure`, `on_error`, `on_partial`, `on_blocked`, `on_maintain`, `on_retry_exhausted`). Any other `on_*` key (e.g., `on_done`, `on_complete`) is silently dropped — the target state name is never stored.

**Layer 2 — Reachability analysis (`validation.py:419–446` + `schema.py:319–350`)**: `_find_reachable_states()` uses BFS over `StateConfig.get_referenced_states()`. That method only iterates the known attributes above, plus `route.routes.values()`. Because `on_done` was already dropped in Layer 1, `final` never enters the BFS frontier and is marked unreachable.

**Layer 3 — Runtime routing (`executor.py:746–758`)**: `_route()` has the same hardcoded shorthand logic. A custom `on_done` key returns `None` → "No valid transition" error at runtime.

## Proposed Solution

Add `extra_routes: dict[str, str]` to `StateConfig` to capture any `on_*` key not in the hardcoded set, storing it as `verdict_str → target_state`.

### `schema.py` — add field + update three methods

```python
# Field (after on_retry_exhausted)
extra_routes: dict[str, str] = field(default_factory=dict)
```

```python
# from_dict() — collect unknown on_* keys
KNOWN_ON_KEYS = {
    "on_yes", "on_success", "on_no", "on_failure",
    "on_error", "on_partial", "on_blocked",
    "on_maintain", "on_retry_exhausted",
}
extra_routes = {}
for key, val in data.items():
    if key.startswith("on_") and key not in KNOWN_ON_KEYS and isinstance(val, str):
        extra_routes[key[3:]] = val  # strip "on_" prefix → verdict key
```

```python
# get_referenced_states() — include extra_routes targets
refs.update(self.extra_routes.values())
```

```python
# to_dict() — round-trip serialize back to on_* keys
for verdict, target in self.extra_routes.items():
    result[f"on_{verdict}"] = target
```

### `executor.py` — add dynamic fallback in `_route()`

After the hardcoded shorthand block (line ~756), before `return None`:

```python
# Dynamic on_<verdict> shorthands from extra_routes
if verdict in state.extra_routes:
    return self._resolve_route(state.extra_routes[verdict], ctx)
```

### `validation.py` — include `extra_routes` in `has_shorthand`

```python
has_shorthand = (
    state.on_yes is not None
    or state.on_no is not None
    or state.on_error is not None
    or state.on_partial is not None
    or bool(state.extra_routes)   # ← add this
)
```

*Note: `on_blocked` is also currently missing from `has_shorthand` — a separate minor omission.*

## Implementation Steps

1. In `schema.py`, add `extra_routes: dict[str, str] = field(default_factory=dict)` to `StateConfig` after the `on_retry_exhausted` field.
2. In `StateConfig.from_dict()`, after parsing known `on_*` keys, loop over remaining `on_*` keys and populate `extra_routes` (strip `on_` prefix).
3. In `StateConfig.get_referenced_states()`, add `refs.update(self.extra_routes.values())`.
4. In `StateConfig.to_dict()`, serialize `extra_routes` back as `on_<verdict>` keys for round-trip fidelity.
5. In `executor.py:_route()`, after the hardcoded shorthand block, add a lookup in `state.extra_routes` before returning `None`.
6. In `validation.py:_validate_state_routing()`, add `or bool(state.extra_routes)` to the `has_shorthand` expression.
7. In `scripts/little_loops/fsm/fsm-loop-schema.json`, update the state object definition (lines 202–286) to allow custom `on_*` keys — add `"patternProperties": {"^on_": {"type": "string"}}` alongside the existing explicit `on_*` property declarations. Confirm `"additionalProperties": false` is either removed or that the pattern covers the custom keys.
8. Add a fixture loop YAML `scripts/tests/fixtures/fsm/custom-on-routing.yaml` with `llm_structured` + custom schema + `on_done: final` / `on_retry: check`, modeled on `scripts/tests/fixtures/fsm/valid-loop.yaml`.
9. Add tests to `scripts/tests/test_fsm_schema.py` verifying `extra_routes` targets appear in `get_referenced_states()` and round-trip through `to_dict()`, modeled on the `on_blocked` six-test battery at lines 342–398.
10. Create `scripts/tests/test_fsm_validation.py` (new file) and add a reachability test for `extra_routes` targets, modeled on `test_unreachable_state_warning` in `test_fsm_schema.py:674–688`.
11. Add a test to `scripts/tests/test_fsm_executor.py` verifying `_route()` dispatches custom `on_*` verdicts via `extra_routes`, modeled on `on_partial` shorthand routing tests at lines 1048–1113 (3-test pattern: shorthand routes correctly, shorthand routes to fix state, missing shorthand falls through to error).
12. Run `python -m pytest scripts/tests/ -k "fsm_schema or fsm_executor or fsm_validation" -v`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

13. Update `scripts/little_loops/cli/loop/testing.py:140–153` — add `elif verdict in state.extra_routes: next_state = state.extra_routes[verdict]` branch to the inline routing block in `cmd_test`; matches the `_route()` fix in step 5
14. Update `scripts/little_loops/cli/loop/layout.py:187–210` — add `for verdict, target in state.extra_routes.items(): edges.append(...)` iteration in `_collect_edges()` so custom `on_*` edges appear in `ll-loop show` diagrams
15. Update `docs/generalized-fsm-loop.md:253–255, 445` — add custom `on_<verdict>` pattern to shorthand enumeration and Resolution Order section
16. Update `docs/guides/LOOPS_GUIDE.md:635` — add custom `on_<verdict>` to the shorthand enumeration line
17. Update `skills/review-loop/SKILL.md:198` — add `or bool(state.extra_routes)` to the QC-13 dead-end check condition so states with only custom routing are not flagged as dead-ends
18. Add `test_validate_with_custom_on_routing_no_false_positive` to `scripts/tests/test_ll_loop_commands.py` modeled on `test_validate_with_unreachable_state_prints_warning` at line 75 — verifies that `on_done: final` does not produce a false-positive warning

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `extra_routes` field to `StateConfig`; update `from_dict()`, `get_referenced_states()`, `to_dict()`
- `scripts/little_loops/fsm/executor.py` — update `_route()` to fall back to `extra_routes` before returning `None`
- `scripts/little_loops/fsm/validation.py` — update `_validate_state_routing()` `has_shorthand` check to include `extra_routes`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `patternProperties: {"^on_": {"type": "string"}}` to stateConfig definition; remove or relax `"additionalProperties": false` [_Wiring pass added by `/ll:wire-issue`:_]
- `scripts/little_loops/cli/loop/testing.py:140–153` — `cmd_test` inline routing hardcodes `on_yes`/`on_no`/`on_error` only; no `extra_routes` fallback — custom verdicts silently produce "no route" in dry-run testing [_Wiring pass added by `/ll:wire-issue`:_]
- `scripts/little_loops/cli/loop/layout.py:187–210` — `_collect_edges()` enumerates shorthand fields one-by-one; does not iterate `extra_routes` so custom `on_*` edges are absent from `ll-loop show` FSM diagrams [_Wiring pass added by `/ll:wire-issue`:_]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation.py:440` — calls `state.get_referenced_states()` inside `_find_reachable_states()` BFS (direct consumer of the gap)
- `scripts/little_loops/fsm/fragments.py` — calls `FSMLoop.from_dict()` after fragment resolution; will benefit from round-trip fidelity fix
- `scripts/little_loops/fsm/persistence.py` — calls `FSMLoop.from_dict()` / `to_dict()` indirectly via `LoopState`
- `scripts/tests/test_fsm_schema.py` — tests `get_referenced_states()` directly (needs new `extra_routes` test cases)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py:608` — `FSMLoop.get_referenced_states()` calls `state.get_referenced_states()` on each state; will automatically benefit from the fix but confirms the fix propagates to loop-level refs
- `scripts/little_loops/fsm/validation.py:346` — second `get_referenced_states()` call site inside `validate_fsm()` for the "references unknown state" check (distinct from the BFS at line 440); both call sites benefit from the fix

### Similar Patterns
- `scripts/little_loops/fsm/schema.py:342–398` (`test_fsm_schema.py`) — `on_blocked` five-test battery is the **direct template** for `extra_routes` tests (field, `from_dict`, `to_dict`, absent-from-dict-when-None, `get_referenced_states`, roundtrip)
- `scripts/little_loops/fsm/executor.py:747–756` — hardcoded shorthand dispatch block; `extra_routes` lookup goes immediately after line 756 before `return None`
- `scripts/little_loops/fsm/schema.py:249–258` — `to_dict()` skip-if-None pattern for each `on_*` field; `extra_routes` uses a loop (`for verdict, target in self.extra_routes.items()`)
- `scripts/tests/test_fsm_executor.py:1048–1181` — `on_partial`/`on_blocked` executor routing tests are the template for the custom-verdict routing test

### Tests
- `scripts/tests/test_fsm_schema.py` — add `extra_routes` six-test battery modeled on the `on_blocked` battery at lines 342–398
- `scripts/tests/test_fsm_validation.py` — **DOES NOT EXIST; must be created as a new file**; add reachability test for `extra_routes` targets modeled on `test_unreachable_state_warning` in `test_fsm_schema.py:674–688`
- `scripts/tests/test_fsm_executor.py` — add `_route()` test for custom `on_*` verdict dispatch, modeled on `on_partial` shorthand routing tests at lines 1048–1113 (`on_blocked` mirror is at 1116–1181)
- New fixture YAML `scripts/tests/fixtures/fsm/custom-on-routing.yaml` with `llm_structured` + custom schema + `on_done: final` / `on_retry: check` (model on `valid-loop.yaml`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_commands.py:75–107` — `test_validate_with_unreachable_state_prints_warning` is the direct template; add a companion test `test_validate_with_custom_on_routing_no_false_positive` verifying that a loop with `on_done: final` does **not** emit an unreachable-state warning after the fix

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Critical: `fsm-loop-schema.json` uses `"additionalProperties": false` on state objects** (`scripts/little_loops/fsm/fsm-loop-schema.json:202–286`). The existing `on_*` keys are each declared as explicit string properties. Any custom `on_*` key not declared here will be rejected by JSON Schema validation before Python deserialization runs. **Implementation Step 7 must add an `additionalProperties`-compatible pattern or declare a catch-all `on_*` pattern** (e.g., `patternProperties: {"^on_": {"type": "string"}}`).
- `test_fsm_validation.py` does not exist — it must be created as a new test file, not added to an existing file.
- The `on_blocked` shorthand **is** handled in `executor.py:_route()` (line 755–756) but **is not** included in `validation.py:has_shorthand` (lines 244–250). The issue mentions this as a separate minor omission; including `or state.on_blocked is not None` in the `has_shorthand` fix is low-risk and removes a pre-existing false negative.
- `_resolve_route()` signature (lines 760–772): `_resolve_route(self, route: str, ctx: InterpolationContext) -> str`. The `extra_routes` fallback calls it exactly as the existing shorthand branches do: `return self._resolve_route(state.extra_routes[verdict], ctx)`.

_Second-pass refinement (verified against current code):_

- **Line number corrections**: `validation.py:has_shorthand` is at lines 245–250 (not 244–250); `_find_reachable_states()` BFS is at lines 430–444 (not 419–446); `executor.py:_route()` method is defined at line 713, shorthand block at lines 747–758.
- **`test_unreachable_state_warning` is 14 lines (674–688)**, not 674–703 as originally documented. The test structure is simple: construct an FSM with an orphan state, call `validate_fsm()`, assert a WARNING-severity result containing "not reachable".
- **`testing.py` broader shorthand gap**: The inline routing block at `testing.py:148–153` only handles 3 verdicts (`yes`, `no`, `error`). `on_partial` and `on_blocked` are also absent from this block — pre-existing gaps that exist independent of this fix. Step 13 adds the `extra_routes` branch; implementers should be aware the block was already incomplete for `on_partial`/`on_blocked`, but fixing those is out-of-scope for this issue.
- **Executor test ranges**: `on_partial` shorthand battery starts at `test_fsm_executor.py:1048`; `on_blocked` shorthand battery starts at line 1116. Both follow the same 3-test structure (shorthand routes correctly, shorthand routes to fix state, missing shorthand falls to error). The new `extra_routes` test should mirror either battery.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md:253–255` — "Shorthand for common cases" block lists only `on_yes`/`on_no`/`on_error`; needs a note that any `on_<verdict>` key is valid when using `llm_structured` with a custom schema
- `docs/generalized-fsm-loop.md:445` — Resolution Order section enumerates `on_yes/no/error/blocked` explicitly; should include "or any custom `on_<verdict>` shorthand"
- `docs/guides/LOOPS_GUIDE.md:635` — "States use shorthand (`on_yes`, `on_no`, `on_partial`, `on_blocked`) or a route table" — enumeration incomplete; add custom `on_<verdict>` pattern
- `skills/review-loop/SKILL.md:198` — QC-13 dead-end check enumerates `on_yes`, `on_no`, `on_partial`, `on_error`, `next`, `route.*` explicitly; a state with only `extra_routes` targets would be falsely flagged as a dead-end non-terminal (FA-6 Error)

### Configuration
- N/A

## Impact

- **Priority**: P2 — The `on_<custom_verdict>` routing pattern is completely non-functional; any `llm_structured` evaluator using a custom schema with non-standard verdict strings cannot route at all
- **Effort**: Small-medium — 3 files, ~20 lines of changes; no schema-breaking changes
- **Risk**: Low — `extra_routes` is additive; existing hardcoded `on_*` keys are unchanged
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `schema`, `validation`, `executor`, `llm_structured`

## Session Log
- `/ll:ready-issue` - 2026-04-11T22:05:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/506c300c-d5d9-40a6-8c70-92e1144ff16e.jsonl`
- `/ll:refine-issue` - 2026-04-11T21:29:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0800be1c-f6b4-497c-b5ac-2b3352749526.jsonl`
- `/ll:confidence-check` - 2026-04-11T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d9d3c2d4-5cf6-495c-8cd4-7181ace6fb24.jsonl`
- `/ll:confidence-check` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7e9754d-cf7a-45bf-b3bd-c6451115fbb0.jsonl`
- `/ll:wire-issue` - 2026-04-11T21:17:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef748997-a896-4299-a4ad-3b2fcbbc6bc1.jsonl`
- `/ll:refine-issue` - 2026-04-11T21:09:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2dff0ee-2abf-45bc-ad9a-01799e669ef8.jsonl`
- `/ll:format-issue` - 2026-04-11T21:05:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3bd1ba80-531f-439b-9cb9-52cd75a653ee.jsonl`
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a526cc2e-06c1-44e3-add0-5ba3cb7b1190.jsonl`

---

## Resolution

**Fixed** | Resolved: 2026-04-11 | Priority: P2

### Changes Made

- `scripts/little_loops/fsm/schema.py`: Added `extra_routes: dict[str, str]` field to `StateConfig`; updated `from_dict()` to collect unknown `on_*` keys, `get_referenced_states()` to include their targets, and `to_dict()` for round-trip serialization.
- `scripts/little_loops/fsm/executor.py`: Added `extra_routes` lookup in `_route()` after the hardcoded shorthand block.
- `scripts/little_loops/fsm/validation.py`: Added `or state.on_blocked is not None` and `or bool(state.extra_routes)` to `has_shorthand` expression.
- `scripts/little_loops/fsm/fsm-loop-schema.json`: Added `patternProperties: {"^on_": {"type": "string"}}` to allow custom `on_*` keys alongside `"additionalProperties": false`.
- `scripts/little_loops/cli/loop/testing.py`: Added `extra_routes` fallback in `cmd_test` inline routing.
- `scripts/little_loops/cli/loop/layout.py`: Added `extra_routes` iteration in `_collect_edges()`.
- `docs/generalized-fsm-loop.md`: Documented `on_<verdict>` custom shorthand pattern; updated Resolution Order section.
- `docs/guides/LOOPS_GUIDE.md`: Added custom `on_<verdict>` to shorthand enumeration.
- `skills/review-loop/SKILL.md`: Updated QC-13 dead-end check to include `extra_routes`.
- New fixture: `scripts/tests/fixtures/fsm/custom-on-routing.yaml`
- New tests: 6 `extra_routes` tests in `test_fsm_schema.py`; new file `test_fsm_validation.py` with 3 reachability tests; 2 executor routing tests in `test_fsm_executor.py`; 1 no-false-positive validation test in `test_ll_loop_commands.py`.

### Verification

- All 4604 tests pass, 0 failures.
- `ruff check scripts/` — clean.

## Status

**Resolved** | Created: 2026-04-11 | Priority: P2
