---
discovered_date: 2026-04-10
discovered_by: capture-issue
---

# BUG-1019: confidence_check state uses invalid evaluator type shell_exit

## Summary

The `confidence_check` state in `refine-to-ready-issue.yaml` uses `evaluate.type: shell_exit` (a fragment name) instead of `exit_code` (the actual evaluator type), causing a `ValueError` at runtime that silently terminates the sub-loop and wastes 90+ minutes of refinement in the auto-refine-and-implement outer loop.

## Context

**Direct mode**: User description: "Fix: `confidence_check` state uses invalid evaluator type `shell_exit`"

## Current Behavior

The `confidence_check` state in `refine-to-ready-issue.yaml` declares `evaluate.type: shell_exit` — a fragment name, not a valid evaluator type. At runtime, the `evaluate()` dispatcher raises `ValueError("Unknown evaluator type: shell_exit")`, bypassing the `on_error: check_scores_from_file` routing (which only catches `EvaluationResult(verdict="error")`, not Python exceptions). The exception propagates to `run()`'s broad `except Exception` handler at `executor.py`, terminating the sub-loop with error. The outer loop receives this error and routes to `skip_issue`/`detect_children`, never implementing the issue.

## Expected Behavior

The `confidence_check` state should successfully evaluate readiness scores and route accordingly: `on_yes: done` when both readiness and outcome thresholds are met, `on_no: check_refine_limit` when they are not. The validator (`_validate_evaluator()`) should catch unknown evaluator types at YAML load time, raising a `ValidationError` with a clear message instead of silently allowing them through.

## Steps to Reproduce

1. Start the `auto-refine-and-implement` or `recursive-refine` FSM loop with any issue
2. The sub-loop `refine-to-ready-issue` runs: `format_issue` → `refine_issue` → `wire_issue` states complete successfully
3. The FSM reaches the `confidence_check` state and runs `/ll:confidence-check`
4. `_evaluate()` calls `evaluate()` dispatcher with `type="shell_exit"`
5. `evaluators.py:836` raises `ValueError("Unknown evaluator type: shell_exit")`
6. `run()` catches via `except Exception` → `_finish("error")` → outer loop routes to `skip_issue`
7. Observe: issue is skipped despite passing format/refine/wire stages successfully

## Root Cause

**File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`
**Evaluator dispatch**: `scripts/little_loops/fsm/evaluators.py:836`

The `confidence_check` state declares `evaluate.type: shell_exit`, which is a **fragment name**, not a valid evaluator type. `shell_exit` is only valid as `fragment: shell_exit`, which the fragment system resolves to `evaluate.type: exit_code`. Used directly in `evaluate.type`, it causes `ValueError("Unknown evaluator type: shell_exit")` at runtime.

**Why it passes validation**: Python's `Literal` type hint is not runtime-enforced. The validator (`_validate_evaluator`) only checks required fields for known types but never validates that `evaluate.type` is a recognized type. `EVALUATOR_REQUIRED_FIELDS.get("shell_exit", [])` returns `[]` instead of flagging it.

**Why `on_error: check_scores_from_file` never fires**: The state declares `on_error: check_scores_from_file` (line 137), suggesting a graceful fallback. But `on_error` routing only triggers when `_evaluate()` returns an `EvaluationResult(verdict="error")` — it does NOT catch Python exceptions raised during evaluation. The `ValueError` from the `evaluate()` dispatcher propagates directly to `run()`'s broad `except Exception` handler at `executor.py:315`, bypassing the `_route()` method entirely. The fallback state is dead code.

**Runtime failure path**:
1. `_execute_state()` runs the slash command action (`/ll:confidence-check`)
2. `_evaluate()` calls `evaluate()` dispatcher with `type="shell_exit"`
3. `evaluate()` raises `ValueError("Unknown evaluator type: shell_exit")`
4. `run()` catches via `except Exception` (executor.py:315) -> `_finish("error")`
5. Sub-loop terminates with error -> outer loop routes to `skip_issue`

**Secondary issue**: The `evaluate` block contains an `action` field (the Python script), but `EvaluateConfig` has no `action` attribute -- the script is dead code, silently ignored during deserialization.

**Why FEAT-8928 succeeded**: FEAT-8928 was the first issue processed and the only one implemented. Its `check_lifetime_limit` returned `1` (lifetime cap already reached), so the FSM took the `on_no` path to `breakdown_issue` → `done`, **never reaching `confidence_check`**. All subsequent issues had `check_lifetime_limit: 0` (under cap), so they ran the full pipeline and hit the broken state.

**Blast radius (auto-refine-and-implement, ~476 minutes)**:

| Issue | check_lifetime_limit | Reached confidence_check? | Skipped? |
|-------|---------------------|--------------------------|----------|
| FEAT-8928 | `1` → no (bypassed) | No | No (implemented) |
| FEAT-8923 | `0` → yes | Yes (98/100 readiness) | Yes |
| ENH-8952 | `0` → yes | Yes (98/100 readiness) | Yes |
| BUG-9017 | `0` → yes | Yes (100/100 readiness) | Yes |
| ENH-8981 | `0` → yes | Yes (93/100 readiness) | Yes |
| ENH-9013 | `0` → yes | Yes (100/100 readiness) | Yes |
| FEAT-9019 | `0` → yes | Yes (93/100 readiness) | Yes |
| FEAT-9020 | `0` → yes | Yes (75/100 readiness) | Yes |
| ENH-9022 | `0` → yes | Yes (100/100 readiness) | Yes |
| FEAT-9021 | `0` → yes | Yes (85/100 readiness) | Yes |

## Motivation

Every issue processed through `refine-to-ready-issue` passes format -> refine -> wire successfully, then crashes at `confidence_check`. The outer loop sees this as a sub-loop error and routes to `skip_issue`, making the entire auto-refine pipeline non-functional. This is a P1 because it silently wastes significant compute time with zero useful output.

## Implementation Steps

### Fix 1: Split `confidence_check` into two states

The state currently tries to do two things: (1) run `/ll:confidence-check` to update scores, and (2) run a Python script to read scores and evaluate. The FSM doesn't support two actions in one state. Split into:

**State 1: `confidence_check`** (runs the skill, unconditional transition):
```yaml
confidence_check:
  action: "/ll:confidence-check ${captured.issue_id.output}"
  action_type: slash_command
  next: check_scores
