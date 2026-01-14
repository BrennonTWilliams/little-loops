# FEAT-045: FSM Executor Core

## Summary

Implement the core FSM execution engine that runs state machines: executing actions, evaluating results, routing to next states, and enforcing safety limits.

## Priority

P1 - Core execution engine

## Dependencies

- FEAT-040: FSM Schema Definition and Validation
- FEAT-041: Paradigm Compilers
- FEAT-042: Variable Interpolation System
- FEAT-043: Tier 1 Deterministic Evaluators
- FEAT-044: Tier 2 LLM Evaluator

## Blocked By

- FEAT-040, FEAT-042, FEAT-043

## Description

The FSM Executor is the runtime engine that:

1. Loads and validates FSM definitions
2. Executes actions (shell commands or slash commands)
3. Evaluates results using appropriate evaluators
4. Routes to next state based on verdict
5. Tracks iteration count and enforces limits
6. Manages captured variables and context

### Files to Create

```
scripts/little_loops/fsm/
└── executor.py
```

## Technical Details

### Execution Flow

```
1. Load FSM from YAML
2. Set state to `initial`
3. Execute action (shell or Claude CLI)
4. Evaluate result (deterministic or LLM)
5. Route to next state based on verdict
6. Emit event
7. Repeat until terminal or limits reached
```

### Executor Class

```python
# executor.py
from dataclasses import dataclass, field
from pathlib import Path
import subprocess
import time
from typing import Callable

from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.fsm.evaluators import evaluate, EvaluationResult
from little_loops.fsm.interpolation import InterpolationContext, interpolate

@dataclass
class ExecutionResult:
    final_state: str
    iterations: int
    terminated_by: str  # "terminal", "max_iterations", "timeout", "error"
    duration_ms: int
    captured: dict
    error: str | None = None

@dataclass
class ActionResult:
    output: str
    stderr: str
    exit_code: int
    duration_ms: int

EventCallback = Callable[[dict], None]


class FSMExecutor:
    """Execute an FSM loop."""

    def __init__(
        self,
        fsm: FSMLoop,
        event_callback: EventCallback | None = None,
        action_runner: "ActionRunner | None" = None,
    ):
        self.fsm = fsm
        self.event_callback = event_callback or (lambda e: None)
        self.action_runner = action_runner or DefaultActionRunner()

        # Runtime state
        self.current_state = fsm.initial
        self.iteration = 0
        self.captured: dict[str, dict] = {}
        self.prev_result: dict | None = None
        self.started_at = ""
        self.start_time_ms = 0

    def run(self) -> ExecutionResult:
        """Execute the FSM until terminal state or limits reached."""
        self.started_at = _iso_now()
        self.start_time_ms = _now_ms()

        self._emit("loop_start", {"loop": self.fsm.name})

        try:
            while True:
                # Check limits
                if self.iteration >= self.fsm.max_iterations:
                    return self._finish("max_iterations")

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
                self._emit("state_enter", {
                    "state": self.current_state,
                    "iteration": self.iteration,
                })

                # Execute state
                next_state = self._execute_state(state_config)

                # Handle maintain mode
                if next_state is None and self.fsm.maintain:
                    next_state = state_config.on_maintain or self.fsm.initial

                if next_state is None:
                    return self._finish("error", error="No valid transition")

                self._emit("route", {
                    "from": self.current_state,
                    "to": next_state,
                })

                self.current_state = next_state

        except Exception as e:
            return self._finish("error", error=str(e))

    def _execute_state(self, state: StateConfig) -> str | None:
        """Execute a single state and return next state name."""

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
        ctx.result = eval_result.__dict__ if eval_result else None

        # Route based on verdict
        return self._route(state, eval_result.verdict if eval_result else "success", ctx)

    def _run_action(
        self, action_template: str, state: StateConfig, ctx: InterpolationContext
    ) -> ActionResult:
        """Execute action and optionally capture result."""
        action = interpolate(action_template, ctx)

        self._emit("action_start", {"action": action})

        result = self.action_runner.run(
            action,
            timeout=state.timeout or 120,
            is_slash_command=action.startswith("/"),
        )

        self._emit("action_complete", {
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
        })

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
        """Evaluate action result."""
        if state.evaluate is None:
            # Default evaluation based on action type
            if action_result:
                if state.action and state.action.startswith("/"):
                    # Slash command: use LLM evaluation
                    from little_loops.fsm.evaluators import evaluate_llm_structured, LLMEvaluatorConfig
                    config = LLMEvaluatorConfig(
                        model=self.fsm.llm.model,
                        max_tokens=self.fsm.llm.max_tokens,
                        timeout=self.fsm.llm.timeout,
                    )
                    result = evaluate_llm_structured(action_result.output, config)
                else:
                    # Shell command: use exit code
                    from little_loops.fsm.evaluators import evaluate_exit_code
                    result = evaluate_exit_code(action_result.exit_code)

                self._emit("evaluate", {
                    "type": "default",
                    "verdict": result.verdict,
                })
                return result
            return None

        # Explicit evaluation config
        result = evaluate(
            config=state.evaluate,
            output=action_result.output if action_result else "",
            exit_code=action_result.exit_code if action_result else 0,
            context=ctx,
        )

        self._emit("evaluate", {
            "type": state.evaluate.type,
            "verdict": result.verdict,
            **result.details,
        })

        return result

    def _route(
        self, state: StateConfig, verdict: str, ctx: InterpolationContext
    ) -> str | None:
        """Determine next state from verdict."""

        # Resolution order (from design doc):
        # 1. next (unconditional) - handled before this method
        # 2. route (full routing table)
        # 3. on_success/on_failure/on_error (shorthand)
        # 4. terminal - handled in main loop
        # 5. error

        if state.route:
            routes = state.route.routes
            if verdict in routes:
                return self._resolve_route(routes[verdict], ctx)
            if state.route.default and "_" in routes:
                return self._resolve_route(routes["_"], ctx)
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
        """Resolve route target, handling special tokens."""
        if route == "$current":
            return self.current_state
        return interpolate(route, ctx)

    def _build_context(self) -> InterpolationContext:
        """Build interpolation context for current state."""
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

    def _emit(self, event: str, data: dict):
        """Emit an event."""
        self.event_callback({
            "event": event,
            "ts": _iso_now(),
            **data,
        })

    def _finish(self, terminated_by: str, error: str | None = None) -> ExecutionResult:
        """Finalize execution."""
        self._emit("loop_complete", {
            "final_state": self.current_state,
            "iterations": self.iteration,
            "terminated_by": terminated_by,
        })

        return ExecutionResult(
            final_state=self.current_state,
            iterations=self.iteration,
            terminated_by=terminated_by,
            duration_ms=_now_ms() - self.start_time_ms,
            captured=self.captured,
            error=error,
        )


class DefaultActionRunner:
    """Execute actions via subprocess or Claude CLI."""

    def run(
        self, action: str, timeout: int, is_slash_command: bool
    ) -> ActionResult:
        start = _now_ms()

        if is_slash_command:
            # Execute via Claude CLI
            cmd = [
                "claude",
                "--dangerously-skip-permissions",
                "-p", action,
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
    return int(time.time() * 1000)

def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
```

