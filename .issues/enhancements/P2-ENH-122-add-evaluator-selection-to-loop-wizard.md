---
discovered_date: 2026-01-23
discovered_by: capture_issue
---

# ENH-122: Add evaluator selection to loop creation wizard

## Summary

The `/ll:create-loop` command creates loops that are technically valid but practically don't work because the wizard doesn't gather evaluator configuration. Users specify check commands but are never asked HOW to determine success/failure.

## Context

Identified from conversation analyzing why created loops have "transitions that can't be checked, unclear states." The root cause is the gap between what the wizard captures and what the FSM compilers need.

**Current behavior**: Wizard asks for check/fix command pairs but assumes exit code evaluation.

**Problem scenarios**:
- Command exits 0 but has warnings the user cares about
- Command exits non-zero for benign reasons (deprecation warnings)
- Success requires parsing output content, not just exit code

## Current Behavior

The goal/invariants/imperative paradigm compilers (`scripts/little_loops/fsm/compilers.py:144-150, 314-322, 401-405`) use `on_success`/`on_failure` routing without explicit evaluators, defaulting to exit code interpretation.

Only the convergence paradigm (lines 218-228) uses an explicit `EvaluateConfig`.

## Expected Behavior

When a user specifies a check command in the wizard, follow up with:

1. "How should success be determined?"
   - Exit code (default) - command returns 0
   - Output contains pattern - look for specific text
   - Output numeric threshold - compare number to target
   - Let AI decide - use llm_structured evaluator

2. For pattern matching: "What pattern indicates success?"
   - Offer smart suggestions based on the tool (e.g., "Success" for mypy)

## Proposed Solution

Extend `commands/create_loop.md` wizard to add evaluator questions after each check command:

```yaml
questions:
  - question: "How should success be determined for this check?"
    header: "Evaluator"
    options:
      - label: "Exit code (Recommended)"
        description: "Success if command exits with code 0"
      - label: "Output contains pattern"
        description: "Success if output contains specific text"
      - label: "Output is numeric"
        description: "Compare numeric output to threshold"
      - label: "AI interpretation"
        description: "Let Claude analyze the output"
```

Then update the paradigm compilers to accept and use explicit evaluator configs.

## Impact

- **Priority**: P2 (significantly improves loop reliability)
- **Effort**: Medium (wizard changes + compiler updates)
- **Risk**: Low (additive, doesn't break existing loops)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | scripts/little_loops/fsm/compilers.py | Paradigm compilation logic |
| architecture | scripts/little_loops/fsm/fsm-loop-schema.json | Evaluator schema definition |
| commands | commands/create_loop.md | Wizard implementation |

## Labels

`enhancement`, `create-loop`, `evaluators`, `captured`

---

## Status

**Open** | Created: 2026-01-23 | Priority: P2

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `commands/create_loop.md`: Added evaluator selection questions after check command collection for goal, invariants, and imperative paradigms. Added conditional follow-up questions for output_contains (pattern selection) and output_numeric (condition selection). Updated YAML templates to include evaluator configuration. Enhanced FSM preview to show evaluator info.
- `scripts/little_loops/fsm/compilers.py`: Added `_build_evaluate_config()` helper function. Updated `compile_goal()` to accept and pass evaluator config to StateConfig. Updated `compile_invariants()` to accept per-constraint evaluator config. Updated `compile_imperative()` to accept evaluator config for exit condition.
- `scripts/tests/test_fsm_compilers.py`: Added comprehensive `TestEvaluatorSupport` class with 13 test cases covering all paradigms and evaluator types.

### Verification Results
- Tests: PASS (67 tests passed)
- Lint: PASS
- Types: PASS
