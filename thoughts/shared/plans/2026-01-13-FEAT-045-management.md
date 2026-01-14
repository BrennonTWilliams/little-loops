# FEAT-045: FSM Executor Core - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P1-FEAT-045-fsm-executor-core.md`
- **Type**: feature
- **Priority**: P1
- **Action**: implement

## Current State Analysis

The FSM system already has all dependent components implemented:

### Key Discoveries
- `scripts/little_loops/fsm/schema.py:323-409` - `FSMLoop` dataclass with states, context, iteration limits
- `scripts/little_loops/fsm/evaluators.py:502-612` - `evaluate()` dispatcher routing to specific evaluators
- `scripts/little_loops/fsm/interpolation.py:169-206` - `interpolate()` function for `${namespace.path}` resolution
- `scripts/little_loops/fsm/evaluators.py:43-54` - `EvaluationResult` dataclass with verdict/details
- `scripts/little_loops/subprocess_utils.py:55-148` - Existing subprocess execution pattern with callbacks

### Dependencies Complete
- FEAT-040: FSM Schema Definition (FSMLoop, StateConfig, EvaluateConfig, RouteConfig)
- FEAT-041: Paradigm Compilers (compile_paradigm)
- FEAT-042: Variable Interpolation (interpolate, InterpolationContext)
- FEAT-043: Tier 1 Deterministic Evaluators (exit_code, output_numeric, output_json, output_contains, convergence)
- FEAT-044: Tier 2 LLM Evaluator (llm_structured)

## Desired End State

A fully functional `FSMExecutor` class that:
1. Takes an `FSMLoop` instance and executes it to completion
2. Supports shell commands via `subprocess.run()` and slash commands via `claude CLI`
3. Uses the two-layer transition system (evaluate → route)
4. Tracks state, captures variables, and emits events
5. Respects `max_iterations`, `timeout`, and `maintain` settings

### How to Verify
- Unit tests pass for executor logic
- Integration tests with mock action runner demonstrate full execution paths
- All existing FSM tests continue to pass
- Type checking passes

## What We're NOT Doing

- **NOT** implementing state persistence (FEAT-046)
- **NOT** implementing the CLI tool `ll-loop` (FEAT-047)
- **NOT** implementing scope-based concurrency control (FEAT-049)
- **NOT** adding background/daemon execution
- Deferring resume from persisted state to FEAT-046

## Problem Analysis

Need to implement the runtime engine that:
1. Maintains FSM state (current state, iteration, captured values)
2. Executes actions and captures output
3. Applies evaluation to determine verdict
4. Routes to next state based on verdict
5. Terminates on terminal state or limits

## Solution Approach

Create `executor.py` with:
1. `ExecutionResult` - Dataclass for execution outcome
2. `ActionResult` - Dataclass for action execution output
3. `ActionRunner` protocol - Interface for action execution (enables mocking)
4. `DefaultActionRunner` - Default implementation using subprocess
5. `FSMExecutor` - Main executor class

Follow existing patterns:
- Dataclass with `to_dict()`/`from_dict()` like schema classes
- Event callback pattern from subprocess_utils
- Type hints throughout

## Implementation Phases

### Phase 1: Create executor.py with Result Dataclasses

#### Overview
Create the executor module with result dataclasses and type definitions.

#### Changes Required

**File**: `scripts/little_loops/fsm/executor.py`
**Changes**: Create new file with dataclasses and type definitions

