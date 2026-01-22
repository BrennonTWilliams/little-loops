---
discovered_date: 2026-01-22
discovered_by: capture_issue
---

# ENH-109: Add action_type field to FSM state config for prompt actions

## Summary

The FSM executor currently only distinguishes between slash commands (actions starting with `/`) and shell commands (everything else). Plain prompts intended for Claude that don't start with `/` are incorrectly executed as bash commands.

An explicit `action_type` field should be added to the state config to support `prompt`, `slash_command`, and `shell` action types.

## Context

Identified from conversation discussing FSM prompt execution. The current implementation in `scripts/little_loops/fsm/executor.py:138-148` uses a simple heuristic:

```python
if is_slash_command:
    # Execute via Claude CLI
    cmd = ["claude", "--dangerously-skip-permissions", "-p", action]
else:
    # Shell command
    cmd = ["bash", "-c", action]
```

Where `is_slash_command` is determined by `action.startswith("/")`.

This fails for plain prompts like `"Analyze the test failures and fix them"` which would be incorrectly run as a bash command.

## Current Behavior

- Actions starting with `/` are executed via Claude CLI with `--dangerously-skip-permissions`
- All other actions are executed as shell commands via `bash -c`
- No way to specify a plain prompt for Claude

## Expected Behavior

- State config should support an explicit `action_type` field
- Valid values: `prompt`, `slash_command`, `shell` (or `bash`)
- When `action_type: prompt`, execute via Claude CLI regardless of whether action starts with `/`
- Maintain backward compatibility: if `action_type` is omitted, use current heuristic

## Proposed Solution

1. **Update FSM schema** (`scripts/little_loops/fsm/schema.py`):
   - Add `action_type: Optional[str]` field to `StateConfig`
   - Valid values: `"prompt"`, `"slash_command"`, `"shell"` (default inferred)

2. **Update executor** (`scripts/little_loops/fsm/executor.py`):
   - Modify `DefaultActionRunner.run()` to accept `action_type` parameter
   - Update logic:
     ```python
     if action_type == "prompt" or action_type == "slash_command" or action.startswith("/"):
         cmd = ["claude", "--dangerously-skip-permissions", "-p", action]
     else:
         cmd = ["bash", "-c", action]
     ```

3. **Update YAML parsing** to pass `action_type` through

4. **Update documentation** for FSM state config

## Impact

- **Priority**: P2 - Important for FSM usability with non-slash-command prompts
- **Effort**: Low - Schema and executor changes are straightforward
- **Risk**: Low - Backward compatible with existing configs

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/generalized-fsm-loop.md | FSM loop design documentation |

## Labels

`enhancement`, `fsm`, `captured`

---

## Status

**Completed** | Created: 2026-01-22 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-22
- **Status**: Completed

### Changes Made
- `scripts/little_loops/fsm/schema.py`: Added `action_type` field to `StateConfig` dataclass with `Literal["prompt", "slash_command", "shell"] | None` type, updated `to_dict()` and `from_dict()` methods
- `scripts/little_loops/fsm/fsm-loop-schema.json`: Added `action_type` property to `stateConfig` definition with enum constraint
- `scripts/little_loops/fsm/executor.py`: Updated `_run_action()` and `_evaluate()` methods to use `action_type` when present, falling back to heuristic when None
- `scripts/tests/test_fsm_schema.py`: Added 6 tests for `action_type` field behavior
- `scripts/tests/test_fsm_executor.py`: Added `TestActionType` class with 5 tests for executor behavior

### Verification Results
- Tests: PASS (1453 tests passed)
- Lint: PASS (ruff check)
- Types: PASS (mypy)
