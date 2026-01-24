# ENH-127: Loop simulation/dry-run mode - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P4-ENH-127-loop-simulation-dry-run-mode.md
- **Type**: enhancement
- **Priority**: P4
- **Action**: implement

## Current State Analysis

The `ll-loop` CLI already has:
1. **`--dry-run` flag** (cli.py:497-498, 700-702) - Prints execution plan showing states and transitions without running
2. **`ll-loop test` command** (cli.py:973-1121) - Runs a single iteration of the initial state
3. **`MockActionRunner`** in tests (test_fsm_executor.py:22-81) - Pattern for mocking action execution
4. **`ActionRunner` Protocol** (executor.py:95-114) - Interface for dependency injection

### Key Discoveries
- `print_execution_plan()` at cli.py:565-599 shows FSM structure but doesn't trace execution
- `FSMExecutor` accepts `action_runner` parameter at executor.py:199 for dependency injection
- Progress display with event callbacks exists at cli.py:601-668
- `cmd_test()` at cli.py:973-1121 executes single iteration but uses real command execution

### Patterns to Follow
- `MockActionRunner` pattern from test_fsm_executor.py:22-81 for simulation
- Progress display pattern from cli.py:601-668 for trace output
- `choices` parameter pattern from cli.py:1184 for scenario selection

## Desired End State

A new `ll-loop simulate <name>` subcommand that traces through loop logic interactively without executing commands:

```bash
ll-loop simulate fix-types
```

Output shows FSM execution trace with user prompts for simulated results:

```
=== SIMULATION: fix-types ===

[1] State: evaluate
    Action: mypy src/
    [SIMULATED] Would execute: mypy src/

    ? What should the simulated result be?
      > 0 (Success)
        1 (Failure)
        2+ (Error)

    Evaluator: exit_code
    Result: FAILURE
    Transition: evaluate → fix

[2] State: fix
    ...

=== Summary ===
States visited: evaluate → fix → evaluate → done
Iterations: 3
Would have executed 4 commands
```

### How to Verify
- `ll-loop simulate <loop-name>` traces through execution without running commands
- User can select simulated outcomes for each action
- Scenario mode `--scenario=all-pass|all-fail|first-fail` auto-selects outcomes
- Summary shows visited states and iteration count

## What We're NOT Doing

- **Not implementing Option C (--trace)** - Real execution with verbose logging is out of scope
- **Not modifying existing --dry-run** - Keep current behavior, add new `simulate` subcommand
- **Not adding GUI** - CLI-only interactive simulation
- **Not mocking LLM evaluators fully** - Provide simple verdict selection (success/failure/blocked)

## Problem Analysis

Users creating loops via `/ll:create_loop` can't verify FSM behavior before running. The existing `--dry-run` shows structure but not execution flow. Users need to trace through the state machine interactively to understand transitions and catch infinite loops.

## Solution Approach

Implement Option A (Interactive Simulation) + Option B (Predefined Scenarios) from the issue:

1. Add new `simulate` subcommand to `ll-loop`
2. Create `SimulationActionRunner` class that prompts user instead of executing
3. For scenario mode, auto-select results based on pattern
4. Reuse `FSMExecutor` with injected simulation runner
5. Display trace output in progress callback

## Implementation Phases

### Phase 1: SimulationActionRunner Class

#### Overview
Create a new action runner class that prompts user for simulated results instead of executing commands.

#### Changes Required

**File**: `scripts/little_loops/fsm/executor.py`
**Changes**: Add `SimulationActionRunner` class after `DefaultActionRunner`

```python
@dataclass
class SimulationActionRunner:
    """Action runner for simulation mode - prompts user instead of executing."""

    scenario: str | None = None  # "all-pass", "all-fail", "first-fail", "alternating"
    call_count: int = 0
    calls: list[str] = field(default_factory=list)

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
    ) -> ActionResult:
        """Prompt user for simulated result instead of executing."""
        self.calls.append(action)
        self.call_count += 1

        print(f"    [SIMULATED] Would execute: {action}")

        if self.scenario:
            exit_code = self._scenario_result()
        else:
            exit_code = self._prompt_result()

        return ActionResult(
            output=f"[simulated output for: {action}]",
            stderr="",
            exit_code=exit_code,
            duration_ms=0,
        )

    def _scenario_result(self) -> int:
        """Return exit code based on scenario pattern."""
        if self.scenario == "all-pass":
            return 0
        elif self.scenario == "all-fail":
            return 1
        elif self.scenario == "first-fail":
            return 1 if self.call_count == 1 else 0
        elif self.scenario == "alternating":
            return 1 if self.call_count % 2 == 1 else 0
        return 0

    def _prompt_result(self) -> int:
        """Prompt user for simulated exit code."""
        print()
        print("    ? What should the simulated result be?")
        print("      1) Success (exit 0)")
        print("      2) Failure (exit 1)")
        print("      3) Error (exit 2)")

        while True:
            try:
                choice = input("    > ").strip()
                if choice in ("1", ""):
                    return 0
                elif choice == "2":
                    return 1
                elif choice == "3":
                    return 2
                print("    Invalid choice. Enter 1, 2, or 3.")
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_executor.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/executor.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/executor.py`

