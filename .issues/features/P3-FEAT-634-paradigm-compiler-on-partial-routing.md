---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# FEAT-634: No paradigm compiler generates `on_partial` routing despite executor and evaluator supporting it

## Summary

`StateConfig` has an `on_partial` field, the executor routes `"partial"` verdicts via `_route()`, and the `llm_structured` evaluator schema explicitly includes `"partial"` as a valid verdict. However, none of the four paradigm compilers (`compile_goal`, `compile_convergence`, `compile_invariants`, `compile_imperative`) generate an `on_partial` route in any state they produce. Users writing paradigm YAML cannot access `on_partial` behavior without dropping to raw FSM syntax.

## Location

- **File**: `scripts/little_loops/fsm/compilers.py`
- **Line(s)**: 109–122, 224–250, 299–333, 394–433, 489–520 (at scan commit: 12a6af0)
- **Anchor**: `in function compile_paradigm()`, `compile_goal()`, `compile_convergence()`, `compile_invariants()`, `compile_imperative()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/compilers.py#L109-L122)

## Current Behavior

Writing a `goal`-paradigm loop YAML:
```yaml
paradigm: goal
on_partial: refine   # silently ignored — compile_goal() does not use this field
```

The compiled FSM has no `on_partial` routing on the `evaluate` state. `"partial"` verdicts fall through `_route()` returning `None`, triggering `_finish("error")`.

## Expected Behavior

Paradigm specs that include an `on_partial_target` (or similar field) should produce `on_partial` routes in the compiled FSM states.

## Use Case

A developer builds a `goal`-paradigm loop for iterative document refinement. Their `llm_structured` evaluator returns `"partial"` when the document is improving but not yet done. They want `"partial"` to route to a `"light_fix"` state (minor tweaks) while `"failure"` routes to a `"full_fix"` state (major revision). This is not expressible in paradigm YAML today; they must write raw FSM syntax.

## Acceptance Criteria

- At least `compile_goal` and `compile_imperative` support an `on_partial_target` field in their paradigm spec
- The compiled states include `on_partial: <on_partial_target>` where specified
- Paradigm YAML without `on_partial_target` continues to behave as today (no partial routing)
- The validation fix in ENH-625 (adding `on_partial` to `has_shorthand`) is a prerequisite

## API/Interface

```yaml
# goal paradigm with on_partial support
paradigm: goal
check: /ll:check-quality
fix: /ll:improve-draft
on_partial_target: light_fix   # new optional field

# The compiler generates:
# evaluate.on_partial = "light_fix"
# And a "light_fix" state must exist (or be defined in an extra_states block)
```

## Proposed Solution

Add an optional `on_partial_target: str` field to the paradigm spec dataclasses and pass it through to the compiled `StateConfig`:

```python
# In compile_goal():
on_partial = spec.get("on_partial_target")
"evaluate": StateConfig(
    ...
    on_partial=on_partial,  # None if not specified
),
```

The referenced target state must either exist in the compiled states or be user-defined (validation catches dangling references).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/compilers.py` — `compile_goal()`, `compile_imperative()` (and optionally others)
- `scripts/little_loops/fsm/validation.py` — ENH-625 prerequisite (add `on_partial` to shorthand check)

### Tests
- `scripts/tests/test_fsm_compilers.py` — add tests for `on_partial_target` in goal and imperative paradigms

### Documentation
- Loop paradigm documentation

### Configuration
- N/A

## Implementation Steps

1. Merge ENH-625 first (validation fix for `on_partial`)
2. Add `on_partial_target` optional field recognition in `compile_goal()`
3. Pass through to compiled `evaluate` state's `on_partial` field
4. Extend to `compile_imperative()` similarly
5. Add tests

## Blocked By

- ENH-625 (on_partial missing from validation shorthand check — prerequisite)

## Impact

- **Priority**: P3 — Unlocks a documented feature for paradigm YAML users; currently only accessible via raw FSM syntax
- **Effort**: Medium — Schema extension + compiler changes + tests
- **Risk**: Low — Additive; no changes to existing compilation paths when `on_partial_target` is absent
- **Breaking Change**: No

## Labels

`feature`, `fsm`, `compiler`, `paradigm`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P3