```

**State 2: `check_scores`** (runs Python script, evaluates result):
```yaml
check_scores:
  action: |
    python3 << 'PYEOF'
    import json, sys, subprocess
    from pathlib import Path

    p = Path('.ll/ll-config.json')
    cg = {}
    if p.exists():
        try:
            cg = json.loads(p.read_text()).get('commands', {}).get('confidence_gate', {})
        except Exception:
            pass
    readiness = cg.get('readiness_threshold', ${context.readiness_threshold})
    outcome = cg.get('outcome_threshold', ${context.outcome_threshold})

    r = subprocess.run(
        ['ll-issues', 'show', '${captured.issue_id.output}', '--json'],
        capture_output=True, text=True
    )
    d = json.loads(r.stdout)
    sys.exit(0 if int(d.get('confidence') or 0) >= readiness
               and int(d.get('outcome') or 0) >= outcome else 1)
    PYEOF
  action_type: shell
  evaluate:
    type: exit_code
  on_yes: done
  on_no: check_refine_limit
  on_error: check_scores_from_file
```

Uses `exit_code` directly (not via fragment) since the state has non-default fields that would conflict with fragment deep-merge.

### Fix 2: Close the validation gap

Add evaluator type validation in `_validate_evaluator()` (`scripts/little_loops/fsm/validation.py`, around line 116):

```python
VALID_EVAL_TYPES = set(EVALUATOR_REQUIRED_FIELDS.keys())
if evaluate.type not in VALID_EVAL_TYPES:
    errors.append(
        ValidationError(
            message=f"Unknown evaluator type '{evaluate.type}'. "
            f"Must be one of: {', '.join(sorted(VALID_EVAL_TYPES))}",
            path=path,
        )
    )
```

## Files to Modify

1. `scripts/little_loops/loops/refine-to-ready-issue.yaml` -- split confidence_check into two states, remove dead `evaluate.action` field
2. `scripts/little_loops/fsm/validation.py` -- add evaluator type validation

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:105-137` — replace `confidence_check` with two states (`confidence_check` + `check_scores`), remove dead `evaluate.action` field
- `scripts/little_loops/fsm/validation.py:102-126` — add evaluator type validation in `_validate_evaluator()`

