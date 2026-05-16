---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 86
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
- `scripts/little_loops/fsm/compilers.py` — four locations:
  - `compile_goal()` lines 225–231: `StateConfig("evaluate", on_success="done", on_failure="fix")` — add `on_partial`
  - `compile_convergence()` lines 299–315: `StateConfig("measure", route=RouteConfig(...))` — add `on_partial` to route or as shorthand
  - `compile_invariants()` lines 405–410: per-constraint `StateConfig(on_success=next_check, on_failure=fix_state)` — add `on_partial`
  - `compile_imperative()` lines 501–506: `StateConfig("check_done", on_success="done", on_failure="step_0")` — add `on_partial`
- `scripts/little_loops/fsm/validation.py` — **already updated by ENH-625** (line 162: `or state.on_partial is not None`); no changes needed

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/compilers.py:compile_paradigm()` — dispatch function at lines 109–122 calls the individual compilers; no changes needed here
- `scripts/little_loops/fsm/schema.py:198` — `StateConfig.on_partial: str | None = None` already exists and is wired into `to_dict`, `from_dict`, `get_referenced_states`
- `scripts/little_loops/fsm/executor.py:734–735` — `_route()` already checks `state.on_partial`; no changes needed

### Similar Patterns (Direct Analogue)
- `compilers.py:380` — `maintain = spec.get("maintain", False)` shows how optional boolean spec fields are read
- `compilers.py:418–421` — `StateConfig(on_maintain=first_check if maintain else None)` shows how a conditional field flows into a compiled state
- `compilers.py:246` — `backoff=spec.get("backoff")` / `timeout=spec.get("timeout")` shows simple `spec.get("field")` → `None` when absent pattern

### Tests
- `scripts/tests/test_fsm_compilers.py` — add tests for `on_partial_target` in each supported compiler:
  - Model after `test_maintain_mode` (line 645) — field present → routing set on compiled state
  - Model after `test_maintain_default_false` (line 671) — field absent → `on_partial` is `None`
  - Model after `test_goal_validates` (line 192) — compiled FSM passes `validate_fsm()` end-to-end
  - Test class locations: `TestGoalCompiler` (line 94), `TestImperativeCompiler` (line 746), `TestConvergenceCompiler` (line 401), `TestInvariantsCompiler` (line 584)
- `scripts/tests/test_fsm_schema_fuzz.py` — may need `on_partial_target` added to property-based test specs

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — documents paradigm YAML syntax; add `on_partial_target` field description
- `docs/generalized-fsm-loop.md` — core FSM design doc; reference paradigm `on_partial_target`

### Configuration
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON schema for loop YAML; add `on_partial_target` to paradigm spec object definitions

## Implementation Steps

1. ~~Merge ENH-625 first~~ — **ENH-625 is completed** (`validation.py:162` already includes `on_partial` in shorthand check); no prerequisite work needed
2. In `compilers.py:compile_goal()` (~line 222), read the new field: `on_partial_target = spec.get("on_partial_target")`, then pass `on_partial=on_partial_target` to the `"evaluate"` `StateConfig` constructor at lines 225–231
3. In `compilers.py:compile_imperative()` (~line 486), read `on_partial_target = spec.get("on_partial_target")` from `spec["until"]` or top-level spec (decide during impl), then pass `on_partial=on_partial_target` to the `"check_done"` `StateConfig` at lines 501–506
4. Optionally extend `compile_convergence()` (lines 299–315) and `compile_invariants()` (lines 405–410) using the same pattern — acceptance criteria says "at least" goal + imperative
5. Add `on_partial_target` to `fsm-loop-schema.json` paradigm spec objects (optional string field, no constraints on value — validation catches dangling refs)
6. Add tests in `test_fsm_compilers.py` following the `maintain` pattern (lines 618–654):
   - `test_goal_with_on_partial_target` — spec with field → `fsm.states["evaluate"].on_partial == <target>`
   - `test_goal_without_on_partial_target` — spec without field → `fsm.states["evaluate"].on_partial is None`
   - Same for `compile_imperative` targeting the `"check_done"` state
   - Include a `test_*_with_on_partial_target_validates` test confirming `validate_fsm()` passes (model after line 192)
7. Update `docs/guides/LOOPS_GUIDE.md` with `on_partial_target` field documentation

## Blocked By

- ~~ENH-625~~ — **Completed** (merged to main); `validation.py:162` already includes `on_partial`. No remaining blockers.

## Impact

- **Priority**: P3 — Unlocks a documented feature for paradigm YAML users; currently only accessible via raw FSM syntax
- **Effort**: Medium — Schema extension + compiler changes + tests
- **Risk**: Low — Additive; no changes to existing compilation paths when `on_partial_target` is absent
- **Breaking Change**: No

## Labels

`feature`, `fsm`, `compiler`, `paradigm`, `captured`

## Verification Notes

- **Verdict**: VALID — all claims verified against current codebase (main, post-1.35.0)
- `StateConfig.on_partial` confirmed at `schema.py:198`
- Executor partial routing confirmed at `executor.py:731-732`
- `llm_structured` evaluator "partial" enum confirmed at `evaluators.py:54`
- No `on_partial` in any compiler function in `compilers.py` (confirmed absent)
- ENH-625 exists as an active issue (confirmed prerequisite is valid)
- **DEP_ISSUES (minor)**: ENH-625 is missing a `## Blocks` backlink to FEAT-634

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d11c154b-ec01-40ba-bc51-c1eb3dd6ae2f.jsonl` — DEP_ISSUES resolved: added `## Blocks: FEAT-634` backlink to ENH-625
- `/ll:refine-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32a17f1a-60cf-46d8-b1b8-af6c34cf10c5.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/715cc5ab-154a-447a-b467-fd39461241ca.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/897fd6cd-c2f2-4a09-b789-054b18754b98.jsonl`
- `/ll:manage-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

## Resolution

**Completed** on 2026-03-07.

### Changes Made

- `scripts/little_loops/fsm/compilers.py`: Added `on_partial_target` support to all four paradigm compilers
  - `compile_goal()`: reads `spec.get("on_partial_target")`, passes `on_partial=on_partial_target` to `"evaluate"` StateConfig
  - `compile_convergence()`: reads `spec.get("on_partial_target")`, passes `on_partial=on_partial_target` to `"measure"` StateConfig
  - `compile_invariants()`: reads `spec.get("on_partial_target")`, passes `on_partial=on_partial_target` to each `check_*` StateConfig
  - `compile_imperative()`: reads `spec.get("on_partial_target")`, passes `on_partial=on_partial_target` to `"check_done"` StateConfig
- `scripts/little_loops/fsm/fsm-loop-schema.json`: Added `on_partial` field to `stateConfig` definition
- `scripts/tests/test_fsm_compilers.py`: Added 10 new tests covering `on_partial_target` for all four compilers (with/without field, and validation)
- `docs/guides/LOOPS_GUIDE.md`: Documented `on_partial_target` optional field for goal and imperative paradigms; added `on_partial` to routing shorthand docs

### Acceptance Criteria Met

- [x] `compile_goal` and `compile_imperative` support `on_partial_target` in their paradigm spec
- [x] `compile_convergence` and `compile_invariants` also support it (exceeds minimum)
- [x] Compiled states include `on_partial: <on_partial_target>` where specified
- [x] Paradigm YAML without `on_partial_target` behaves as before (`on_partial` is `None`)
- [x] All 99 tests pass; no regressions

## Status

**Completed** | Created: 2026-03-07 | Completed: 2026-03-07 | Priority: P3
