# ENH-109: Add action_type field to FSM state config - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P2-ENH-109-fsm-action-type-field-for-prompts.md
- **Type**: enhancement
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The FSM executor currently determines action type using a simple heuristic:
- Actions starting with `/` are treated as slash commands and executed via Claude CLI
- All other actions are treated as shell commands and executed via `bash -c`

### Key Discoveries
- `executor.py:392` - `is_slash_command=action.startswith("/")` determines action type
- `executor.py:138-148` - `DefaultActionRunner.run()` branches on `is_slash_command` boolean
- `executor.py:439-449` - Default evaluation also uses `state.action.startswith("/")` heuristic
- `schema.py:185-195` - `StateConfig` has no `action_type` field
- `fsm-loop-schema.json:69-122` - JSON schema's `stateConfig` definition has no `action_type` property

### Pattern from codebase
- Optional fields use `str | None = None` pattern (e.g., `capture`, `timeout`)
- `Literal` types used for constrained strings (e.g., `EvaluateConfig.type`)
- `to_dict()` only includes non-None values
- `from_dict()` uses `data.get("field")` for optional fields

## Desired End State

- States can specify `action_type: prompt`, `action_type: slash_command`, or `action_type: shell`
- When `action_type: prompt`, execute via Claude CLI regardless of whether action starts with `/`
- Backward compatible: if `action_type` is omitted, use current heuristic

### How to Verify
- Test that `action_type: prompt` causes action to be executed via Claude CLI
- Test that `action_type: shell` causes action to be executed via bash
- Test that omitting `action_type` maintains current behavior
- Existing tests continue to pass

## What We're NOT Doing