### Dependent Files (Callers of refine-to-ready-issue)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:35-40` — invokes refine-to-ready-issue as sub-loop; `on_error: skip_issue` currently masks the ValueError as "issue skipped"
- `scripts/little_loops/loops/recursive-refine.yaml:93-97` — also invokes refine-to-ready-issue as sub-loop; `on_error: detect_children` routes errored issues to child detection

### Correct Usage in Same File
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:158-185` — `check_scores_from_file` state correctly uses `fragment: shell_exit` (line 182), which resolves to `evaluate.type: exit_code`. This is the pattern the fix should follow.

### Tests
- `scripts/tests/test_fsm_fragments.py:822-847` — `TestBuiltinLoopMigration` loads refine-to-ready-issue.yaml and asserts validation passes. This test must still pass after the fix.
- `scripts/tests/test_fsm_evaluators.py:540-547` — `test_dispatch_unknown_type_raises` tests the exact ValueError path triggered by this bug.
- `scripts/tests/test_fsm_schema.py` — FSM schema validation tests (includes evaluator field validation)
- Suggest new test: add a test case in `test_fsm_schema.py` or `test_fsm_fragments.py` that asserts `_validate_evaluator()` rejects unknown evaluator types like `shell_exit`

### Documentation
- `docs/generalized-fsm-loop.md` — FSM loop system design doc (references `shell_exit` fragment and `exit_code` evaluator type)
- `docs/guides/LOOPS_GUIDE.md` — User-facing loops guide (references `confidence_check` and evaluator types)
- `docs/reference/API.md` — API reference (documents `EvaluateConfig` and evaluator types)

## Verification

1. `python -m pytest scripts/tests/test_fsm_fragments.py -v` -- builtin loop migration test should still pass
2. `python -m pytest scripts/tests/ -k "refine" -v` -- any refine-related tests
3. `python -c "from little_loops.fsm.validation import load_and_validate; from pathlib import Path; _, errs = load_and_validate(Path('scripts/little_loops/loops/refine-to-ready-issue.yaml')); print(errs)"` -- should load without errors
4. Verify `check_scores` state exists with `evaluate.type: exit_code` and proper routing

## Related Key Documentation

- `docs/generalized-fsm-loop.md` — FSM loop system design (fragment system, evaluator types)
- `docs/guides/LOOPS_GUIDE.md` — User-facing loops guide (confidence_check, evaluator configuration)
- `docs/reference/API.md` — API reference (EvaluateConfig, evaluator dispatch)

## Impact

- **Priority**: P1 - Silently terminates every issue's refinement pipeline after 90+ minutes of processing; routes all issues to `skip_issue`. The entire auto-refine-and-implement pipeline is non-functional.
- **Effort**: Small - Two targeted file changes: split `confidence_check` state in YAML + add type validation in `_validate_evaluator()`
- **Risk**: Low - Fixes a broken state; existing tests (`TestBuiltinLoopMigration`, `test_dispatch_unknown_type_raises`) verify the fix
- **Breaking Change**: No

## Labels

`bug`, `fixed`

## Resolution

**Fixed** | 2026-04-10

### Changes Made

1. **`scripts/little_loops/loops/refine-to-ready-issue.yaml`**: Split `confidence_check` into two states:
   - `confidence_check`: runs `/ll:confidence-check` skill, unconditional `next: check_scores`
   - `check_scores`: runs Python script to read scores from issue frontmatter, uses `evaluate.type: exit_code` (valid), routes `on_yes: done`, `on_no: check_refine_limit`, `on_error: check_scores_from_file`

2. **`scripts/little_loops/fsm/validation.py`**: Added unknown evaluator type validation in `_validate_evaluator()` — unknown types now raise a `ValidationError` at YAML load time instead of `ValueError` at runtime.

3. **`scripts/tests/test_builtin_loops.py`**: Updated `TestRefineToReadyIssueSubLoop` tests to reflect new two-state structure (`confidence_check` → `check_scores`).

## Session Log
- `/ll:ready-issue` - 2026-04-10T19:12:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8cc3e29c-a60b-4144-a54e-33e4dd71cd9f.jsonl`
- `/ll:refine-issue` - 2026-04-10T18:57:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ade57844-f3d8-473c-8de6-84e77f05a160.jsonl`
- `/ll:manage-issue` - 2026-04-10T19:30:00 - bug fix BUG-1019

---

## Status

**Fixed** | Created: 2026-04-10 | Priority: P1