```python
"""FSM Executor - Runtime engine for FSM loop execution.

This module provides the execution engine that runs FSM loops:
- Executes actions (shell commands or slash commands)
- Evaluates results using appropriate evaluators
- Routes to next states based on verdicts
- Tracks iteration count and enforces limits
- Manages captured variables and context
"""

from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from little_loops.fsm.evaluators import (
    EvaluationResult,
    evaluate,
    evaluate_exit_code,
    evaluate_llm_structured,
)
from little_loops.fsm.interpolation import InterpolationContext, interpolate
from little_loops.fsm.schema import FSMLoop, StateConfig


@dataclass
class ExecutionResult:
    """Result from FSM execution.

    Attributes:
        final_state: Name of the state when execution stopped
        iterations: Total iterations executed
        terminated_by: Reason for termination (terminal, max_iterations, timeout, error)
        duration_ms: Total execution time in milliseconds
        captured: All captured variable values
        error: Error message if terminated_by is "error"
    """

    final_state: str
    iterations: int
    terminated_by: str  # "terminal", "max_iterations", "timeout", "error"
    duration_ms: int
    captured: dict[str, dict[str, Any]]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "final_state": self.final_state,
            "iterations": self.iterations,
            "terminated_by": self.terminated_by,
            "duration_ms": self.duration_ms,
            "captured": self.captured,
        }
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass
class ActionResult:
    """Result from action execution.

    Attributes:
        output: stdout from the action
        stderr: stderr from the action
        exit_code: Exit code from the action
        duration_ms: Execution time in milliseconds
    """

    output: str
    stderr: str
    exit_code: int
    duration_ms: int


# Type for event callback
EventCallback = Callable[[dict[str, Any]], None]


class ActionRunner(Protocol):
    """Protocol for action execution."""

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
    ) -> ActionResult:
        """Execute an action and return the result.

        Args:
            action: The command to execute
            timeout: Timeout in seconds
            is_slash_command: True if this is a slash command (starts with /)

        Returns:
            ActionResult with output, stderr, exit_code, duration_ms
        """
        ...
```

#### Success Criteria

**Automated Verification**:
- [ ] File created at correct location
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/executor.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/executor.py`

---

### Phase 2: Implement DefaultActionRunner

#### Overview
Implement the default action runner that executes shell commands and slash commands.

#### Changes Required

**File**: `scripts/little_loops/fsm/executor.py`
**Changes**: Add DefaultActionRunner class

```python
class DefaultActionRunner:
    """Execute actions via subprocess or Claude CLI."""

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
    ) -> ActionResult:
        """Execute action and return result.

        Args:
            action: The command to execute
            timeout: Timeout in seconds
            is_slash_command: True if action starts with /

        Returns:
            ActionResult with execution details
        """
        start = _now_ms()

        if is_slash_command:
            # Execute via Claude CLI
            cmd = [
                "claude",
                "--dangerously-skip-permissions",
                "-p",
                action,
            ]
        else:
            # Shell command
            cmd = ["bash", "-c", action]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ActionResult(
                output=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=_now_ms() - start,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                output="",
                stderr="Action timed out",
                exit_code=124,  # Standard timeout exit code
                duration_ms=timeout * 1000,
            )


def _now_ms() -> int:
    """Get current time in milliseconds."""
    return int(time.time() * 1000)


