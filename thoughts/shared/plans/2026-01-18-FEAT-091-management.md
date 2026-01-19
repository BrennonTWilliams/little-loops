# FEAT-091: Loop Context Handoff Integration - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-091-loop-context-handoff-integration.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The FSM executor system is a well-structured state-machine-based automation engine with clear separation of concerns:

### Key Discoveries
- `FSMExecutor` at `executor.py:172` handles main loop execution with support for optional event callbacks and custom action runners
- `DefaultActionRunner` at `executor.py:107` executes actions via subprocess, returning `ActionResult` with stdout/stderr/exit_code
- `PersistentExecutor` at `persistence.py:201` wraps FSMExecutor to add state persistence, saving state after `state_enter`, `route`, and `loop_complete` events
- `LoopState` at `persistence.py:36` captures all runtime state needed for resume, including `status` field for "running", "completed", "failed", "interrupted"
- Existing handoff detection in `subprocess_utils.py:24`: `CONTEXT_HANDOFF_PATTERN = re.compile(r"CONTEXT_HANDOFF:\s*Ready for fresh session")`
- `FSMLoop` schema at `schema.py:323` contains the loop configuration with `maintain`, `llm`, etc. - this is where `on_handoff` should be added

### Integration Points
- `_run_action()` at `executor.py:346` is where action output is available - ideal place for signal detection
- `_finish()` at `executor.py:536` handles loop termination - can be extended for handoff termination
- `_save_state()` at `persistence.py:269` creates `LoopState` - already handles status field
- `cmd_resume()` at `cli.py:864` handles resume - needs to support `awaiting_continuation` status

## Desired End State

After implementation:
1. FSM executor can detect `CONTEXT_HANDOFF:`, `FATAL_ERROR:`, and `LOOP_STOP:` signals in action output
2. When handoff is detected, executor saves state with `status="awaiting_continuation"`
3. `on_handoff` config option allows users to choose behavior: `pause` (default), `spawn`, or `terminate`
4. `ll-loop resume` handles `awaiting_continuation` status and displays continuation context
5. Architecture is layered and extensible for future signal types

### How to Verify
- Unit tests pass for SignalDetector and HandoffHandler
- Existing FSM executor tests continue to pass (backward compatibility)
- Integration test: loop with CONTEXT_HANDOFF in output saves state correctly
- `ll-loop resume` on `awaiting_continuation` state works correctly

## What We're NOT Doing

- **Not implementing automatic spawn behavior in this PR** - Will default to `pause`, spawn can be implemented later
- **Not modifying subprocess_utils.py** - SignalDetector is a new, more flexible pattern
- **Not changing existing handoff detection in ll-parallel** - That uses its own pattern
- **Not adding rate limiting for spawn** - Deferred to future enhancement per issue notes

## Problem Analysis

Currently, when a slash command outputs `CONTEXT_HANDOFF:`, the FSM executor treats it as normal output. The loop may continue or terminate based on normal evaluation, but there's no special handling for handoff signals. This means:
1. Loop state is lost when Claude signals context exhaustion
2. No way to resume from where the handoff occurred
3. No configuration option for users to control handoff behavior

## Solution Approach

Implement a layered architecture per the issue specification:

```
FSMExecutor (core) → SignalDetector → HandoffHandler
```

1. **SignalDetector** - Reusable signal detection with extensible patterns
2. **HandoffHandler** - Behavior handlers (pause/spawn/terminate)
3. **Executor integration** - Optional signal detection via callback pattern
4. **Schema extension** - Add `on_handoff` to FSMLoop
5. **Persistence extension** - Add `continuation_prompt` to LoopState
6. **CLI enhancement** - Resume displays continuation context

## Implementation Phases

### Phase 1: Create SignalDetector Module

#### Overview
Create the signal detection layer in a new file `scripts/little_loops/fsm/signal_detector.py`.

#### Changes Required

**File**: `scripts/little_loops/fsm/signal_detector.py`
**Changes**: Create new file with signal detection infrastructure

