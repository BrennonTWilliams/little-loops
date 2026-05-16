---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 93
outcome_confidence: 93
---

# FEAT-632: `cmd_test` silently skips slash-command states — no evaluation possible for majority of real loops

## Summary

The `ll-loop test` subcommand immediately exits with code 0 and "SKIPPED" when the target state uses a slash command or prompt action type. Since most production loops are built around slash commands (`/ll:check-code`, `/ll:manage-issue`, etc.), the test command provides no diagnostic value for the majority of real-world loop configurations.

## Location

- **File**: `scripts/little_loops/cli/loop/testing.py`
- **Line(s)**: 63–69 (at scan commit: 12a6af0)
- **Anchor**: `in function cmd_test()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/cli/loop/testing.py#L63-L69)
- **Code**:
```python
if is_slash:
    print("Note: Slash commands require Claude CLI; skipping actual execution.")
    print()
    print("Verdict: SKIPPED (slash command)")
    print()
    print("\u2713 Loop structure is valid (slash command not executed)")
    return 0
```

The `cmd_simulate` function in the same file uses `SimulationActionRunner` which does run full FSM simulation for slash-command states (prompting interactively or using a `--scenario`). `cmd_test` has no equivalent path.

## Current Behavior

`ll-loop test myloop evaluate` exits immediately with SKIPPED if the `evaluate` state uses a slash command. The user gets no feedback on whether their routing logic, evaluator configuration, or state transitions are correct.

## Expected Behavior

`cmd_test` should offer a simulation mode for slash-command states rather than bailing out. Options:
1. Prompt the user to provide a simulated exit code (matching `cmd_simulate`'s interactive mode)
2. Accept a `--exit-code` flag to specify the simulated result
3. Automatically run `cmd_simulate` on the target state instead

## Motivation

Most production loops are built around slash commands (`/ll:check-code`, `/ll:manage-issue`, `/ll:run-tests`, etc.). Because `cmd_test` exits immediately with SKIPPED for any slash-command state, the test subcommand is functionally useless for the majority of real-world loop configurations. Users have no way to verify routing logic, evaluator configuration, or FSM transitions before running a loop in production — increasing the risk of misconfigured loops silently looping or stalling. This feature restores diagnostic value to `ll-loop test` for the loop types that users actually build.

## Use Case

A user is building a `goal`-paradigm loop with `evaluate_type: llm_structured`. Before running the full loop, they want to verify that the routing is correct: if evaluate succeeds, does the FSM reach `done`? If it fails, does it route to `fix`? They run `ll-loop test myloop evaluate` and expect to see routing traced through the FSM. Instead, they see `SKIPPED`.

## Acceptance Criteria

- `ll-loop test myloop <state>` on a slash-command state does not exit immediately with SKIPPED
- The user is shown routing and transition information for the tested state
- At minimum: `ll-loop test --exit-code 0 myloop evaluate` simulates success and traces the resulting route
- `ll-loop test --exit-code 1 myloop evaluate` simulates failure and traces the resulting route

## API/Interface

New `--exit-code` argument added to the `test` subparser:

```
ll-loop test [--exit-code N] <loop-name> <state-name>
```

- `--exit-code N` (int, optional): Simulated exit code for slash-command states. When provided, `cmd_test` uses `SimulationActionRunner` with this exit code instead of bailing out with SKIPPED. If omitted and the state is a slash command, falls back to interactive prompt (same as `cmd_simulate`).

No changes to existing positional arguments or other flags.

## Proposed Solution

Add `--exit-code N` support to `cmd_test` for slash-command states, using `SimulationActionRunner` internally:

```python
if is_slash:
    exit_code = getattr(args, "exit_code", None)
    if exit_code is None:
        # Fall back to interactive prompt (same as cmd_simulate)
        exit_code = _prompt_result()
    # Run simulation with provided exit code
    runner = SimulationActionRunner(scenario="all-pass", ...)
    # Override to return specified exit_code
    ...
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/testing.py` — `cmd_test()`, add `--exit-code` arg
- `scripts/little_loops/cli/loop/__init__.py` — test_parser argument additions

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `SimulationActionRunner` to reuse

### Tests
- `scripts/tests/` — add tests for `cmd_test` with slash-command state and `--exit-code`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `--exit-code` argument to the `test` subparser in `__init__.py`
2. In `cmd_test()`, replace the immediate SKIPPED exit with a simulation path using `SimulationActionRunner`
3. Show routing trace (target state → verdict → next state) as the test output
4. Add tests

## Impact

- **Priority**: P3 — Most loop users run slash-command loops; the test command is currently useless for them
- **Effort**: Medium — Requires integrating `SimulationActionRunner` into `cmd_test`, but the pieces exist
- **Risk**: Low — Additive change; SKIPPED path remains for users without `--exit-code` or interactive mode
- **Breaking Change**: No

## Labels

`feature`, `fsm`, `cli`, `loop`, `testing`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/99c55e6a-35b9-4d6a-9bb6-0f7896598fc3.jsonl`

---

## Resolution

**Completed** | 2026-03-07

- Added `--exit-code N` argument to the `test` subparser in `scripts/little_loops/cli/loop/__init__.py`
- Replaced the immediate SKIPPED early return in `cmd_test()` with a simulation path:
  - If `--exit-code N` is provided, uses it as the simulated exit code directly
  - If omitted, falls back to `SimulationActionRunner` interactive prompt (same as `cmd_simulate`)
- Both paths create a synthetic `ActionResult` and fall through to the normal evaluation/routing display
- Updated existing `test_test_slash_command_skipped` test to reflect new behavior
- Added 3 new tests in `TestCmdTest` covering `--exit-code 0`, `--exit-code 1`, and interactive fallback

## Status

**Completed** | Created: 2026-03-07 | Priority: P3
