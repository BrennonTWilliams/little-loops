---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
---

# FEAT-609: `ll-loop test` only tests initial state — add `--state` flag

## Summary

`cmd_test` hardcodes to `fsm.initial` and has no mechanism for the user to specify a different state. Loops with multiple meaningful states (e.g., `check_types`, `fix_types`, `check_lint`, `fix_lint`) cannot have individual states tested. The test execution logic already operates on a generic `state_config` reference and would work with any state.

## Current Behavior

`cmd_test` at `testing.py:35-37` always tests `fsm.initial`:
```python
initial = fsm.initial
state_config = fsm.states[initial]
```

`test_parser` accepts only the `loop` positional argument.

## Expected Behavior

`test_parser` accepts an optional `--state` argument. If provided, `cmd_test` looks up `fsm.states[args.state]` instead of `fsm.states[initial]`.

## Use Case

A user creating a multi-state quality gate loop wants to verify that the `fix_lint` state's action and evaluator work correctly before running the full loop. They run `ll-loop test my-loop --state fix_lint` to test just that state in isolation.

## Acceptance Criteria

- [ ] `ll-loop test <loop> --state <name>` tests the specified state
- [ ] Error message if `--state` value doesn't exist in the loop's states
- [ ] Without `--state`, behavior unchanged (tests initial state)

## Proposed Solution

Add `--state` to `test_parser` in `__init__.py`. In `cmd_test`, replace:
```python
initial = fsm.initial
state_config = fsm.states[initial]
```
with:
```python
target = args.state if args.state else fsm.initial
if target not in fsm.states:
    logger.error(f"State '{target}' not found. Available: {', '.join(fsm.states)}")
    return 1
state_config = fsm.states[target]
```

## Impact

- **Priority**: P3 - Useful for loop development and debugging
- **Effort**: Small - Existing test logic is state-agnostic, just needs arg wiring
- **Risk**: Low - Additive, no change to existing behavior without the flag
- **Breaking Change**: No

## Labels

`feature`, `ll-loop`, `testing`

---

**Open** | Created: 2026-03-06 | Priority: P3