```python
"""Signal detection for FSM loop execution output.

This module provides pattern-based signal detection for interpreting
special markers in action output, such as CONTEXT_HANDOFF:, FATAL_ERROR:, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DetectedSignal:
    """A signal detected in command output.

    Attributes:
        signal_type: Type of signal (e.g., "handoff", "error", "stop")
        payload: Captured content after the signal marker
        raw_match: The full matched string
    """

    signal_type: str
    payload: str | None
    raw_match: str


class SignalPattern:
    """Configurable signal pattern for detection.

    Attributes:
        name: Signal type name
        regex: Compiled regex pattern
    """

    def __init__(self, name: str, pattern: str) -> None:
        """Initialize signal pattern.

        Args:
            name: Signal type name (e.g., "handoff")
            pattern: Regex pattern with optional capture group for payload
        """
        self.name = name
        self.regex = re.compile(pattern, re.MULTILINE)

    def search(self, output: str) -> DetectedSignal | None:
        """Search for this signal pattern in output.

        Args:
            output: Command output to search

        Returns:
            DetectedSignal if found, None otherwise
        """
        match = self.regex.search(output)
        if match:
            payload = match.group(1).strip() if match.groups() else None
            return DetectedSignal(
                signal_type=self.name,
                payload=payload,
                raw_match=match.group(0),
            )
        return None


# Built-in signal patterns
HANDOFF_SIGNAL = SignalPattern("handoff", r"CONTEXT_HANDOFF:\s*(.+)")
ERROR_SIGNAL = SignalPattern("error", r"FATAL_ERROR:\s*(.+)")
STOP_SIGNAL = SignalPattern("stop", r"LOOP_STOP:\s*(.*)")


class SignalDetector:
    """Detect signals in command output.

    Provides pattern-based signal detection with extensibility
    for custom signal types.
    """

    def __init__(self, patterns: list[SignalPattern] | None = None) -> None:
        """Initialize detector with patterns.

        Args:
            patterns: List of signal patterns to detect.
                     Defaults to built-in patterns (handoff, error, stop).
        """
        self.patterns = patterns or [HANDOFF_SIGNAL, ERROR_SIGNAL, STOP_SIGNAL]

    def detect(self, output: str) -> list[DetectedSignal]:
        """Detect all signals in output.

        Args:
            output: Command output to scan

        Returns:
            List of all detected signals
        """
        return [
            signal
            for pattern in self.patterns
            if (signal := pattern.search(output)) is not None
        ]

    def detect_first(self, output: str) -> DetectedSignal | None:
        """Detect first matching signal in output.

        Args:
            output: Command output to scan

        Returns:
            First detected signal, or None if no signals found
        """
        for pattern in self.patterns:
            if signal := pattern.search(output):
                return signal
        return None
```

#### Success Criteria

**Automated Verification**:
- [ ] New file created at correct path
- [ ] Tests pass: `python -m pytest scripts/tests/test_signal_detector.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/signal_detector.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/signal_detector.py`

---

### Phase 2: Create HandoffHandler Module

#### Overview
Create the handoff handling layer in a new file `scripts/little_loops/fsm/handoff_handler.py`.

#### Changes Required

**File**: `scripts/little_loops/fsm/handoff_handler.py`
**Changes**: Create new file with handoff behavior handling

