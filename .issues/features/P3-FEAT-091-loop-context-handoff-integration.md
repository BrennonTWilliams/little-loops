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
6. Spawn new Claude session: claude -p "<continuation>"
7. New session resumes loop via ll-loop resume <name>
```

## Architecture: Hybrid Layered Approach

The implementation uses a layered architecture that keeps the core executor clean while providing automatic handoff support:

```
┌─────────────────────────────────────┐
│  FSM Executor (core)                │  <- No handoff knowledge
│  - State transitions                │
│  - Action execution                 │
│  - Callbacks/hooks for results      │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  Output Signal Detector             │  <- Detects CONTEXT_HANDOFF:, errors, etc.
│  - Pattern matching                 │
│  - Extensible for other signals     │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  Handoff Handler (Claude-specific)  │  <- spawn/pause/terminate logic
└─────────────────────────────────────┘
```

**Benefits of this layering:**
1. **Core executor stays clean** - Testable without Claude dependencies
2. **Signal detection is reusable** - Can detect other patterns like `ERROR:`, `STOP:`
3. **Handoff handling is isolated** - Claude-specific spawning logic in one place

## Technical Details

### Output Signal Detector (New Module)

```python
# In scripts/little_loops/fsm/signal_detector.py
import re
from dataclasses import dataclass
from typing import Protocol

@dataclass
class DetectedSignal:
    """A signal detected in command output."""
    signal_type: str  # "handoff", "error", "stop", etc.
    payload: str | None
    raw_match: str

class SignalPattern:
    """Configurable signal pattern."""
    def __init__(self, name: str, pattern: str):
        self.name = name
        self.regex = re.compile(pattern, re.MULTILINE)

    def search(self, output: str) -> DetectedSignal | None:
        match = self.regex.search(output)
        if match:
            return DetectedSignal(
                signal_type=self.name,
                payload=match.group(1).strip() if match.groups() else None,
                raw_match=match.group(0)
            )
        return None

# Built-in signal patterns
HANDOFF_SIGNAL = SignalPattern("handoff", r'CONTEXT_HANDOFF:\s*(.+)')
ERROR_SIGNAL = SignalPattern("error", r'FATAL_ERROR:\s*(.+)')
STOP_SIGNAL = SignalPattern("stop", r'LOOP_STOP:\s*(.*)')

class SignalDetector:
    """Detect signals in command output."""

    def __init__(self, patterns: list[SignalPattern] | None = None):
        self.patterns = patterns or [HANDOFF_SIGNAL, ERROR_SIGNAL, STOP_SIGNAL]

    def detect(self, output: str) -> list[DetectedSignal]:
        """Detect all signals in output."""
        return [
            signal for pattern in self.patterns
            if (signal := pattern.search(output)) is not None
        ]

    def detect_first(self, output: str) -> DetectedSignal | None:
        """Detect first matching signal."""
        for pattern in self.patterns:
            if signal := pattern.search(output):
                return signal
        return None
```

### Handoff Handler (Claude-specific)

```python
# In scripts/little_loops/fsm/handoff_handler.py
import subprocess
from dataclasses import dataclass
from enum import Enum

class HandoffBehavior(Enum):
    TERMINATE = "terminate"  # Stop loop execution
    PAUSE = "pause"          # Save state, exit, require manual resume
    SPAWN = "spawn"          # Save state, spawn continuation session

@dataclass
class HandoffResult:
    """Result of handling a handoff signal."""
    behavior: HandoffBehavior
    continuation_prompt: str | None
    spawned_process: subprocess.Popen | None = None

class HandoffHandler:
    """Handle context handoff signals."""

    def __init__(self, behavior: HandoffBehavior = HandoffBehavior.PAUSE):
        self.behavior = behavior

    def handle(self, loop_name: str, continuation: str) -> HandoffResult:
        """Handle a detected handoff signal."""
        if self.behavior == HandoffBehavior.TERMINATE:
            return HandoffResult(self.behavior, continuation)

        if self.behavior == HandoffBehavior.PAUSE:
            # State saving handled by executor
            return HandoffResult(self.behavior, continuation)

        if self.behavior == HandoffBehavior.SPAWN:
            process = self._spawn_continuation(loop_name, continuation)
            return HandoffResult(self.behavior, continuation, process)

        raise ValueError(f"Unknown behavior: {self.behavior}")

    def _spawn_continuation(self, loop_name: str, continuation: str) -> subprocess.Popen:
        """Spawn new Claude session to continue loop."""
        prompt = f"Continue loop execution. Run: ll-loop resume {loop_name}\n\n{continuation}"
        cmd = ["claude", "-p", prompt]
        return subprocess.Popen(cmd)
