---
id: BUG-1608
type: BUG
priority: P3
title: "Add test coverage for failure terminal diagnostic action requirement"
status: open
parent: BUG-1603
size: Medium
---

# BUG-1608: Add test coverage for failure terminal diagnostic action requirement

## Summary

Add tests that assert all built-in loop YAML files have a pre-terminal `diagnose` state before any failure terminal, and validate the new `validate_failure_terminal_action()` check in `validation.py` (if BUG-1607 adds it). Also update per-loop test assertions to confirm the `diagnose` state exists after BUG-1606 lands.

## Parent Issue

Decomposed from BUG-1603: failure terminal states in built-in loops have no diagnostic action — silent failure in ll-loop history

## Dependencies

- BUG-1606 must land first (YAML fixes must exist before per-loop assertions can pass)
- BUG-1607 should land first if `TestFailureTerminalActionValidation` is to be written (requires `validate_failure_terminal_action()` in validation.py)

## Implementation Steps

### Step 1 — test_builtin_loops.py: global regression test

In `scripts/tests/test_builtin_loops.py`, add `test_all_failure_terminals_have_diagnostic_action` to `TestBuiltinLoopFiles`:

```python
def test_all_failure_terminals_have_diagnostic_action(self):
    """All built-in loops must have a pre-terminal diagnose state before failure terminals."""
    for loop_name, loop_yaml in self._load_all_builtin_loops():
        states = loop_yaml.get("states", {})
        failure_terminals = [
            name for name, cfg in states.items()
            if cfg.get("terminal") and name in ("failed", "error", "aborted")
        ]
        for ft in failure_terminals:
            # Find any state that routes to this terminal
            routes_to_terminal = [
                (name, cfg) for name, cfg in states.items()
                if cfg.get("next") == ft or ft in (cfg.get("transitions") or {}).values()
            ]
            # That routing state must have an action
            for name, cfg in routes_to_terminal:
                assert cfg.get("action"), (
                    f"Loop '{loop_name}': state '{name}' routes to terminal '{ft}' "
                    f"but has no diagnostic action"
                )
```

Adjust routing detection to match the actual FSM YAML structure.

### Step 2 — Per-loop test assertions in test_builtin_loops.py

At the existing assertions in `test_builtin_loops.py` at lines 1967, 2354, 2717, 2914, 3071 that assert `terminal: true` on `failed` states, add a companion assertion:

```python
# After BUG-1606: a pre-terminal diagnose state must exist
diagnose_state = states.get("diagnose") or states.get("diagnose_failure") or states.get("report")
assert diagnose_state is not None, f"Expected a pre-terminal diagnose state before 'failed'"
assert diagnose_state.get("action"), "Pre-terminal diagnose state must have an action"
```

Adjust state name lookup to match what BUG-1606 actually used for each loop.

### Step 3 — test_fsm_validation.py: TestFailureTerminalActionValidation (if BUG-1607 adds validation)

If `validate_failure_terminal_action()` is added to `validation.py` by BUG-1607, add `TestFailureTerminalActionValidation` following the `TestDescriptionFieldValidation` pattern:

```python
class TestFailureTerminalActionValidation:
    def test_bare_failure_terminal_emits_warning(self):
        fsm = {"states": {"failed": {"terminal": True}}}
        errors = validate_fsm(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert any("failed" in str(w) for w in warnings)

    def test_failure_terminal_with_diagnose_state_passes(self):
        fsm = {"states": {
            "diagnose": {"action_type": "prompt", "action": "...", "next": "failed"},
            "failed": {"terminal": True}
        }}
        errors = validate_fsm(fsm)
        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING
                    and "failed" in str(e)]
        assert not warnings
```

### Step 4 — test_fsm_executor.py fixture updates

Lines 3834 and 3858 contain inline `failed: terminal: true` YAML fixtures. If `validate_fsm()` is called on them during the test, they will emit the new WARNING. Either:
- Add `action:` to those fixtures to suppress the warning, or
- Filter the warnings in the test assertion

Determine which approach is cleaner based on what the tests actually assert.

### Step 5 — test_fsm_schema.py

`test_terminal_only_state_valid()` at line ~951–963 explicitly asserts `StateConfig(terminal=True)` with no action produces zero errors. Since BUG-1607 uses `ValidationSeverity.WARNING` (not ERROR), this test passes unchanged. Verify this is still true after BUG-1607 lands.

## Acceptance Criteria

- `test_all_failure_terminals_have_diagnostic_action` passes for all 12 fixed loops (after BUG-1606)
- Per-loop assertions at lines 1967, 2354, 2717, 2914, 3071 each have companion `diagnose` state assertions
- `TestFailureTerminalActionValidation` passes (if BUG-1607 adds validation)
- `test_terminal_only_state_valid()` still passes (WARNING severity, not ERROR)
- No regressions in test_fsm_executor.py fixtures

## Labels

`bug`, `tests`, `fsm`, `diagnostics`

---

**Priority**: P3 | **Created**: 2026-05-18

## Session Log
- `/ll:issue-size-review` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbd13cdc-51a4-41ee-85fe-30c33cc936aa.jsonl`