```python
"""Handoff handling for FSM loop execution.

This module provides behavior handlers for context handoff signals,
supporting pause, spawn, and terminate behaviors.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum


class HandoffBehavior(Enum):
    """Behavior when a handoff signal is detected.

    Attributes:
        TERMINATE: Stop loop execution immediately
        PAUSE: Save state and exit, requiring manual resume
        SPAWN: Save state and spawn continuation session
    """

    TERMINATE = "terminate"
    PAUSE = "pause"
    SPAWN = "spawn"


@dataclass
class HandoffResult:
    """Result from handling a handoff signal.

    Attributes:
        behavior: The behavior that was applied
        continuation_prompt: The continuation prompt from the signal
        spawned_process: Popen object if spawn behavior was used
    """

    behavior: HandoffBehavior
    continuation_prompt: str | None
    spawned_process: subprocess.Popen[str] | None = None


class HandoffHandler:
    """Handle context handoff signals.

    Provides configurable behavior for when handoff signals are detected
    in loop action output.
    """

    def __init__(self, behavior: HandoffBehavior = HandoffBehavior.PAUSE) -> None:
        """Initialize handler with behavior.

        Args:
            behavior: How to handle handoff signals (default: pause)
        """
        self.behavior = behavior

    def handle(self, loop_name: str, continuation: str | None) -> HandoffResult:
        """Handle a detected handoff signal.

        Args:
            loop_name: Name of the loop for spawn commands
            continuation: Continuation prompt from the signal

        Returns:
            HandoffResult with behavior taken and any spawned process
        """
        if self.behavior == HandoffBehavior.TERMINATE:
            return HandoffResult(self.behavior, continuation)

        if self.behavior == HandoffBehavior.PAUSE:
            # State saving handled by executor
            return HandoffResult(self.behavior, continuation)

        if self.behavior == HandoffBehavior.SPAWN:
            process = self._spawn_continuation(loop_name, continuation)
            return HandoffResult(self.behavior, continuation, process)

        # Should never reach here, but satisfy type checker
        return HandoffResult(self.behavior, continuation)

    def _spawn_continuation(
        self, loop_name: str, continuation: str | None
    ) -> subprocess.Popen[str]:
        """Spawn new Claude session to continue loop.

        Args:
            loop_name: Name of the loop to resume
            continuation: Continuation context from handoff

        Returns:
            Popen object for the spawned process
        """
        prompt_parts = [f"Continue loop execution. Run: ll-loop resume {loop_name}"]
        if continuation:
            prompt_parts.append(f"\n\n{continuation}")
        prompt = "".join(prompt_parts)

        cmd = ["claude", "-p", prompt]
        return subprocess.Popen(cmd, text=True)
```

#### Success Criteria

**Automated Verification**:
- [ ] New file created at correct path
- [ ] Tests pass: `python -m pytest scripts/tests/test_handoff_handler.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/handoff_handler.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/handoff_handler.py`

---

### Phase 3: Extend Schema with on_handoff

#### Overview
Add `on_handoff` configuration option to `FSMLoop` schema.

#### Changes Required

**File**: `scripts/little_loops/fsm/schema.py`
**Changes**: Add `on_handoff` field to FSMLoop dataclass

At line 343-354 (after `maintain` field), add:
```python
    on_handoff: Literal["pause", "spawn", "terminate"] = "pause"
```

Update `to_dict()` method (around line 376):
```python
        if self.on_handoff != "pause":
            result["on_handoff"] = self.on_handoff
```

Update `from_dict()` method (around line 407):
```python
            on_handoff=data.get("on_handoff", "pause"),
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/schema.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/schema.py`
- [ ] Existing schema tests pass: `python -m pytest scripts/tests/test_fsm_schema.py -v`

---

### Phase 4: Extend LoopState with continuation_prompt

#### Overview
Add `continuation_prompt` field to `LoopState` for handoff context preservation.

#### Changes Required

**File**: `scripts/little_loops/fsm/persistence.py`
**Changes**: Add `continuation_prompt` field to LoopState dataclass

At line 66 (after `status` field), add:
```python
    continuation_prompt: str | None = None
```

Update `to_dict()` method to include:
```python
            "continuation_prompt": self.continuation_prompt,
```

Update `from_dict()` method to include:
```python
            continuation_prompt=data.get("continuation_prompt"),
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/persistence.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/persistence.py`
- [ ] Existing persistence tests pass: `python -m pytest scripts/tests/test_fsm_persistence.py -v`

---

### Phase 5: Integrate Signal Detection into Executor

#### Overview
Modify FSMExecutor to optionally detect signals in action output and handle handoffs.

#### Changes Required

**File**: `scripts/little_loops/fsm/executor.py`
**Changes**: Add signal_detector and handoff_handler parameters, detect signals after action execution

1. Add imports at top of file:
```python
from little_loops.fsm.signal_detector import DetectedSignal, SignalDetector
from little_loops.fsm.handoff_handler import HandoffBehavior, HandoffHandler, HandoffResult
```