def _iso_now() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/executor.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/executor.py`

---

### Phase 3: Implement FSMExecutor Core

#### Overview
Implement the main FSMExecutor class with the execution loop.

#### Changes Required

**File**: `scripts/little_loops/fsm/executor.py`
**Changes**: Add FSMExecutor class

```python
class FSMExecutor:
    """Execute an FSM loop.

    The executor runs an FSM from its initial state until:
    - A terminal state is reached
    - max_iterations is exceeded
    - A timeout occurs
    - An unrecoverable error occurs

    Events are emitted via the callback for observability.
    """

    def __init__(
        self,
        fsm: FSMLoop,
        event_callback: EventCallback | None = None,
        action_runner: ActionRunner | None = None,
    ):
        """Initialize the executor.

        Args:
            fsm: The FSM loop to execute
            event_callback: Optional callback for events
            action_runner: Optional custom action runner (for testing)
        """
        self.fsm = fsm
        self.event_callback = event_callback or (lambda e: None)
        self.action_runner = action_runner or DefaultActionRunner()

        # Runtime state
        self.current_state = fsm.initial
        self.iteration = 0
        self.captured: dict[str, dict[str, Any]] = {}
        self.prev_result: dict[str, Any] | None = None
        self.started_at = ""
        self.start_time_ms = 0

    def run(self) -> ExecutionResult:
        """Execute the FSM until terminal state or limits reached.

        Returns:
            ExecutionResult with final state and execution metadata
        """
        self.started_at = _iso_now()
        self.start_time_ms = _now_ms()

        self._emit("loop_start", {"loop": self.fsm.name})

        try:
            while True:
                # Check iteration limit
                if self.iteration >= self.fsm.max_iterations:
                    return self._finish("max_iterations")

                # Check timeout
                if self.fsm.timeout:
                    elapsed = _now_ms() - self.start_time_ms
                    if elapsed > self.fsm.timeout * 1000:
                        return self._finish("timeout")

                # Get current state config
                state_config = self.fsm.states[self.current_state]

                # Check terminal
                if state_config.terminal:
                    return self._finish("terminal")

                self.iteration += 1
                self._emit(
                    "state_enter",
                    {
                        "state": self.current_state,
                        "iteration": self.iteration,
                    },
                )

                # Execute state
                next_state = self._execute_state(state_config)

                # Handle maintain mode
                if next_state is None and self.fsm.maintain:
                    next_state = state_config.on_maintain or self.fsm.initial

                if next_state is None:
                    return self._finish("error", error="No valid transition")

                self._emit(
                    "route",
                    {
                        "from": self.current_state,
                        "to": next_state,
                    },
                )

                self.current_state = next_state

        except Exception as e:
            return self._finish("error", error=str(e))

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        """Emit an event via the callback."""
        self.event_callback(
            {
                "event": event,
                "ts": _iso_now(),
                **data,
            }
        )

    def _finish(
        self, terminated_by: str, error: str | None = None
    ) -> ExecutionResult:
        """Finalize execution and return result."""
        self._emit(
            "loop_complete",
            {
                "final_state": self.current_state,
                "iterations": self.iteration,
                "terminated_by": terminated_by,
            },
        )

        return ExecutionResult(
            final_state=self.current_state,
            iterations=self.iteration,
            terminated_by=terminated_by,
            duration_ms=_now_ms() - self.start_time_ms,
            captured=self.captured,
            error=error,
        )
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/executor.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/executor.py`

---

### Phase 4: Implement State Execution Logic

#### Overview
Implement the `_execute_state`, `_run_action`, `_evaluate`, and `_route` methods.

#### Changes Required

**File**: `scripts/little_loops/fsm/executor.py`
**Changes**: Add state execution methods to FSMExecutor

```python
    def _execute_state(self, state: StateConfig) -> str | None:
        """Execute a single state and return next state name.

        Args:
            state: The state configuration to execute

        Returns:
            Next state name, or None if no valid transition
        """
        # Build interpolation context
        ctx = self._build_context()

        # Handle unconditional transition
        if state.next:
            if state.action:
                self._run_action(state.action, state, ctx)
            return interpolate(state.next, ctx)

        # Execute action if present
        action_result = None
        if state.action:
            action_result = self._run_action(state.action, state, ctx)

        # Evaluate
        eval_result = self._evaluate(state, action_result, ctx)
        self.prev_result = {
            "output": action_result.output if action_result else "",
            "exit_code": action_result.exit_code if action_result else 0,
            "state": self.current_state,
        }

        # Update context with result for routing interpolation
        if eval_result:
            ctx.result = eval_result.__dict__

        # Route based on verdict
        verdict = eval_result.verdict if eval_result else "success"
        return self._route(state, verdict, ctx)

    def _run_action(
        self,
        action_template: str,
        state: StateConfig,
        ctx: InterpolationContext,
    ) -> ActionResult:
        """Execute action and optionally capture result.

        Args:
            action_template: Action string (may contain variables)
            state: State configuration
            ctx: Interpolation context

        Returns:
            ActionResult with output and exit code
        """
        action = interpolate(action_template, ctx)

        self._emit("action_start", {"action": action})

        result = self.action_runner.run(
            action,
            timeout=state.timeout or 120,
            is_slash_command=action.startswith("/"),
        )

        self._emit(
            "action_complete",
            {
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            },
        )

        # Capture if requested
        if state.capture:
            self.captured[state.capture] = {
                "output": result.output,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            }

        return result

    def _evaluate(
        self,
        state: StateConfig,
        action_result: ActionResult | None,
        ctx: InterpolationContext,
    ) -> EvaluationResult | None:
        """Evaluate action result.

        Args:
            state: State configuration
            action_result: Result from action execution (may be None)
            ctx: Interpolation context

        Returns:
            EvaluationResult, or None if no evaluation needed
        """
        if state.evaluate is None:
            # Default evaluation based on action type
            if action_result:
                if state.action and state.action.startswith("/"):
                    # Slash command: use LLM evaluation
                    result = evaluate_llm_structured(
                        action_result.output,
                        model=self.fsm.llm.model,
                        max_tokens=self.fsm.llm.max_tokens,
                        timeout=self.fsm.llm.timeout,
                    )
                else:
                    # Shell command: use exit code
                    result = evaluate_exit_code(action_result.exit_code)

                self._emit(
                    "evaluate",
                    {
                        "type": "default",
                        "verdict": result.verdict,
                    },
                )
                return result
            return None

        # Explicit evaluation config
        result = evaluate(
            config=state.evaluate,
            output=action_result.output if action_result else "",
            exit_code=action_result.exit_code if action_result else 0,
            context=ctx,
        )

        self._emit(
            "evaluate",
            {
                "type": state.evaluate.type,
                "verdict": result.verdict,
                **result.details,
            },
        )

        return result

    def _route(
        self,
        state: StateConfig,
        verdict: str,
        ctx: InterpolationContext,
    ) -> str | None:
        """Determine next state from verdict.

        Resolution order (from design doc):
        1. next (unconditional) - handled before this method
        2. route (full routing table)
        3. on_success/on_failure/on_error (shorthand)
        4. terminal - handled in main loop
        5. error

        Args:
            state: State configuration
            verdict: Verdict string from evaluation
            ctx: Interpolation context

        Returns:
            Next state name, or None if no valid route
        """
        if state.route:
            routes = state.route.routes
            if verdict in routes:
                return self._resolve_route(routes[verdict], ctx)
            if state.route.default:
                return self._resolve_route(state.route.default, ctx)
            if verdict == "error" and state.route.error:
                return self._resolve_route(state.route.error, ctx)
            return None

        # Shorthand routing
        if verdict == "success" and state.on_success:
            return self._resolve_route(state.on_success, ctx)
        if verdict == "failure" and state.on_failure:
            return self._resolve_route(state.on_failure, ctx)
        if verdict == "error" and state.on_error:
            return self._resolve_route(state.on_error, ctx)

        return None

    def _resolve_route(self, route: str, ctx: InterpolationContext) -> str:
        """Resolve route target, handling special tokens.

        Args:
            route: Route target string
            ctx: Interpolation context

        Returns:
            Resolved state name
        """
        if route == "$current":
            return self.current_state
        return interpolate(route, ctx)

    def _build_context(self) -> InterpolationContext:
        """Build interpolation context for current state.

        Returns:
            InterpolationContext with all runtime values
        """
        return InterpolationContext(
            context=self.fsm.context,
            captured=self.captured,
            prev=self.prev_result,
            result=None,
            state_name=self.current_state,
            iteration=self.iteration,
            loop_name=self.fsm.name,
            started_at=self.started_at,
            elapsed_ms=_now_ms() - self.start_time_ms,
        )
