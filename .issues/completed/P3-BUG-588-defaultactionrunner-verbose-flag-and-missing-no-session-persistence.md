---
discovered_date: 2026-03-05
discovered_by: manual_audit
---

# BUG-588: DefaultActionRunner uses --verbose flag and missing --no-session-persistence

## Summary

`DefaultActionRunner.run()` in `scripts/little_loops/fsm/executor.py` had two CLI flag issues when invoking `claude -p` for slash command actions:

1. `--verbose` was included, which outputs turn-by-turn debug info and risks polluting the stdout that evaluators parse for signals.
2. `--no-session-persistence` was absent, causing unnecessary session accumulation on disk for every loop iteration.

## Location

- **File**: `scripts/little_loops/fsm/executor.py`
- **Class**: `DefaultActionRunner`
- **Method**: `run()` (line ~145)

## Actual Behavior

```python
cmd = [
    "claude",
    "--dangerously-skip-permissions",
    "--verbose",        # pollutes stdout / large stderr noise
    "-p",
    action,
]
```

- `--verbose` dumps turn-by-turn output alongside the final response, risking false matches in `output_contains`, `output_numeric`, and `output_json` evaluators.
- No `--no-session-persistence` means each loop action creates a persisted Claude session.

## Expected Behavior

```python
cmd = [
    "claude",
    "--dangerously-skip-permissions",
    "--no-session-persistence",
    "-p",
    action,
]
```

- Clean text output to stdout for evaluator parsing.
- No session files written for ephemeral loop actions.

## Root Cause

- `--verbose` was likely added to provide live progress via the `on_output_line` streaming callback, but `-p` with `subprocess.Popen` already streams stdout line-by-line without it.
- `--no-session-persistence` was present in `evaluate_llm_structured()` but not propagated to `DefaultActionRunner`.

## Implementation Steps

1. Remove `--verbose` from the `DefaultActionRunner` CLI command list.
2. Add `--no-session-persistence` in its place.

## Integration Map

### Files Modified
- `scripts/little_loops/fsm/executor.py` — updated `DefaultActionRunner.run()` CLI flags

### Related
- `evaluate_llm_structured()` in `scripts/little_loops/fsm/evaluators.py` — correct reference implementation (uses `--output-format json` and `--no-session-persistence`)

## Impact

- **Priority**: P3
- **Effort**: Trivial
- **Risk**: Low

## Labels

`bug`, `fsm`, `cli-integration`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-03-05
- **Status**: Completed

### Changes Made
- `scripts/little_loops/fsm/executor.py`: Removed `--verbose`, added `--no-session-persistence` to `DefaultActionRunner.run()` CLI command.

### Verification Results
- Tests: not run (flag-only change, no logic change)
- Lint: not run
- Types: not run

## Session Log
- Manual audit of `DefaultActionRunner.run()` against `docs/claude-code/cli-reference.md` — 2026-03-05

## Status

**Completed** | Created: 2026-03-05 | Completed: 2026-03-05 | Priority: P3
