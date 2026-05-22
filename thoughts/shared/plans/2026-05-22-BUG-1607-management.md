# BUG-1607 Implementation Plan: Failure Terminal Tooling Convention

**Issue**: Update docs, create-loop wizard, and validation for failure terminal convention
**Status**: Step 1 done (docs committed), Steps 2-4 remain
**Date**: 2026-05-22

## Summary

Four changes to solidify the pre-terminal `diagnose → failed` convention:
1. ~~Verify/commit docs/generalized-fsm-loop.md~~ Done
2. Update `loop-types.md` wizard escalate template + `SKILL.md` warning
3. Add `validate_failure_terminal_action()` to `validation.py`
4. Add API.md bullet for the new check

## Step 2: Update Wizard Templates and Warning

### 2a: `skills/create-loop/loop-types.md` (lines 1050-1067)

Replace the `escalate` single-state terminal (with `verdict: failure` — unrecognized field):
```yaml
  escalate:
    action: "echo 'Sub-loop failed, needs manual attention'"
    action_type: shell
    terminal: true
    verdict: failure
```
With two-state pre-terminal pattern:
```yaml
  diagnose_failure:
    action: "echo 'Sub-loop failed, needs manual attention'"
    action_type: shell
    next: failed

  failed:
    terminal: true
```
Also update `on_failure: escalate` → `on_failure: diagnose_failure` on `fix_lint` and `run_tests`.

### 2b: `skills/create-loop/SKILL.md` (line 143)

Current warning only flags terminals with no `action:`. Update to describe the two-state pre-terminal diagnose pattern — flag terminal states that have an `action:` field (dead code) and recommend the two-state pattern.

## Step 3: Add `validate_failure_terminal_action()` to validation.py

### Function design

```python
def _validate_failure_terminal_action(fsm: FSMLoop) -> list[ValidationError]:
```

- Takes full `FSMLoop` (needs predecessor routing analysis)
- Failure-named terminal set: `{"failed", "error", "aborted"}`
- For each failure terminal: find predecessor states that route to it
- Check at least one predecessor has diagnostic capability (`action` or `loop`)
- Severity: `ValidationSeverity.WARNING` (not ERROR)
- Wire into `validate_fsm()` after the per-state loop (alongside unreachable state check, line ~770)

### Predecessor detection

For a given failure terminal `ft`:
1. Scan all states for any routing field (`next`, `on_yes`, `on_no`, `on_error`, `on_partial`, `on_blocked`, `on_retry_exhausted`, `on_rate_limit_exhausted`, `extra_routes`) pointing to `ft`
2. A predecessor counts as "diagnostic" if it has `action`, `action_type`, or `loop` set

### Design decisions
- WARNING not ERROR: avoids breaking `test_terminal_only_state_valid()` (filters by ERROR)
- Wired after per-state loop (not inside `_validate_state_action`) because it needs the full FSM for predecessor analysis
- Model after unreachable-state WARNING pattern at lines 760-770

## Step 4: Update `docs/reference/API.md`

Add bullet to `validate_fsm` "Checks performed" list (line 4456-4463):
- Warns (WARNING) when a failure-named terminal state (e.g. `failed`, `error`, `aborted`) has no predecessor state routing through a diagnostic action before the terminal.

## Test Strategy

Tests explicitly deferred to BUG-1608 per issue confidence check notes. Skip Phase 3a (TDD Red) — the new validation function ships with WARNING severity so existing tests pass unchanged.

## Implementation Order

1. Step 2a: Update `loop-types.md` escalate template
2. Step 2b: Update `SKILL.md` warning
3. Step 3: Add `validate_failure_terminal_action()` to `validation.py`
4. Step 4: Update `docs/reference/API.md`
5. Verify: run tests, lint, type check
