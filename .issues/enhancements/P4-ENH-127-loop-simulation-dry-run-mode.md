---
discovered_date: 2026-01-23
discovered_by: capture_issue
---

# ENH-127: Loop simulation/dry-run mode

## Summary

Add a simulation mode to `ll-loop` that traces through loop logic without executing commands, allowing users to verify state transitions and understand loop behavior before running it for real.

## Context

Identified from conversation analyzing why created loops don't work. Users often don't understand the FSM structure their paradigm YAML compiles to, and can't predict how the loop will behave. A dry-run mode would let them step through the logic safely.

## Current Behavior

The only way to test a loop is to run it for real with `ll-loop <name>`. This:
- Executes actual commands that may modify files
- May take significant time for long-running checks
- Doesn't clearly show the decision logic at each step

## Expected Behavior

Add `--dry-run` or `--simulate` flag to `ll-loop`:

```bash
ll-loop fix-types --dry-run
```

Output would show the FSM execution trace without running commands:

```
=== DRY RUN: fix-types ===

[1] State: evaluate
    Action: mypy src/
    [SIMULATED] Would execute: mypy src/

    ? What should the simulated result be?
      > Success (exit 0)
        Failure (exit non-zero)
        Custom output

[User selects: Failure]

    Evaluator: exit_code
    Result: FAILURE
    Transition: evaluate → fix

[2] State: fix
    Action: /ll:check_code fix
    [SIMULATED] Would execute: /ll:check_code fix
    Transition: fix → evaluate (unconditional)

[3] State: evaluate
    Action: mypy src/
    [SIMULATED] Would execute: mypy src/

    ? What should the simulated result be?
      > Success (exit 0)
        Failure (exit non-zero)

[User selects: Success]

    Evaluator: exit_code
    Result: SUCCESS
    Transition: evaluate → done

[4] State: done
    [TERMINAL] Loop complete

=== Summary ===
States visited: evaluate → fix → evaluate → done
Iterations: 2
Would have executed 3 commands
```

## Proposed Solution

### Option A: Interactive Simulation (Recommended)

1. Add `--dry-run` flag to `ll-loop` CLI
2. For each state, show what command WOULD run
3. Prompt user for simulated result (success/failure/custom)
4. Apply evaluator logic to simulated result
5. Show transition decision
6. Continue until terminal state or max iterations

Pros: Users can explore different scenarios
Cons: Requires interaction

### Option B: Predefined Scenarios

1. Add `--dry-run --scenario=all-pass` or `--scenario=first-fail`
2. Automatically simulate predefined result patterns
3. Show full trace without interaction

Scenarios:
- `all-pass`: Every check succeeds
- `all-fail`: Every check fails (shows infinite loop potential)
- `first-fail`: First check fails, then passes (common case)
- `alternating`: Alternates success/failure

### Option C: Trace Mode

1. Add `--trace` flag that runs commands but with verbose FSM logging
2. Shows evaluator decisions and transition logic
3. Actually executes, but with detailed visibility

## Implementation Notes

For Option A, the simulation logic would:
1. Load and compile the loop spec
2. Start at initial state
3. For each iteration:
   - Display state name and action
   - Prompt for simulated result
   - Run evaluator with simulated output
   - Determine next state
   - Check for terminal or max iterations

The evaluator simulation would need mock inputs:
- `exit_code`: Ask for exit code number
- `output_contains`: Ask for sample output text
- `output_numeric`: Ask for numeric value
- `convergence`: Ask for current value
- `llm_structured`: Skip or mock with predefined verdicts

## Impact

- **Priority**: P4 (helpful for debugging, not essential)
- **Effort**: High (significant new feature)
- **Risk**: Low (read-only simulation)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | scripts/little_loops/fsm/executor.py | Execution logic to simulate |
| architecture | scripts/little_loops/fsm/evaluators.py | Evaluator logic to mock |
| cli | scripts/little_loops/cli.py | CLI to extend |

## Labels

`enhancement`, `ll-loop`, `debugging`, `simulation`, `captured`

---

## Status

**Open** | Created: 2026-01-23 | Priority: P4