```

### Modified Executor Integration

```python
# In executor.py - executor uses signal detector via callback
class FSMExecutor:
    def __init__(self, ..., signal_detector: SignalDetector | None = None,
                 handoff_handler: HandoffHandler | None = None):
        self.signal_detector = signal_detector
        self.handoff_handler = handoff_handler

    def _execute_state(self, state: StateConfig) -> ActionResult:
        result = self.action_runner.run(action)

        # Signal detection is optional - executor works without it
        if self.signal_detector:
            signal = self.signal_detector.detect_first(result.output)
            if signal and signal.signal_type == "handoff":
                return self._handle_handoff(signal, result)

        return result

    def _handle_handoff(self, signal: DetectedSignal, result: ActionResult) -> ActionResult:
        """Handle handoff signal if handler configured."""
        if not self.handoff_handler:
            # No handler = terminate (backward compatible)
            return ActionResult(
                exit_code=0, output=result.output,
                handoff=True, continuation=signal.payload
            )

        handoff_result = self.handoff_handler.handle(
            self.loop_name, signal.payload
        )

        # Update state for pause/spawn
        if handoff_result.behavior in (HandoffBehavior.PAUSE, HandoffBehavior.SPAWN):
            self.state.status = "awaiting_continuation"
            self.state.continuation_prompt = signal.payload
            self._save_state()

        return ActionResult(
            exit_code=0, output=result.output,
            handoff=True, continuation=signal.payload,
            handoff_behavior=handoff_result.behavior.value
        )
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
on_handoff: "spawn"  # "pause" (default) | "spawn" | "terminate"
states:
  # ...
```

| Value | Behavior |
|-------|----------|
| `pause` | Save state, exit, require manual resume **(default)** |
| `spawn` | Save state, spawn continuation session automatically |
| `terminate` | Stop loop immediately (legacy behavior) |

**Rationale for `pause` as default:**
- Most useful behavior - preserves state for later resumption
- Safe - no automatic process spawning without explicit opt-in
- Backward compatible - loops still stop, just with saved state

## Acceptance Criteria

### Architecture
- [ ] `SignalDetector` class implemented in `scripts/little_loops/fsm/signal_detector.py`
- [ ] `HandoffHandler` class implemented in `scripts/little_loops/fsm/handoff_handler.py`
- [ ] Executor accepts optional `signal_detector` and `handoff_handler` parameters
- [ ] Core executor works without signal detection (backward compatible)

### Signal Detection
- [ ] Detects `CONTEXT_HANDOFF:` pattern in action output
- [ ] Detects `FATAL_ERROR:` pattern for error signals
- [ ] Detects `LOOP_STOP:` pattern for explicit stop signals
- [ ] Signal patterns are extensible via `SignalPattern` class

### Handoff Handling
- [ ] State saved with `awaiting_continuation` status on pause/spawn
- [ ] Continuation prompt preserved in state file
- [ ] `on_handoff: pause` saves state and exits (default)
- [ ] `on_handoff: spawn` launches new Claude session via CLI
- [ ] `on_handoff: terminate` stops without saving continuation state

### CLI Integration
- [ ] `ll-loop resume` handles `awaiting_continuation` status
- [ ] Resume displays continuation context to user
- [ ] Optional `on_handoff` config in loop YAML schema

### Testing
- [ ] Unit tests for `SignalDetector` patterns
- [ ] Unit tests for `HandoffHandler` behaviors
- [ ] Integration tests verify handoff → resume cycle

## Testing Requirements

```python
class TestSignalDetector:
    """Tests for signal_detector.py"""

    def test_handoff_detection(self):
        """Detect handoff signal in output."""
        detector = SignalDetector()
        output = "Running check...\nCONTEXT_HANDOFF: Continue from iteration 5\nDone."
        signal = detector.detect_first(output)
        assert signal is not None
        assert signal.signal_type == "handoff"
        assert signal.payload == "Continue from iteration 5"

    def test_error_detection(self):
        """Detect error signal in output."""
        detector = SignalDetector()
        output = "Processing...\nFATAL_ERROR: Database connection failed"
        signal = detector.detect_first(output)
        assert signal.signal_type == "error"
        assert signal.payload == "Database connection failed"

    def test_stop_detection(self):
        """Detect stop signal in output."""
        detector = SignalDetector()
        output = "LOOP_STOP: User requested termination"
        signal = detector.detect_first(output)
        assert signal.signal_type == "stop"

    def test_no_signal(self):
        """Normal output without signals."""
        detector = SignalDetector()
        output = "All checks passed."
        signal = detector.detect_first(output)
        assert signal is None

    def test_multiple_signals(self):
        """Detect all signals in output."""
        detector = SignalDetector()
        output = "CONTEXT_HANDOFF: foo\nFATAL_ERROR: bar"
        signals = detector.detect(output)
        assert len(signals) == 2

    def test_custom_pattern(self):
        """Custom signal patterns work."""
        custom = SignalPattern("custom", r'MY_SIGNAL:\s*(.+)')
        detector = SignalDetector(patterns=[custom])
        signal = detector.detect_first("MY_SIGNAL: hello")
        assert signal.signal_type == "custom"