**Manual Verification**:
- [ ] `SimulationActionRunner` class exists and follows `ActionRunner` protocol

---

### Phase 2: CLI Subcommand and Integration

#### Overview
Add the `simulate` subcommand to `ll-loop` CLI and wire up the simulation runner.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add simulate subcommand parser and handler

1. Add "simulate" to known subcommands (around line 449):
```python
known_subcommands = {
    "run", "compile", "validate", "list", "status", "stop", "resume", "history", "test",
    "simulate",  # NEW
}
```

2. Add simulate parser (after test parser, around line 545):
```python
# Simulate subparser
simulate_parser = subparsers.add_parser(
    "simulate",
    help="Trace loop execution interactively without running commands",
)
simulate_parser.add_argument("loop_name", help="Name of the loop to simulate")
simulate_parser.add_argument(
    "--scenario",
    choices=["all-pass", "all-fail", "first-fail", "alternating"],
    help="Auto-select results based on pattern instead of prompting",
)
simulate_parser.add_argument(
    "--max-iterations",
    type=int,
    help="Override max iterations for simulation",
)
```

3. Add simulate command handler (around line 1130):
```python
def cmd_simulate(loop_name: str) -> int:
    """Run interactive simulation of loop execution."""
    from little_loops.fsm.executor import FSMExecutor, SimulationActionRunner
    from little_loops.fsm.validation import load_and_validate

    try:
        path = resolve_loop_path(loop_name)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1

    # Load and compile if needed
    content = path.read_text()
    parsed = yaml.safe_load(content)

    if "paradigm" in parsed:
        from little_loops.fsm.compilers import compile_paradigm
        fsm = compile_paradigm(parsed)
    else:
        fsm = load_and_validate(path)

    # Apply CLI overrides
    if args.max_iterations:
        fsm.max_iterations = args.max_iterations

    # Limit iterations for simulation safety
    if fsm.max_iterations > 20:
        fsm.max_iterations = 20
        print(f"Note: Limiting simulation to 20 iterations")

    # Create simulation runner
    sim_runner = SimulationActionRunner(scenario=args.scenario)

    # Track simulation state
    states_visited: list[str] = []

    def simulation_callback(event: dict) -> None:
        """Display simulation progress."""
        event_type = event.get("event")

        if event_type == "state_enter":
            iteration = event.get("iteration", 0)
            state = event.get("state", "")
            states_visited.append(state)
            print()
            print(f"[{iteration}] State: {state}")

        elif event_type == "action_start":
            action = event.get("action", "")
            action_display = action[:70] + "..." if len(action) > 70 else action
            print(f"    Action: {action_display}")

        elif event_type == "evaluate":
            evaluator = event.get("evaluator", "exit_code")
            verdict = event.get("verdict", "")
            print(f"    Evaluator: {evaluator}")
            print(f"    Result: {verdict.upper()}")

        elif event_type == "route":
            from_state = event.get("from", "")
            to_state = event.get("to", "")
            print(f"    Transition: {from_state} → {to_state}")

    # Print header
    mode = f"scenario={args.scenario}" if args.scenario else "interactive"
    print(f"=== SIMULATION: {fsm.name} ({mode}) ===")

    # Run simulation
    executor = FSMExecutor(
        fsm,
        event_callback=simulation_callback,
        action_runner=sim_runner,
    )
    result = executor.run()

    # Print summary
    print()
    print("=== Summary ===")
    print(f"States visited: {' → '.join(states_visited)}")
    print(f"Iterations: {result.iterations}")
    print(f"Would have executed {len(sim_runner.calls)} commands")
    print(f"Terminated by: {result.terminated_by}")

    return 0
```

