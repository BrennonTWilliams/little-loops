---
discovered_commit: 31d60756
discovered_branch: main
discovered_date: 2026-04-11T00:00:00Z
discovered_by: capture-issue
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
7. Add a fixture loop YAML in `scripts/tests/fixtures/` (or inline) with `llm_structured` + custom schema + `on_done: final` / `on_retry: check`.
8. Add tests to `scripts/tests/test_fsm_schema.py` verifying `extra_routes` targets appear in `get_referenced_states()` and round-trip through `to_dict()`.
9. Add a test to `scripts/tests/test_fsm_validation.py` (alongside `test_unreachable_state_warning`) verifying that `extra_routes` targets are considered reachable.
10. Run `python -m pytest scripts/tests/ -k "fsm_schema or fsm_executor or fsm_validation" -v`.

## Impact

- **Priority**: P2 — The `on_<custom_verdict>` routing pattern is completely non-functional; any `llm_structured` evaluator using a custom schema with non-standard verdict strings cannot route at all
- **Effort**: Small-medium — 3 files, ~20 lines of changes; no schema-breaking changes
- **Risk**: Low — `extra_routes` is additive; existing hardcoded `on_*` keys are unchanged
- **Breaking Change**: No

## Labels

`bug`, `fsm`, `schema`, `validation`, `executor`, `llm_structured`

## Session Log
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a526cc2e-06c1-44e3-add0-5ba3cb7b1190.jsonl`

---

## Status

**Open** | Created: 2026-04-11 | Priority: P2