class TestHandoffHandler:
    """Tests for handoff_handler.py"""

    def test_terminate_behavior(self):
        """Terminate returns without spawning."""
        handler = HandoffHandler(HandoffBehavior.TERMINATE)
        result = handler.handle("test-loop", "continuation prompt")
        assert result.behavior == HandoffBehavior.TERMINATE
        assert result.spawned_process is None

    def test_pause_behavior(self):
        """Pause returns without spawning."""
        handler = HandoffHandler(HandoffBehavior.PAUSE)
        result = handler.handle("test-loop", "continuation prompt")
        assert result.behavior == HandoffBehavior.PAUSE
        assert result.continuation_prompt == "continuation prompt"
        assert result.spawned_process is None

    def test_spawn_behavior(self, mocker):
        """Spawn launches Claude process."""
        mock_popen = mocker.patch('subprocess.Popen')
        handler = HandoffHandler(HandoffBehavior.SPAWN)
        result = handler.handle("test-loop", "continuation prompt")
        assert result.behavior == HandoffBehavior.SPAWN
        mock_popen.assert_called_once()
        assert "claude" in mock_popen.call_args[0][0]


class TestExecutorHandoffIntegration:
    """Integration tests for executor + signal handling"""

    def test_state_saved_on_handoff(self, tmp_path):
        """State preserved when handoff detected."""
        # Setup executor with signal detector and pause handler
        # Run action that returns CONTEXT_HANDOFF:
        # Verify state file has awaiting_continuation status
        pass

    def test_resume_from_handoff(self, tmp_path):
        """Resume picks up from handoff state."""
        # Create state file with awaiting_continuation
        # Run ll-loop resume
        # Verify execution continues from saved state
        pass

    def test_executor_without_detector(self):
        """Executor works without signal detection (backward compat)."""
        # Create executor without signal_detector
        # Run action with CONTEXT_HANDOFF: in output
        # Verify no special handling occurs
        pass
```

## Notes

### Design Rationale

The layered architecture was chosen to:
- **Keep the core executor testable** without Claude-specific dependencies
- **Enable extensibility** - `SignalDetector` can detect any pattern, not just handoff
- **Support future signals** - `FATAL_ERROR:`, `LOOP_STOP:`, or custom patterns
- **Allow opt-in complexity** - Simple loops work without any signal handling

### Implementation Notes

- This feature enables truly long-running loops that can span multiple Claude sessions
- Integrates with existing `/ll:handoff` command infrastructure
- `ll-auto` and `ll-parallel` can leverage `spawn` behavior for orchestrated execution
- Consider rate limiting continuation spawns to prevent runaway loops (future enhancement)

## Reference

- Design doc: `docs/generalized-fsm-loop.md` section "Future Considerations"
- Handoff protocol: `docs/claude-cli-integration-mechanics.md` section "Context Handoff Protocol"
- Existing handoff: `scripts/little_loops/subprocess_utils.py`

### New Modules (to be created)

- `scripts/little_loops/fsm/signal_detector.py` - Signal detection layer
- `scripts/little_loops/fsm/handoff_handler.py` - Claude-specific handoff handling

---

## Verification Notes

**Verified: 2026-01-18**

- Blocker FEAT-046 (State Persistence and Events) is now **completed** (in `.issues/completed/`)
- Blocker FEAT-047 (ll-loop CLI Tool) is now **completed** (in `.issues/completed/`)
- This feature is now **unblocked** and ready for implementation

**Updated: 2026-01-18**

- Revised to use hybrid layered architecture (SignalDetector + HandoffHandler)
- Changed default `on_handoff` behavior from `terminate` to `pause`
- Added extensible signal pattern system for future signals

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-18
- **Status**: Completed

### Changes Made

- `scripts/little_loops/fsm/signal_detector.py` [CREATED]: SignalDetector class with extensible pattern-based signal detection for CONTEXT_HANDOFF:, FATAL_ERROR:, LOOP_STOP:
- `scripts/little_loops/fsm/handoff_handler.py` [CREATED]: HandoffHandler class with pause/spawn/terminate behaviors
- `scripts/little_loops/fsm/schema.py` [MODIFIED]: Added `on_handoff` field to FSMLoop dataclass
- `scripts/little_loops/fsm/persistence.py` [MODIFIED]: Added `continuation_prompt` to LoopState, updated PersistentExecutor to handle handoffs with `awaiting_continuation` status
- `scripts/little_loops/fsm/executor.py` [MODIFIED]: Added signal_detector and handoff_handler parameters, `_handle_handoff` method, handoff fields to ExecutionResult
- `scripts/little_loops/fsm/__init__.py` [MODIFIED]: Exported new classes
- `scripts/little_loops/cli.py` [MODIFIED]: Updated cmd_status and cmd_resume to display continuation context
- `scripts/tests/test_signal_detector.py` [CREATED]: 17 unit tests for SignalDetector
- `scripts/tests/test_handoff_handler.py` [CREATED]: 10 unit tests for HandoffHandler

### Verification Results

- Tests: PASS (1390 tests, all passing)
- Types: PASS (mypy strict, no issues)
- Lint: PASS (ruff, all checks passed)

---

## Status

**Completed** | Created: 2026-01-17 | Completed: 2026-01-18 | Priority: P3