```

#### Success Criteria

**Automated Verification**:
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/executor.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/executor.py`

---

### Phase 5: Create Comprehensive Tests

#### Overview
Create integration tests for the executor using a mock action runner.

#### Changes Required

**File**: `scripts/tests/test_fsm_executor.py`
**Changes**: Create new test file

```python
"""Tests for FSM Executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from little_loops.fsm.executor import (
    ActionResult,
    ActionRunner,
    ExecutionResult,
    FSMExecutor,
)
from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    LLMConfig,
    RouteConfig,
    StateConfig,
)


@dataclass
class MockActionRunner:
    """Mock action runner for testing."""

    results: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    call_index: int = 0
    calls: list[str] = field(default_factory=list)
    default_result: dict[str, Any] = field(
        default_factory=lambda: {"output": "", "stderr": "", "exit_code": 0}
    )

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
    ) -> ActionResult:
        """Return configured result for action."""
        self.calls.append(action)

        # Check for specific result
        for pattern, result_data in self.results:
            if pattern in action or pattern == action:
                return ActionResult(
                    output=result_data.get("output", ""),
                    stderr=result_data.get("stderr", ""),
                    exit_code=result_data.get("exit_code", 0),
                    duration_ms=result_data.get("duration_ms", 100),
                )

        # Check for indexed results
        if self.call_index < len(self.results):
            _, result_data = self.results[self.call_index]
            self.call_index += 1
            return ActionResult(
                output=result_data.get("output", ""),
                stderr=result_data.get("stderr", ""),
                exit_code=result_data.get("exit_code", 0),
                duration_ms=result_data.get("duration_ms", 100),
            )

        return ActionResult(
            output=self.default_result.get("output", ""),
            stderr=self.default_result.get("stderr", ""),
            exit_code=self.default_result.get("exit_code", 0),
            duration_ms=self.default_result.get("duration_ms", 100),
        )

    def set_result(self, action: str, **kwargs: Any) -> None:
        """Set result for a specific action pattern."""
        self.results.append((action, kwargs))

    def always_return(self, **kwargs: Any) -> None:
        """Set default result for all actions."""
        self.default_result = kwargs


class TestFSMExecutorBasic:
    """Basic executor tests."""

    def test_simple_success_path(self) -> None:
        """check → done on first success."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="pytest",
                    on_success="done",
                    on_failure="fix",
                ),
                "done": StateConfig(terminal=True),
                "fix": StateConfig(action="fix.sh", next="check"),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("pytest", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.iterations == 1
        assert result.terminated_by == "terminal"
        assert "pytest" in mock_runner.calls

    def test_fix_retry_loop(self) -> None:
        """check → fix → check → done with retry."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="pytest",
                    on_success="done",
                    on_failure="fix",
                ),
                "fix": StateConfig(action="fix.sh", next="check"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        # First check fails, fix succeeds, second check passes
        mock_runner.results = [
            ("pytest", {"exit_code": 1}),
            ("fix.sh", {"exit_code": 0}),
            ("pytest", {"exit_code": 0}),
        ]

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.iterations == 3
        assert result.terminated_by == "terminal"

    def test_max_iterations_respected(self) -> None:
        """Loop terminates at max_iterations."""
        fsm = FSMLoop(
            name="test",
            initial="loop",
            max_iterations=3,
            states={
                "loop": StateConfig(
                    action="fail.sh",
                    on_success="done",
                    on_failure="loop",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=1)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.iterations == 3
        assert result.terminated_by == "max_iterations"


class TestVariableInterpolation:
    """Tests for variable interpolation in executor."""

    def test_context_interpolation(self) -> None:
        """${context.*} resolves in action."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            context={"target_dir": "src/"},
            states={
                "check": StateConfig(
                    action="mypy ${context.target_dir}",
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

        assert "mypy src/" in mock_runner.calls


class TestCapture:
    """Tests for output capture."""

    def test_capture_stores_output(self) -> None:
        """capture: saves action result."""
        fsm = FSMLoop(
            name="test",
            initial="measure",
            states={
                "measure": StateConfig(
                    action="count.sh",
                    capture="errors",
                    next="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("count.sh", output="42", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert "errors" in result.captured
        assert result.captured["errors"]["output"] == "42"


class TestRouting:
    """Tests for verdict routing."""

    def test_full_route_table(self) -> None:
        """Full route table with custom verdicts."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="check.sh",
                    evaluate=EvaluateConfig(
                        type="output_contains",
                        pattern="BLOCKED",
                    ),
                    route=RouteConfig(
                        routes={"success": "done", "failure": "blocked"},
                    ),
                ),
                "done": StateConfig(terminal=True),
                "blocked": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.set_result("check.sh", output="BLOCKED: need help", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        # Pattern found = success, routes to "done"
        assert result.final_state == "done"

    def test_current_state_token(self) -> None:
        """$current token routes back to current state."""
        fsm = FSMLoop(
            name="test",
            initial="retry",
            max_iterations=3,
            states={
                "retry": StateConfig(
                    action="flaky.sh",
                    on_success="done",
                    on_failure="$current",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=1)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert result.iterations == 3
        assert result.terminated_by == "max_iterations"


class TestEvents:
    """Tests for event emission."""

    def test_events_emitted(self) -> None:
        """Event callback receives all lifecycle events."""
        events: list[dict[str, Any]] = []
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test.sh",
                    on_success="done",
                    on_failure="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(
            fsm, event_callback=events.append, action_runner=mock_runner
        )
        executor.run()

        event_types = [e["event"] for e in events]
        assert "loop_start" in event_types
        assert "state_enter" in event_types
        assert "action_start" in event_types
        assert "action_complete" in event_types
        assert "evaluate" in event_types
        assert "route" in event_types
        assert "loop_complete" in event_types


class TestMaintainMode:
    """Tests for maintain mode."""

    def test_maintain_restarts_after_terminal(self) -> None:
        """maintain: true restarts from initial after terminal."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            maintain=True,
            max_iterations=3,
            states={
                "check": StateConfig(
                    action="check.sh",
                    on_success="done",
                    on_failure="check",
                ),
                "done": StateConfig(terminal=True, on_maintain="check"),
            },
        )
        mock_runner = MockActionRunner()
        # All succeed, so should restart from check due to maintain mode
        mock_runner.always_return(exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        # Should hit max_iterations due to restart cycle
        assert result.terminated_by == "max_iterations"
        assert result.iterations == 3


class TestExecutionResult:
    """Tests for ExecutionResult."""

    def test_to_dict(self) -> None:
        """to_dict() serializes all fields."""
        result = ExecutionResult(
            final_state="done",
            iterations=5,
            terminated_by="terminal",
            duration_ms=1234,
            captured={"errors": {"output": "0"}},
            error=None,
        )

        d = result.to_dict()

        assert d["final_state"] == "done"
        assert d["iterations"] == 5
        assert d["terminated_by"] == "terminal"
        assert d["duration_ms"] == 1234
        assert d["captured"] == {"errors": {"output": "0"}}
        assert "error" not in d

    def test_to_dict_with_error(self) -> None:
        """to_dict() includes error when present."""
        result = ExecutionResult(
            final_state="fix",
            iterations=3,
            terminated_by="error",
            duration_ms=500,
            captured={},
            error="Something went wrong",
        )

        d = result.to_dict()

        assert d["error"] == "Something went wrong"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_executor.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_fsm_executor.py`

