---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 85
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

## Motivation

Multi-state loops (e.g., `check_types → fix_types → check_lint → fix_lint`) are common patterns, but `ll-loop test` can only validate the initial state. Debugging a misconfigured non-initial state requires running the full loop and waiting for it to reach that state, which is time-consuming. Adding `--state` gives loop authors fine-grained control over what to test, reducing iteration time during loop development.

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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/testing.py` — update `cmd_test` signature to accept `args: argparse.Namespace`; replace hardcoded `fsm.initial` lookup with `args.state`-aware logic
- `scripts/little_loops/cli/loop/__init__.py` — add `--state` argument to `test_parser`; update `cmd_test` call to pass `args` instead of `args.loop`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:202` — sole caller of `cmd_test`

### Similar Patterns
- `simulate_parser.add_argument("--scenario", ...)` in `__init__.py` — same argparse pattern for optional enum-style subcommand arg
- `cmd_simulate(loop_name, args, loops_dir, logger)` in `testing.py` — shows how `args` namespace is passed alongside other params

### Tests
- `scripts/tests/test_ll_loop_commands.py` — add tests for `--state` arg (valid state, missing state error, default behavior)
- No existing unit tests for `cmd_test`; new tests needed

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `--state` optional argument to `test_parser` in `__init__.py`
2. Update `cmd_test` call in `__init__.py` to pass `args` instead of just `args.loop`
3. Update `cmd_test` signature in `testing.py` to accept `args: argparse.Namespace`
4. Replace `fsm.initial` lookup with `target = args.state if args.state else fsm.initial`
5. Add validation: if `target not in fsm.states`, log error and return 1
6. Update `State:` print line and `Would transition:` line to use `target` instead of `initial`
7. Add tests for `--state` valid, `--state` invalid, and default (no flag) behaviors

## Impact

- **Priority**: P3 - Useful for loop development and debugging
- **Effort**: Small - Existing test logic is state-agnostic, just needs arg wiring
- **Risk**: Low - Additive, no change to existing behavior without the flag
- **Breaking Change**: No

## Labels

`feature`, `ll-loop`, `testing`

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: `cmd_test` hardcodes `fsm.initial` at `testing.py:35-37`; no `--state` argument in `test_parser`
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — readiness: 100/100 PROCEED, outcome: 85/100 HIGH CONFIDENCE
- `/ll:format-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — added Motivation, Integration Map, Implementation Steps
- `/ll:format-issue` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — added missing ## Status heading (required section per feat-sections.json)

---

## Status

**Open** | Created: 2026-03-06 | Priority: P3
