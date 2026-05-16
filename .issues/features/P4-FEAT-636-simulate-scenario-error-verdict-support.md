---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# FEAT-636: `simulate --scenario` cannot produce `"error"` verdict — error-routing paths untestable non-interactively

## Summary

`SimulationActionRunner` supports four `--scenario` values: `all-pass`, `all-fail`, `first-fail`, and `alternating`. All four return either exit code `0` or `1`. Exit code `2` (which produces an `"error"` verdict in the evaluator) is only reachable through the interactive prompt path. A user wanting to test error-routing in a non-interactive simulation (e.g., in CI) cannot exercise the `"error"` verdict path.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Line(s)**: 255–271 (at scan commit: 12a6af0)
- **Anchor**: `in class SimulationActionRunner, method _scenario_result()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/executor.py#L255-L271)
- **Code**:
```python
def _scenario_result(self) -> int:
    if self.scenario == "all-pass":
        return 0
    elif self.scenario == "all-fail":
        return 1
    elif self.scenario == "first-fail":
        return 1 if self.call_count == 1 else 0
    elif self.scenario == "alternating":
        return 1 if self.call_count % 2 == 1 else 0
    return 0
```

Exit code `2` is only returned from `_prompt_result()` (interactive path).

## Current Behavior

`ll-loop simulate myloop --scenario all-fail` produces `"failure"` verdicts (exit code 1). There is no scenario that produces `"error"` verdicts (exit code 2), making it impossible to non-interactively test `on_error` routing paths in CI or automated testing.

## Expected Behavior

`--scenario all-error` should produce exit code `2` for all states. This enables testing `on_error` routing paths non-interactively.

## Motivation

`on_error` routing paths in FSM loops cannot be exercised non-interactively. Any CI pipeline or automated test suite that wants to verify error-routing behavior (e.g., that the loop terminates on `"error"` verdict rather than cycling) has no way to trigger exit code 2 without simulating interactive input. This blocks test coverage for error paths in goal-paradigm loops.

## Use Case

A developer has a `goal`-paradigm loop and wants to verify in CI that when the evaluator returns `"error"`, the loop terminates immediately (after fixing BUG-624) rather than cycling. They run:
```bash
ll-loop simulate myloop --scenario all-error --max-iterations 3
```
And verify the loop exits with `terminated_by=error` after the first state.

## Acceptance Criteria

- `--scenario all-error` is a valid scenario that returns exit code `2` for every state
- The `--scenario` help text documents that exit code 2 maps to `"error"` verdict
- Existing scenarios are unaffected

## API/Interface

```
ll-loop simulate <loop> --scenario {all-pass,all-fail,first-fail,alternating,all-error}
```

## Proposed Solution

Add `"all-error"` to `_scenario_result()`:

```python
elif self.scenario == "all-error":
    return 2
```

And add `"all-error"` to the `choices` list in the `simulate` subparser.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `SimulationActionRunner._scenario_result()`
- `scripts/little_loops/cli/loop/__init__.py` — add `"all-error"` to `--scenario` choices (line 195 `choices` list)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/testing.py` — imports/uses `SimulationActionRunner`; verify no hardcoded scenario list
- `scripts/tests/test_ll_loop_execution.py` — integration tests exercising simulate paths; may need `all-error` coverage

### Similar Patterns
- N/A — scenario dispatch is a single `_scenario_result()` method; no other files replicate this pattern

### Tests
- `scripts/tests/test_fsm_executor.py` — add unit test: `all-error` scenario returns exit code 2 every call

### Documentation
- N/A — help text update via `--scenario` choices/metavar handles user-facing docs inline

### Configuration
- N/A

## Implementation Steps

1. Add `"all-error"` case to `SimulationActionRunner._scenario_result()`
2. Add `"all-error"` to `--scenario` choices in `simulate` subparser
3. Add test

## Impact

- **Priority**: P4 — Small usability gap for users testing error-routing paths; interactive workaround exists
- **Effort**: Small — Two-line addition
- **Risk**: Low — Purely additive
- **Breaking Change**: No

## Labels

`feature`, `fsm`, `cli`, `loop`, `testing`, `captured`

## Verification Notes

- **Verdict**: VALID (verified 2026-03-07)
- `_scenario_result()` confirmed at lines 268–284 in `executor.py` (minor line drift from scan commit 12a6af0; code unchanged)
- `--scenario` choices confirmed as `["all-pass","all-fail","first-fail","alternating"]` at `cli/loop/__init__.py:195`; `"all-error"` absent as described
- `_prompt_result()` confirmed as the only path returning exit code 2 (interactive path only)

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:format-issue` - 2026-03-07T07:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`

## Resolution

**Completed** | 2026-03-07

### Changes Made
- `scripts/little_loops/fsm/executor.py`: Added `"all-error"` case to `_scenario_result()` returning exit code 2; added `"all-error"` entry to `scenario_label` dict; updated docstring to mention exit code 2
- `scripts/little_loops/cli/loop/__init__.py`: Added `"all-error"` to `--scenario` choices; updated help text to document exit code mapping (0=success, 1=failure, 2=error)
- `scripts/tests/test_fsm_executor.py`: Added `test_scenario_all_error` verifying exit code 2 for all three calls

### Verification
- All 3366 tests pass
- Ruff lint: no issues

## Status

**Completed** | Created: 2026-03-07 | Priority: P4