2. Update `ExecutionResult` dataclass to add handoff info (around line 31):
```python
    handoff: bool = False
    continuation_prompt: str | None = None
```

3. Update `FSMExecutor.__init__` (around line 185) to accept optional parameters:
```python
    def __init__(
        self,
        fsm: FSMLoop,
        event_callback: EventCallback | None = None,
        action_runner: ActionRunner | None = None,
        signal_detector: SignalDetector | None = None,
        handoff_handler: HandoffHandler | None = None,
    ):
```

Store as instance variables:
```python
        self.signal_detector = signal_detector
        self.handoff_handler = handoff_handler
```

4. In `_run_action()` (around line 389, after action execution), add signal detection:
```python
        # Check for signals in output
        if self.signal_detector:
            signal = self.signal_detector.detect_first(result.output)
            if signal and signal.signal_type == "handoff":
                self._pending_handoff = signal
```

5. Add `_pending_handoff` attribute in `__init__`:
```python
        self._pending_handoff: DetectedSignal | None = None
```

6. In the main loop (around line 299, after state execution), check for pending handoff:
```python
                # Check for pending handoff
                if self._pending_handoff:
                    return self._handle_handoff(self._pending_handoff)
```

7. Add `_handle_handoff` method:
```python
    def _handle_handoff(self, signal: DetectedSignal) -> ExecutionResult:
        """Handle a detected handoff signal.

        Args:
            signal: The detected handoff signal

        Returns:
            ExecutionResult with handoff information
        """
        self._emit(
            "handoff_detected",
            {
                "state": self.current_state,
                "iteration": self.iteration,
                "continuation": signal.payload,
            },
        )

        if self.handoff_handler:
            result = self.handoff_handler.handle(self.fsm.name, signal.payload)
            # If spawn, the handler already started the process

        return ExecutionResult(
            final_state=self.current_state,
            iterations=self.iteration,
            terminated_by="handoff",
            duration_ms=_now_ms() - self.start_time_ms,
            captured=self.captured,
            handoff=True,
            continuation_prompt=signal.payload,
        )
```

8. Update `_finish` to emit handoff info if present.

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/executor.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/executor.py`
- [ ] Existing executor tests pass: `python -m pytest scripts/tests/test_fsm_executor.py -v`
- [ ] New executor tests pass with signal detection

---

### Phase 6: Update PersistentExecutor for Handoff

#### Overview
Modify PersistentExecutor to save `awaiting_continuation` status and continuation prompt.

#### Changes Required

**File**: `scripts/little_loops/fsm/persistence.py`
**Changes**: Update PersistentExecutor to handle handoff results

1. Update `__init__` to create executor with signal detector and handler based on FSM config:
```python
        # Create signal detector and handler based on FSM config
        from little_loops.fsm.signal_detector import SignalDetector
        from little_loops.fsm.handoff_handler import HandoffBehavior, HandoffHandler

        signal_detector = SignalDetector()
        handoff_handler = HandoffHandler(
            HandoffBehavior(getattr(fsm, "on_handoff", "pause"))
        )

        self._executor = FSMExecutor(
            fsm,
            event_callback=self._handle_event,
            signal_detector=signal_detector,
            handoff_handler=handoff_handler,
            **executor_kwargs,
        )
```

2. Update `run()` method (around line 304) to handle handoff termination:
```python
        if result.terminated_by == "handoff":
            final_status = "awaiting_continuation"
            # ... save with continuation_prompt
```

3. Update `resume()` to check for `awaiting_continuation` status and display continuation context.

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/persistence.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/persistence.py`
- [ ] All persistence tests pass: `python -m pytest scripts/tests/test_fsm_persistence.py -v`

---

### Phase 7: Update CLI for Continuation Context

#### Overview
Modify `cmd_resume` and `cmd_status` to display continuation context.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Update resume and status commands

1. In `cmd_status` (around line 843), add:
```python
        if state.continuation_prompt:
            print(f"Continuation context: {state.continuation_prompt[:200]}...")
```