- Not adding validation that `action_type` and `action` are both present (action_type without action is harmless)
- Not changing the ActionRunner Protocol (we'll compute is_slash_command before calling it)
- Not adding new evaluator types or changing evaluation defaults (out of scope)

## Problem Analysis

Plain prompts intended for Claude that don't start with `/` are incorrectly executed as bash commands. For example:
```yaml
states:
  analyze:
    action: "Analyze the test failures and fix them"  # This runs as bash!
```

This fails because the action doesn't start with `/`, so it's treated as a shell command.

## Solution Approach

1. Add `action_type` field to `StateConfig` dataclass
2. Update JSON schema to include `action_type` property
3. Modify executor to use `action_type` when determining how to run actions
4. Maintain full backward compatibility with existing configs

## Implementation Phases

### Phase 1: Update Schema Dataclass

#### Overview
Add the `action_type` field to `StateConfig` in schema.py.

#### Changes Required

**File**: `scripts/little_loops/fsm/schema.py`
**Changes**: Add `action_type` field to `StateConfig`

At line 185, after the `action` field definition, add:
```python
action_type: Literal["prompt", "slash_command", "shell"] | None = None
```

Update `to_dict()` method (around line 197-224) to include:
```python
if self.action_type is not None:
    result["action_type"] = self.action_type
```

Update `from_dict()` method (around line 226-249) to include:
```python
action_type=data.get("action_type"),
```

Update docstring (around line 171-183) to document the new field.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_schema.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/schema.py`

---

### Phase 2: Update JSON Schema

#### Overview
Add `action_type` property to the `stateConfig` definition in fsm-loop-schema.json.

#### Changes Required

**File**: `scripts/little_loops/fsm/fsm-loop-schema.json`
**Changes**: Add `action_type` property to `stateConfig` definition

After the `action` property (around line 76), add:
```json
"action_type": {
  "type": "string",
  "description": "How to execute the action: prompt (Claude CLI), slash_command (Claude CLI), or shell (bash)",
  "enum": ["prompt", "slash_command", "shell"]
},
```

#### Success Criteria

**Automated Verification**:
- [ ] JSON schema is valid JSON
- [ ] Schema validation tests pass: `python -m pytest scripts/tests/test_fsm_schema.py -v`

---

### Phase 3: Update Executor

#### Overview
Modify the executor to use `action_type` from `StateConfig` when determining how to run actions.

#### Changes Required

**File**: `scripts/little_loops/fsm/executor.py`
**Changes**: Compute `is_slash_command` using `action_type` if present

In `_run_action()` method (around line 389-393), change:
```python
result = self.action_runner.run(
    action,
    timeout=state.timeout or 120,
    is_slash_command=action.startswith("/"),
)
```

To:
```python
# Determine if this is a slash command/prompt based on action_type or heuristic
if state.action_type is not None:
    is_slash_command = state.action_type in ("prompt", "slash_command")
else:
    is_slash_command = action.startswith("/")

result = self.action_runner.run(
    action,
    timeout=state.timeout or 120,
    is_slash_command=is_slash_command,
)
```

In `_evaluate()` method (around line 439), update the default evaluation logic:
```python
if state.evaluate is None:
    # Default evaluation based on action type
    if action_result:
        # Determine if this is a prompt/slash command for default evaluation
        if state.action_type is not None:
            is_prompt = state.action_type in ("prompt", "slash_command")
        else:
            is_prompt = state.action and state.action.startswith("/")

        if is_prompt:
            # Slash command or prompt: use LLM evaluation
            result = evaluate_llm_structured(
                action_result.output,
                model=self.fsm.llm.model,
                max_tokens=self.fsm.llm.max_tokens,
                timeout=self.fsm.llm.timeout,
            )
        else:
            # Shell command: use exit code
            result = evaluate_exit_code(action_result.exit_code)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_executor.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/executor.py`

---

### Phase 4: Add Unit Tests

#### Overview
Add tests for the new `action_type` field behavior.

#### Changes Required

**File**: `scripts/tests/test_fsm_schema.py`
**Changes**: Add tests for `action_type` field in StateConfig

```python
def test_action_type_field(self) -> None:
    """State with explicit action_type."""
    state = StateConfig(
        action="Analyze the code and fix bugs",
        action_type="prompt",
        on_success="done",
        on_failure="retry",
    )

    assert state.action_type == "prompt"

def test_action_type_roundtrip(self) -> None:
    """action_type survives serialization roundtrip."""
    original = StateConfig(
        action="echo hello",
        action_type="shell",
        on_success="done",
    )

    restored = StateConfig.from_dict(original.to_dict())

    assert restored.action_type == "shell"

def test_action_type_none_by_default(self) -> None:
    """action_type is None when not specified."""
    state = StateConfig(action="pytest")

    assert state.action_type is None
```

**File**: `scripts/tests/test_fsm_executor.py`
**Changes**: Add tests for action_type behavior in executor

```python
def test_action_type_prompt_uses_claude_cli(self) -> None:
    """action_type=prompt executes via Claude CLI even without / prefix."""
    fsm = FSMLoop(
        name="test",
        initial="analyze",
        states={
            "analyze": StateConfig(
                action="Analyze the code",
                action_type="prompt",
                on_success="done",
                on_failure="done",
            ),
            "done": StateConfig(terminal=True),
        },
    )
    mock_runner = MockActionRunner()
    mock_runner.always_return(exit_code=0, output="Analysis complete")

    executor = FSMExecutor(fsm, action_runner=mock_runner)
    # The mock doesn't actually check is_slash_command but we verify the call was made
    executor.run()

    assert "Analyze the code" in mock_runner.calls

def test_action_type_shell_uses_bash(self) -> None:
    """action_type=shell executes via bash even with / prefix."""
    fsm = FSMLoop(
        name="test",
        initial="run",
        states={
            "run": StateConfig(
                action="/usr/bin/ls",
                action_type="shell",
                on_success="done",
                on_failure="done",
            ),
            "done": StateConfig(terminal=True),
        },
    )
    mock_runner = MockActionRunner()
    mock_runner.always_return(exit_code=0)

    executor = FSMExecutor(fsm, action_runner=mock_runner)
    executor.run()

    assert "/usr/bin/ls" in mock_runner.calls

def test_action_type_none_uses_heuristic(self) -> None:
    """Without action_type, / prefix determines execution method."""
    # Test slash command detection
    fsm = FSMLoop(
        name="test",
        initial="cmd",
        states={
            "cmd": StateConfig(
                action="/ll:help",
                on_success="done",
                on_failure="done",
            ),
            "done": StateConfig(terminal=True),
        },
    )
    mock_runner = MockActionRunner()
    mock_runner.always_return(exit_code=0)

    executor = FSMExecutor(fsm, action_runner=mock_runner)
    executor.run()

    assert "/ll:help" in mock_runner.calls
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- StateConfig with action_type field construction
- to_dict()/from_dict() roundtrip with action_type
- Executor uses action_type when present
- Executor falls back to heuristic when action_type is None

### Integration Tests
- Existing tests continue to pass (backward compatibility)

## References

- Original issue: `.issues/enhancements/P2-ENH-109-fsm-action-type-field-for-prompts.md`
- StateConfig dataclass: `scripts/little_loops/fsm/schema.py:164-277`
- DefaultActionRunner: `scripts/little_loops/fsm/executor.py:117-169`
- _run_action method: `scripts/little_loops/fsm/executor.py:369-418`
- _evaluate method: `scripts/little_loops/fsm/executor.py:420-478`
- JSON schema stateConfig: `scripts/little_loops/fsm/fsm-loop-schema.json:69-122`
