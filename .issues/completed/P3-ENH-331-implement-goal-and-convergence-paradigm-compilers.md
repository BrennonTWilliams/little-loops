---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-331: Implement goal and convergence paradigm compilers

## Summary

The FSM compiler system (`compilers.py`) was designed for 4 paradigms (goal, convergence, invariants, imperative) per FEAT-041, but only invariants and imperative were implemented. The `compile_goal` and `compile_convergence` functions need to be written to complete the paradigm compiler system.

## Current Behavior

`compilers.py:109-110` only registers two compilers:
```python
"invariants": compile_invariants,
"imperative": compile_imperative,
```

The module docstring (`compilers.py:3`) and FEAT-041 both reference all four paradigms. Attempting to use `paradigm: goal` or `paradigm: convergence` in a loop YAML will fail.

## Expected Behavior

All four paradigms compile successfully:

```python
"goal": compile_goal,
"convergence": compile_convergence,
"invariants": compile_invariants,
"imperative": compile_imperative,
```

**Goal paradigm** template pattern (from FEAT-041):
`evaluate → (success → done, failure → fix), fix → evaluate`

**Convergence paradigm** template pattern (from FEAT-041):
`measure → (target → done, progress → apply, stall → done), apply → measure`

The `convergence` evaluator type already exists in `EvaluateConfig` (schema.py:37) with `direction`, `tolerance`, and `previous` fields, so the schema layer is ready.

## Motivation

- Completes the original FEAT-041 design which explicitly listed all 4 paradigms
- Enables goal-directed loops (e.g., "no type errors in src/") and metric convergence loops (e.g., "reduce test failures to 0")
- Unblocks creation of loop templates that use these paradigms
- The `/ll:create_loop` wizard already presents all 4 paradigms to users (per ENH-126) but 2 don't actually work

## Proposed Solution

Implement two new compiler functions in `scripts/little_loops/fsm/compilers.py` following the same pattern as `compile_invariants` and `compile_imperative`:

1. `compile_goal(spec)` - Takes `goal`, `tools`, optional `check` fields → produces evaluate/fix/done FSM
2. `compile_convergence(spec)` - Takes `metric`, `target`, `tools`, optional `tolerance` → produces measure/apply/done FSM

Register both in the `COMPILERS` dict.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/compilers.py` - Add `compile_goal` and `compile_convergence` functions

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli.py` - Uses `compile_paradigm()` (no changes needed, auto-discovers via registry)
- `skills/ll:create_loop.md` - Already references all 4 paradigms in wizard

### Tests
- `scripts/tests/test_fsm_compilers.py` - Add tests for goal and convergence compilers
- `scripts/tests/fixtures/fsm/` - Add `goal-loop.yaml` and `convergence-loop.yaml` fixtures

### Documentation
- `docs/API.md` - Document new compiler functions
- `docs/ARCHITECTURE.md` - Verify paradigm documentation is accurate

### Configuration
- N/A

## Implementation Steps

1. Implement `compile_goal()` following the evaluate→fix→done template pattern
2. Implement `compile_convergence()` following the measure→apply→done template pattern
3. Register both in the compiler registry
4. Add unit tests and YAML fixtures
5. Verify `/ll:create_loop` wizard works end-to-end with new paradigms

## Impact

- **Priority**: P3 - Important for completeness but invariants/imperative cover most use cases
- **Effort**: Medium - Schema support exists, need ~100 lines per compiler plus tests
- **Risk**: Low - Additive change, existing compilers unaffected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize_issues` to discover and link relevant docs._

## Labels

`enhancement`, `fsm`, `captured`

---

## Status

**Closed - Already Fixed** | Created: 2026-02-11 | Closed: 2026-02-11 | Priority: P3

## Resolution

Both `compile_goal` and `compile_convergence` are already implemented in `scripts/little_loops/fsm/compilers.py` (lines 134 and 208) and registered in the `COMPILERS` dict (lines 107-108). All four paradigms are functional.