---

### Phase 6: Update Module Exports

#### Overview
Add executor exports to the fsm module's __init__.py.

#### Changes Required

**File**: `scripts/little_loops/fsm/__init__.py`
**Changes**: Add exports for executor classes

Add imports:
```python
from little_loops.fsm.executor import (
    ActionResult,
    ActionRunner,
    ExecutionResult,
    FSMExecutor,
)
```

Add to `__all__`:
```python
"ActionResult",
"ActionRunner",
"ExecutionResult",
"FSMExecutor",
```

#### Success Criteria

**Automated Verification**:
- [ ] Import test: `python -c "from little_loops.fsm import FSMExecutor, ExecutionResult, ActionResult"`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/__init__.py`

---

### Phase 7: Full Verification

#### Overview
Run all verification checks to ensure the implementation is complete.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Format check: `ruff format scripts/ --check`

---

## Testing Strategy

### Unit Tests
- ExecutionResult.to_dict() serialization
- ActionResult dataclass behavior

### Integration Tests
- Simple success path (check → done)
- Fix retry loop (check → fix → check → done)
- Max iterations termination
- Variable interpolation (${context.*})
- Capture stores output
- Full route table routing
- $current token routing
- Event emission
- Maintain mode restart

## References

- Original issue: `.issues/features/P1-FEAT-045-fsm-executor-core.md`
- Design doc: `docs/generalized-fsm-loop.md` (Execution Engine, Two-Layer Transition System, Security Model)
- Schema: `scripts/little_loops/fsm/schema.py:323-409`
- Evaluators: `scripts/little_loops/fsm/evaluators.py:502-612`
- Interpolation: `scripts/little_loops/fsm/interpolation.py:169-206`
- Similar pattern: `scripts/little_loops/subprocess_utils.py:55-148`