## Acceptance Criteria

- [ ] `FSMExecutor` loads FSM and executes from initial state
- [ ] Shell commands execute via `subprocess.run()`
- [ ] Slash commands execute via `claude --dangerously-skip-permissions -p "..."`
- [ ] Default evaluation: exit_code for shell, llm_structured for slash commands
- [ ] Explicit evaluate config overrides defaults
- [ ] Routing resolves verdict → next state via route table or shorthand
- [ ] `$current` special token routes back to current state
- [ ] `max_iterations` terminates loop with "max_iterations" reason
- [ ] `timeout` (loop-level) terminates loop with "timeout" reason
- [ ] `capture` stores action result in `captured` dict
- [ ] `maintain: true` restarts from initial after terminal state
- [ ] Events emitted for: loop_start, state_enter, action_start, action_complete, evaluate, route, loop_complete
- [ ] `ExecutionResult` contains final_state, iterations, terminated_by, duration_ms, captured

## Testing Requirements

```python
# tests/integration/test_executor.py
class TestFSMExecutor:
    @pytest.fixture
    def mock_action_runner(self):
        """Mock that captures actions and returns configured results."""
        return MockActionRunner()

    def test_simple_success_path(self, mock_action_runner):
        """check → done on first success."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(action="pytest", on_success="done", on_failure="fix"),
                "done": StateConfig(terminal=True),
            }
        )
        mock_action_runner.set_result("pytest", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_action_runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.iterations == 1
        assert result.terminated_by == "terminal"

    def test_fix_retry_loop(self, mock_action_runner):
        """check → fix → check → done with retry."""
        mock_action_runner.set_results([
            ("pytest", {"exit_code": 1}),
            ("fix.sh", {"exit_code": 0}),
            ("pytest", {"exit_code": 0}),
        ])

        # ... test implementation

    def test_max_iterations_respected(self, mock_action_runner):
        """Loop terminates at max_iterations."""
        fsm = FSMLoop(name="test", initial="loop", max_iterations=3, states={
            "loop": StateConfig(action="fail.sh", on_failure="loop"),
        })
        mock_action_runner.always_return(exit_code=1)

        result = FSMExecutor(fsm, action_runner=mock_action_runner).run()

        assert result.iterations == 3
        assert result.terminated_by == "max_iterations"

    def test_variable_interpolation(self, mock_action_runner):
        """${context.*} resolves in action."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            context={"target_dir": "src/"},
            states={
                "check": StateConfig(action="mypy ${context.target_dir}", on_success="done"),
                "done": StateConfig(terminal=True),
            }
        )
        mock_action_runner.set_result_for_action("mypy src/", exit_code=0)

        FSMExecutor(fsm, action_runner=mock_action_runner).run()

        assert mock_action_runner.last_action == "mypy src/"

    def test_capture_stores_output(self, mock_action_runner):
        """capture: saves action result."""
        fsm = FSMLoop(name="test", initial="measure", states={
            "measure": StateConfig(action="count.sh", capture="errors", next="done"),
            "done": StateConfig(terminal=True),
        })
        mock_action_runner.set_result("count.sh", output="42", exit_code=0)

        result = FSMExecutor(fsm, action_runner=mock_action_runner).run()

        assert result.captured["errors"]["output"] == "42"

    def test_events_emitted(self):
        """Event callback receives all lifecycle events."""
        events = []
        executor = FSMExecutor(fsm, event_callback=events.append, ...)
        executor.run()

        event_types = [e["event"] for e in events]
        assert "loop_start" in event_types
        assert "state_enter" in event_types
        assert "loop_complete" in event_types
```

## Reference

- Design doc: `docs/generalized-fsm-loop.md` sections "Execution Engine", "Two-Layer Transition System", "Security Model"