2. In `cmd_resume` (around line 878), handle awaiting_continuation:
```python
        state = persistence.load_state()
        if state and state.status == "awaiting_continuation":
            print(f"Resuming from context handoff...")
            if state.continuation_prompt:
                print(f"Context: {state.continuation_prompt[:500]}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] CLI tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`

---

### Phase 8: Update Module Exports

#### Overview
Export new classes from `__init__.py`.

#### Changes Required

**File**: `scripts/little_loops/fsm/__init__.py`
**Changes**: Add exports for new modules

Add imports:
```python
from little_loops.fsm.signal_detector import (
    DetectedSignal,
    SignalDetector,
    SignalPattern,
    HANDOFF_SIGNAL,
    ERROR_SIGNAL,
    STOP_SIGNAL,
)
from little_loops.fsm.handoff_handler import (
    HandoffBehavior,
    HandoffHandler,
    HandoffResult,
)
```

Add to `__all__`:
```python
    "DetectedSignal",
    "SignalDetector",
    "SignalPattern",
    "HANDOFF_SIGNAL",
    "ERROR_SIGNAL",
    "STOP_SIGNAL",
    "HandoffBehavior",
    "HandoffHandler",
    "HandoffResult",
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/__init__.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/__init__.py`
- [ ] Import test passes

---

### Phase 9: Write Tests

#### Overview
Create comprehensive test files for new modules.

#### Changes Required

**File**: `scripts/tests/test_signal_detector.py`
**Changes**: Create new test file

```python
"""Tests for signal_detector module."""

import pytest

from little_loops.fsm.signal_detector import (
    DetectedSignal,
    SignalDetector,
    SignalPattern,
    HANDOFF_SIGNAL,
    ERROR_SIGNAL,
    STOP_SIGNAL,
)


class TestSignalPattern:
    """Tests for SignalPattern class."""

    def test_handoff_pattern_matches(self) -> None:
        """HANDOFF_SIGNAL matches CONTEXT_HANDOFF: with payload."""
        signal = HANDOFF_SIGNAL.search("CONTEXT_HANDOFF: Continue from iteration 5")
        assert signal is not None
        assert signal.signal_type == "handoff"
        assert signal.payload == "Continue from iteration 5"

    def test_error_pattern_matches(self) -> None:
        """ERROR_SIGNAL matches FATAL_ERROR: with payload."""
        signal = ERROR_SIGNAL.search("FATAL_ERROR: Database connection failed")
        assert signal is not None
        assert signal.signal_type == "error"
        assert signal.payload == "Database connection failed"

    def test_stop_pattern_matches(self) -> None:
        """STOP_SIGNAL matches LOOP_STOP: with optional payload."""
        signal = STOP_SIGNAL.search("LOOP_STOP: User requested")
        assert signal is not None
        assert signal.signal_type == "stop"
        assert signal.payload == "User requested"

    def test_custom_pattern(self) -> None:
        """Custom pattern works."""
        custom = SignalPattern("custom", r"MY_SIGNAL:\s*(.+)")
        signal = custom.search("MY_SIGNAL: hello world")
        assert signal is not None
        assert signal.signal_type == "custom"
        assert signal.payload == "hello world"


class TestSignalDetector:
    """Tests for SignalDetector class."""

    def test_detect_first_handoff(self) -> None:
        """Detect handoff signal in output."""
        detector = SignalDetector()
        output = "Running check...\nCONTEXT_HANDOFF: Continue from iteration 5\nDone."
        signal = detector.detect_first(output)
        assert signal is not None
        assert signal.signal_type == "handoff"
        assert signal.payload == "Continue from iteration 5"

    def test_detect_first_error(self) -> None:
        """Detect error signal in output."""
        detector = SignalDetector()
        output = "Processing...\nFATAL_ERROR: Database connection failed"
        signal = detector.detect_first(output)
        assert signal is not None
        assert signal.signal_type == "error"
        assert signal.payload == "Database connection failed"

    def test_no_signal(self) -> None:
        """Normal output without signals."""
        detector = SignalDetector()
        output = "All checks passed."
        signal = detector.detect_first(output)
        assert signal is None

    def test_detect_multiple(self) -> None:
        """Detect all signals in output."""
        detector = SignalDetector()
        output = "CONTEXT_HANDOFF: foo\nFATAL_ERROR: bar"
        signals = detector.detect(output)
        assert len(signals) == 2

    def test_multiline_output(self) -> None:
        """Finds signal in long multiline output."""
        detector = SignalDetector()
        output = """
        Processing issue BUG-001...
        Work completed successfully.
        CONTEXT_HANDOFF: Ready for fresh session
        Cleaning up resources.
        """
        signal = detector.detect_first(output)
        assert signal is not None
        assert signal.signal_type == "handoff"

    def test_custom_patterns_only(self) -> None:
        """Custom patterns replace defaults."""
        custom = SignalPattern("custom", r"CUSTOM:\s*(.+)")
        detector = SignalDetector(patterns=[custom])

        # Should not detect default patterns
        assert detector.detect_first("CONTEXT_HANDOFF: test") is None

        # Should detect custom pattern
        signal = detector.detect_first("CUSTOM: value")
        assert signal is not None
        assert signal.signal_type == "custom"
```