4. Add dispatch case (around line 712):
```python
elif args.subcommand == "simulate":
    return cmd_simulate(args.loop_name)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/cli.py`

**Manual Verification**:
- [ ] `ll-loop simulate --help` shows new command with options
- [ ] `ll-loop simulate <loop-name>` runs interactive simulation
- [ ] `ll-loop simulate <loop-name> --scenario=all-pass` auto-selects results

---

### Phase 3: Tests

#### Overview
Add tests for simulation functionality.

#### Changes Required

**File**: `scripts/tests/test_fsm_executor.py`
**Changes**: Add tests for SimulationActionRunner

```python
class TestSimulationActionRunner:
    """Tests for SimulationActionRunner."""

    def test_scenario_all_pass(self) -> None:
        """All-pass scenario returns exit code 0."""
        runner = SimulationActionRunner(scenario="all-pass")
        for _ in range(5):
            result = runner.run("test cmd", timeout=60, is_slash_command=False)
            assert result.exit_code == 0

    def test_scenario_all_fail(self) -> None:
        """All-fail scenario returns exit code 1."""
        runner = SimulationActionRunner(scenario="all-fail")
        for _ in range(5):
            result = runner.run("test cmd", timeout=60, is_slash_command=False)
            assert result.exit_code == 1

    def test_scenario_first_fail(self) -> None:
        """First-fail scenario returns 1 first, then 0."""
        runner = SimulationActionRunner(scenario="first-fail")
        result1 = runner.run("test cmd", timeout=60, is_slash_command=False)
        result2 = runner.run("test cmd", timeout=60, is_slash_command=False)
        result3 = runner.run("test cmd", timeout=60, is_slash_command=False)
        assert result1.exit_code == 1
        assert result2.exit_code == 0
        assert result3.exit_code == 0

    def test_scenario_alternating(self) -> None:
        """Alternating scenario returns 1, 0, 1, 0..."""
        runner = SimulationActionRunner(scenario="alternating")
        results = [runner.run("test", timeout=60, is_slash_command=False).exit_code for _ in range(4)]
        assert results == [1, 0, 1, 0]

    def test_records_calls(self) -> None:
        """Runner records all calls."""
        runner = SimulationActionRunner(scenario="all-pass")
        runner.run("cmd1", timeout=60, is_slash_command=False)
        runner.run("cmd2", timeout=60, is_slash_command=False)
        assert runner.calls == ["cmd1", "cmd2"]
        assert runner.call_count == 2
```

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add tests for simulate subcommand

```python
class TestSimulateCommand:
    """Tests for ll-loop simulate command."""

    def test_simulate_shows_help(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Simulate subcommand shows help."""
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "simulate", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                from little_loops.cli import main_loop
                main_loop()
            assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "simulate" in captured.out
        assert "--scenario" in captured.out

    def test_simulate_scenario_mode(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Simulate with scenario runs without prompts."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: check
max_iterations: 3
states:
  check:
    action: "echo check"
    on_success: done
    on_failure: check
  done:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "simulate", "test", "--scenario=all-pass"]):
            from little_loops.cli import main_loop
            result = main_loop()
        assert result == 0
        captured = capsys.readouterr()
        assert "SIMULATION: test" in captured.out
        assert "Summary" in captured.out
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_executor.py::TestSimulationActionRunner -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestSimulateCommand -v`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Create a simple loop and run `ll-loop simulate <name> --scenario=all-pass`
- [ ] Verify trace shows state transitions correctly
- [ ] Run without --scenario and verify interactive prompts work

---

## Testing Strategy

### Unit Tests
- `SimulationActionRunner` scenario patterns (all-pass, all-fail, first-fail, alternating)
- Call recording in simulation runner
- CLI argument parsing for simulate subcommand

### Integration Tests
- Full simulation run with scenario mode
- Simulation of paradigm-based loops (auto-compile)
- Max iterations limit enforcement

## References

- Original issue: `.issues/enhancements/P4-ENH-127-loop-simulation-dry-run-mode.md`
- `MockActionRunner` pattern: `scripts/tests/test_fsm_executor.py:22-81`
- `ActionRunner` Protocol: `scripts/little_loops/fsm/executor.py:95-114`
- Progress display pattern: `scripts/little_loops/cli.py:601-668`
- Existing `cmd_test()`: `scripts/little_loops/cli.py:973-1121`
