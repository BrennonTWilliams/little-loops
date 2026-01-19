# FEAT-091: Loop Context Handoff Integration

## Summary

Enable FSM loop executor to detect `CONTEXT_HANDOFF:` signals from slash commands and spawn continuation sessions while preserving loop state, instead of simply terminating.

## Priority

P3 - Enhancement for long-running automated tasks

## Dependencies

- FEAT-046: State Persistence and Events (completed)
- FEAT-047: ll-loop CLI Tool (completed)

## Description

Currently, when a slash command within a loop execution triggers a context handoff signal (due to context exhaustion), the loop simply terminates. This feature would allow the executor to:

1. **Detect handoff signals** - Parse `CONTEXT_HANDOFF:` markers from slash command output
2. **Preserve loop state** - Save current FSM state, captured variables, and iteration count
3. **Spawn continuation** - Launch a new Claude session with the continuation prompt
4. **Resume execution** - New session picks up loop execution from saved state

### Current Behavior

From `docs/generalized-fsm-loop.md`:
> Context handoff integration - Executor can detect `CONTEXT_HANDOFF:` signals from slash commands and spawn continuation sessions, preserving loop state transparently. Initial implementation may simply terminate.

### Proposed Behavior

```
Loop execution flow:
1. Execute slash command action
2. Command outputs CONTEXT_HANDOFF: <continuation-prompt>
3. Executor detects handoff signal
4. Save current loop state to .loops/.running/<name>.state.json
5. Extract continuation prompt from signal
6. Spawn new Claude session: claude --resume or claude -p "<continuation>"
7. New session resumes loop via ll-loop resume <name>
```

## Technical Details

### Handoff Detection

```python
# In executor.py or action_runner
HANDOFF_PATTERN = re.compile(r'CONTEXT_HANDOFF:\s*(.+)', re.MULTILINE)

def check_for_handoff(output: str) -> tuple[bool, str | None]:
    """Check if output contains handoff signal."""
    match = HANDOFF_PATTERN.search(output)
    if match:
        return True, match.group(1).strip()
    return False, None
```

### Modified Execution Flow

```python
class FSMExecutor:
    def _execute_state(self, state: StateConfig) -> ActionResult:
        result = self.action_runner.run(action)

        # Check for handoff signal
        handoff, continuation = check_for_handoff(result.output)
        if handoff:
            self._handle_handoff(continuation)
            # Return special result indicating handoff
            return ActionResult(
                exit_code=0,
                output=result.output,
                handoff=True,
                continuation=continuation
            )

        return result

    def _handle_handoff(self, continuation: str):
        """Save state and prepare for continuation."""
        # State is already being saved by PersistentExecutor
        # Mark state as "awaiting_continuation"
        self.state.status = "awaiting_continuation"
        self.state.continuation_prompt = continuation
        self._save_state()
```

### Continuation Spawning

```python
# In cli or separate handoff module
def spawn_continuation(loop_name: str, continuation: str):
    """Spawn new Claude session to continue loop."""
    # Option 1: Use claude CLI with resume instruction
    cmd = [
        "claude",
        "-p",
        f"Continue loop execution. Run: ll-loop resume {loop_name}\n\n{continuation}"
    ]
    subprocess.Popen(cmd)

    # Option 2: Use ll-auto or ll-parallel infrastructure
    # This would integrate with existing orchestration
```

### State File Extension

```json
{
  "current_state": "fix",
  "iteration": 3,
  "captured": {"error_count": "5"},
  "status": "awaiting_continuation",
  "continuation_prompt": "Previous session ended due to context limits..."
}
```

### CLI Resume Enhancement

```bash
# Resume detects awaiting_continuation status
ll-loop resume fix-types
# Output: Resuming loop 'fix-types' from state 'fix' (iteration 3)
# Continuation context: Previous session ended due to context limits...
```

## Configuration

Add optional handoff behavior to FSM schema:

```yaml
name: "long-running-fix"
on_handoff: "spawn"  # "spawn" | "terminate" | "pause"
states:
  # ...
```

| Value | Behavior |
|-------|----------|
| `terminate` | Stop loop (current default) |
| `pause` | Save state, exit, require manual resume |
| `spawn` | Save state, spawn continuation session |

## Acceptance Criteria

- [ ] Executor detects `CONTEXT_HANDOFF:` pattern in action output
- [ ] State is saved with `awaiting_continuation` status
- [ ] Continuation prompt is preserved in state file
- [ ] `ll-loop resume` handles `awaiting_continuation` status
- [ ] Optional `on_handoff` config controls behavior
- [ ] Default behavior remains `terminate` for backwards compatibility
- [ ] Integration tests verify handoff → resume cycle

## Testing Requirements

```python
class TestContextHandoff:
    def test_handoff_detection(self):
        """Detect handoff signal in output."""
        output = "Running check...\nCONTEXT_HANDOFF: Continue from iteration 5\nDone."
        handoff, continuation = check_for_handoff(output)
        assert handoff is True
        assert continuation == "Continue from iteration 5"

    def test_no_handoff(self):
        """Normal output without handoff."""
        output = "All checks passed."
        handoff, _ = check_for_handoff(output)
        assert handoff is False

    def test_state_saved_on_handoff(self, tmp_path):
        """State preserved when handoff detected."""
        # Setup executor with mock action that returns handoff
        # Verify state file has awaiting_continuation status
        pass

    def test_resume_from_handoff(self, tmp_path):
        """Resume picks up from handoff state."""
        # Create state file with awaiting_continuation
        # Run ll-loop resume
        # Verify execution continues from saved state
        pass

    def test_on_handoff_terminate(self):
        """on_handoff: terminate stops loop."""
        pass

    def test_on_handoff_spawn(self):
        """on_handoff: spawn launches continuation."""
        # Would need to mock subprocess.Popen
        pass
```

## Notes

- This feature enables truly long-running loops that can span multiple Claude sessions
- Integrates with existing `/ll:handoff` command infrastructure
- May require coordination with `ll-auto` and `ll-parallel` for orchestrated execution
- Consider rate limiting continuation spawns to prevent runaway loops

## Reference

- Design doc: `docs/generalized-fsm-loop.md` section "Future Considerations"
- Handoff protocol: `docs/claude-cli-integration-mechanics.md` section "Context Handoff Protocol"
- Existing handoff: `scripts/little_loops/subprocess_utils.py`

---

## Verification Notes

**Verified: 2026-01-18**

- Blocker FEAT-046 (State Persistence and Events) is now **completed** (in `.issues/completed/`)
- Blocker FEAT-047 (ll-loop CLI Tool) is now **completed** (in `.issues/completed/`)
- This feature is now **unblocked** and ready for implementation

---

## Status

**Open** | Created: 2026-01-17 | Priority: P3