**File**: `scripts/tests/test_handoff_handler.py`
**Changes**: Create new test file

```python
"""Tests for handoff_handler module."""

from unittest.mock import patch

import pytest

from little_loops.fsm.handoff_handler import (
    HandoffBehavior,
    HandoffHandler,
    HandoffResult,
)


class TestHandoffHandler:
    """Tests for HandoffHandler class."""

    def test_terminate_behavior(self) -> None:
        """Terminate returns without spawning."""
        handler = HandoffHandler(HandoffBehavior.TERMINATE)
        result = handler.handle("test-loop", "continuation prompt")
        assert result.behavior == HandoffBehavior.TERMINATE
        assert result.continuation_prompt == "continuation prompt"
        assert result.spawned_process is None

    def test_pause_behavior(self) -> None:
        """Pause returns without spawning."""
        handler = HandoffHandler(HandoffBehavior.PAUSE)
        result = handler.handle("test-loop", "continuation prompt")
        assert result.behavior == HandoffBehavior.PAUSE
        assert result.continuation_prompt == "continuation prompt"
        assert result.spawned_process is None

    def test_spawn_behavior(self) -> None:
        """Spawn launches Claude process."""
        with patch("subprocess.Popen") as mock_popen:
            handler = HandoffHandler(HandoffBehavior.SPAWN)
            result = handler.handle("test-loop", "continuation prompt")

            assert result.behavior == HandoffBehavior.SPAWN
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert "claude" in cmd
            assert "-p" in cmd

    def test_default_behavior_is_pause(self) -> None:
        """Default behavior is pause."""
        handler = HandoffHandler()
        assert handler.behavior == HandoffBehavior.PAUSE

    def test_none_continuation(self) -> None:
        """Handles None continuation prompt."""
        handler = HandoffHandler(HandoffBehavior.PAUSE)
        result = handler.handle("test-loop", None)
        assert result.continuation_prompt is None
```

#### Success Criteria

**Automated Verification**:
- [ ] All new tests pass: `python -m pytest scripts/tests/test_signal_detector.py scripts/tests/test_handoff_handler.py -v`
- [ ] Test coverage for new modules > 90%

---

## Testing Strategy

### Unit Tests
- `test_signal_detector.py`: Pattern matching, multi-signal detection, edge cases
- `test_handoff_handler.py`: All three behaviors, subprocess mocking
- Updates to `test_fsm_executor.py`: Executor with signal detection enabled

### Integration Tests
- Test handoff → save state → resume cycle
- Test `on_handoff: terminate` behavior
- Test backward compatibility (no signal detection by default)

## References

- Original issue: `.issues/features/P3-FEAT-091-loop-context-handoff-integration.md`
- Existing handoff detection: `scripts/little_loops/subprocess_utils.py:24`
- FSM executor: `scripts/little_loops/fsm/executor.py:172`
- Persistence: `scripts/little_loops/fsm/persistence.py:201`
- Schema: `scripts/little_loops/fsm/schema.py:323`
- CLI resume: `scripts/little_loops/cli.py:864`
